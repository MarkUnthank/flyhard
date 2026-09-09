#!/usr/bin/env python3
"""One coordinator: learned foreleg control -> passive wheel -> CARLA.

The requested wheel angle and speed are scripted. The policy has no camera
input. CARLA consumes the measured wheel at the START of each 40 ms interval;
the fly and CARLA then advance to the same endpoint. This is an explicit
zero-order hold, not a mixture of independently recorded clips.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import time

import carla
import imageio.v2 as imageio
import numpy as np
import pyarrow.feather as feather
import torch

from flyhard.cockpit import WheelRig
from flyhard.motor_policy import WheelPolicy


FRAME_DT = 0.04
STEER_GAIN = 0.10
CHECKPOINT_SHA = 'd09953b336df742c00450489c26c3b0ba10de069b4de7e39f656a49a623a4df7'
GRAPH_SHA = 'eff4093bf53c4dd17d7ee4f2f838f6ae5ede70570f9a91317dd8824cca5c771d'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def requested_angle(t):
    """Two smooth, opposing steering cycles; this is a disclosed instruction."""
    if t < 2 or t >= 22:
        return 0.0
    phase = t - 2
    sign = 1 if phase < 10 else -1
    return float(sign * 0.30 * np.sin(2 * np.pi * (phase % 10) / 10))


def load_policy(graph_path, checkpoint_path):
    assert sha(checkpoint_path) == CHECKPOINT_SHA, 'Unexpected trained checkpoint'
    assert sha(graph_path / 'graph.npz') == GRAPH_SHA, 'Unexpected graph'
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    state = checkpoint['model']
    graph = np.load(graph_path / 'graph.npz')
    policy = WheelPolicy(graph, state['sensory_ids'].numpy(), state['motor_ids'].numpy(),
                         state['neutral'].numpy(), state['action_scale'].numpy(),
                         checkpoint['config']['seed'])
    policy.load_state_dict(state)
    return policy.to('cuda').eval()


def ranked_starts(world):
    """Choose a long straight road for the instructed control demonstration."""
    road_map = world.get_map()
    candidates = []
    for index, pose in enumerate(road_map.get_spawn_points()):
        waypoint = road_map.get_waypoint(pose.location)
        if waypoint is None or waypoint.is_junction:
            continue
        start_yaw = waypoint.transform.rotation.yaw
        distance = 0
        for _ in range(60):
            options = waypoint.next(2)
            if not options:
                break
            next_point = min(options, key=lambda p: abs((p.transform.rotation.yaw-start_yaw+180) % 360-180))
            delta = abs((next_point.transform.rotation.yaw-start_yaw+180) % 360-180)
            if next_point.is_junction or delta > 3:
                break
            distance += 2
            waypoint = next_point
        candidates.append((distance, index, pose))
    return sorted(candidates, key=lambda x: (-x[0], x[1]))


def connect_client():
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(5)
    for _ in range(30):
        try:
            world = client.get_world()
            client.set_timeout(40)
            return client, world
        except RuntimeError:
            time.sleep(2)
    raise RuntimeError('CARLA server did not become ready')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='runs/carla-cockpit-v1')
    parser.add_argument('--graph', default='data/graph-traced-v1')
    parser.add_argument('--checkpoint', default='runs/e03-wheel-pilot/checkpoint.pt')
    parser.add_argument('--seconds', type=float, default=24)
    parser.add_argument('--disable-grip', action='store_true')
    parser.add_argument('--speed', type=float, default=2.5)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    assert torch.cuda.is_available(), 'This capture must run on the remote GPU'
    assert 0 < args.seconds <= 30
    torch.set_num_threads(4)
    config = {
        **vars(args), 'experiment': 'Instructed learned steering coupled to CARLA',
        'claim': 'Learned foreleg controls a passive wheel; requested turns and vehicle speed are scripted.',
        'camera_input_to_policy': False, 'vehicle_autopilot': False,
        'neural_decision_hz': 20, 'joint_command_hz': 200, 'physics_dt_s': WheelRig.timestep,
        'carla_dt_s': FRAME_DT, 'camera_fps': 25, 'camera_size': [1200, 868],
        'steer_gain': STEER_GAIN, 'wheel_full_scale_rad': 0.65,
        'coupling': 'Read wheel at interval start; hold derived steer through one CARLA tick. Record both simulators at interval end.',
        'inertial_feedback': 'Thorax supported; vehicle acceleration is not fed into the stationary cockpit dynamics.',
        'checkpoint_sha256': CHECKPOINT_SHA, 'graph_sha256': GRAPH_SHA,
        'turn_schedule': '0 until 2 s; +0.3 sin(2pi(t-2)/10) until 12 s; -0.3 sin(2pi(t-12)/10) until 22 s; then 0.',
        'code_sha256': {name: sha(name) for name in ['scripts/capture_carla_cockpit.py',
            'src/flyhard/cockpit.py', 'src/flyhard/motor_policy.py', 'src/flyhard/connectome.py']},
        'pass_checks': 'Matching camera/world frames; clock error <0.0001 s; applied steer matches physical wheel mapping within 1e-7; finite body states.',
    }
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    start = time.perf_counter()
    policy = load_policy(Path(args.graph), Path(args.checkpoint))
    rig = WheelRig()
    rig.reset(grip=not args.disable_grip)
    client, world = connect_client()
    original_settings = world.get_settings()
    original_weather = world.get_weather()
    actors = []
    collisions = []
    records = []
    body = {key: [] for key in ['time', 'qpos', 'qvel', 'ctrl', 'wheel', 'grip_force', 'decision_index']}
    neural = {key: [] for key in ['time', 'activity', 'action', 'requested_angle']}
    source_video = None
    error = None
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = FRAME_DT
        settings.no_rendering_mode = False
        settings.substepping = True
        settings.max_substep_delta_time = 0.01
        settings.max_substeps = 4
        world.apply_settings(settings)
        world.set_weather(carla.WeatherParameters.ClearNoon)
        library = world.get_blueprint_library()
        blueprint = library.find('vehicle.mini.cooper_s_2021')
        blueprint.set_attribute('color', '48,84,43')
        vehicle = None
        for road_length, spawn_index, pose in ranked_starts(world):
            vehicle = world.try_spawn_actor(blueprint, pose)
            if vehicle is not None:
                break
        assert vehicle is not None, 'No unoccupied start'
        actors.append(vehicle)
        assert road_length >= 65, f'Straight test road too short: {road_length} m'
        vehicle.set_autopilot(False)
        config.update(map=world.get_map().name, spawn_index=spawn_index,
                      straight_road_length_m=road_length, carla_version=client.get_server_version())
        (out / 'config.json').write_text(json.dumps(config, indent=2))
        impact = world.spawn_actor(library.find('sensor.other.collision'), carla.Transform(), attach_to=vehicle)
        actors.append(impact)
        impact.listen(lambda event: collisions.append({'frame': event.frame, 'other': event.other_actor.type_id,
            'impulse': [event.normal_impulse.x, event.normal_impulse.y, event.normal_impulse.z]}))
        vehicle.apply_control(carla.VehicleControl(brake=1.0))
        for _ in range(50):
            world.tick()
        camera_bp = library.find('sensor.camera.rgb')
        for name, value in [('image_size_x', '1200'), ('image_size_y', '868'), ('fov', '80'), ('sensor_tick', '0')]:
            camera_bp.set_attribute(name, value)
        camera = world.spawn_actor(camera_bp,
            carla.Transform(carla.Location(x=-6, z=3.2), carla.Rotation(pitch=-18)), attach_to=vehicle)
        actors.append(camera)
        frames = queue.Queue()
        camera.listen(frames.put)
        base_time = world.get_snapshot().timestamp.elapsed_seconds
        base_location = vehicle.get_location()
        base_yaw = np.radians(vehicle.get_transform().rotation.yaw)
        forward = np.array([np.cos(base_yaw), np.sin(base_yaw)])
        side = np.array([-np.sin(base_yaw), np.cos(base_yaw)])
        base_position = np.array([base_location.x, base_location.y])
        collisions.clear()
        body_step = 0
        action = None
        source_video = imageio.get_writer(out / 'carla-camera.mp4', fps=25, codec='libx264',
            quality=None, macro_block_size=1, ffmpeg_params=['-crf', '16', '-preset', 'fast'])
        for index in range(round(args.seconds / FRAME_DT)):
            source_time = rig.data.time
            source_angle = rig.angle
            steer = float(np.clip(STEER_GAIN * source_angle / 0.65, -1, 1))
            velocity = vehicle.get_velocity()
            speed = float(np.linalg.norm([velocity.x, velocity.y, velocity.z]))
            speed_error = args.speed - speed
            throttle = float(np.clip(0.18 + 0.30 * speed_error, 0, 0.65))
            brake = float(np.clip(-0.25 * speed_error, 0, 0.25)) if speed_error < -0.25 else 0.0
            if brake > 0:
                throttle = 0.0
            vehicle.apply_control(carla.VehicleControl(steer=steer, throttle=throttle, brake=brake))
            for _ in range(8):
                if body_step % 10 == 0:
                    target = requested_angle(rig.data.time)
                    observation = np.r_[target, rig.angle, rig.data.qpos[rig.active_qpos]].astype(np.float32)
                    with torch.no_grad():
                        command, state = policy(torch.as_tensor(observation[None], device='cuda'), return_state=True)
                    action = command[0].cpu().numpy()
                    neural['time'].append(rig.data.time)
                    neural['activity'].append(state[:, 0].cpu().numpy())
                    neural['action'].append(action.copy())
                    neural['requested_angle'].append(target)
                rig.step(action)
                rows = (rig.data.efc_type == 0) & (rig.data.efc_id == rig.grip_id)
                body['time'].append(rig.data.time)
                body['qpos'].append(rig.data.qpos.copy())
                body['qvel'].append(rig.data.qvel.copy())
                body['ctrl'].append(rig.data.ctrl.copy())
                body['wheel'].append(rig.angle)
                body['grip_force'].append(float(np.linalg.norm(rig.data.efc_force[rows])))
                body['decision_index'].append(len(neural['time']) - 1)
                body_step += 1
            tick = world.tick()
            image = frames.get(timeout=30)
            while image.frame < tick:
                image = frames.get(timeout=30)
            assert image.frame == tick
            snapshot = world.get_snapshot()
            assert snapshot.frame == tick
            frame_time = image.timestamp - base_time
            assert abs(frame_time - rig.data.time) < 1e-4
            array = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(868, 1200, 4)[:, :, :3][:, :, ::-1].copy()
            assert array.std() > 1, 'Blank CARLA render'
            source_video.append_data(array)
            applied = vehicle.get_control()
            assert abs(applied.steer - steer) < 1e-7
            position = vehicle.get_location()
            end_velocity = vehicle.get_velocity()
            end_speed = float(np.linalg.norm([end_velocity.x, end_velocity.y, end_velocity.z]))
            displacement = np.array([position.x, position.y]) - base_position
            records.append({'index': index, 'frame': tick, 'camera_frame': image.frame,
                'camera_time': frame_time, 'body_time': rig.data.time,
                'body_index': len(body['time']) - 1, 'neural_index': len(neural['time']) - 1,
                'wheel_read_time': source_time, 'wheel_read_angle': source_angle,
                'applied_steer': applied.steer, 'expected_steer': steer,
                'throttle': applied.throttle, 'brake': applied.brake, 'speed_m_s': end_speed,
                'speed_control_read_m_s': speed,
                'requested_angle': requested_angle(rig.data.time), 'wheel_angle': rig.angle,
                'position': [position.x, position.y, position.z],
                'yaw_degrees': vehicle.get_transform().rotation.yaw,
                'longitudinal_m': float(displacement @ forward), 'lateral_m': float(displacement @ side)})
            if index % 100 == 0:
                print(json.dumps({'frames': index + 1, 'sim_time': rig.data.time,
                    'wheel_rad': rig.angle, 'steer': applied.steer, 'lateral_m': records[-1]['lateral_m']}), flush=True)
    except BaseException as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if source_video is not None:
            source_video.close()
        for actor in reversed(actors):
            if isinstance(actor, carla.Sensor):
                actor.stop()
            actor.destroy()
        world.apply_settings(original_settings)
        world.set_weather(original_weather)
        np.savez_compressed(out / 'body-trace.npz', **body)
        np.savez_compressed(out / 'neural-trace.npz', **neural)
        (out / 'frames.json').write_text(json.dumps(records, indent=2))
        (out / 'collisions.json').write_text(json.dumps(collisions, indent=2))
        metrics = {'status': 'capture_complete' if error is None else 'failed', 'error': error,
            'frames': len(records), 'neural_decisions': len(neural['time']), 'body_samples': len(body['time']),
            'wall_seconds': time.perf_counter() - start, 'collisions': len(collisions),
            'max_clock_error_s': max((abs(x['camera_time']-x['body_time']) for x in records), default=None),
            'max_control_mapping_error': max((abs(x['applied_steer']-x['expected_steer']) for x in records), default=None),
            'lateral_range_m': [min((x['lateral_m'] for x in records), default=0), max((x['lateral_m'] for x in records), default=0)],
            'wheel_range_rad': [min(body['wheel'], default=0), max(body['wheel'], default=0)],
            'distance_forward_m': records[-1]['longitudinal_m'] if records else 0,
            'gpu': torch.cuda.get_device_name(0)}
        (out / 'metrics.json').write_text(json.dumps(metrics, indent=2))
        print(json.dumps(metrics, indent=2), flush=True)
    nodes = feather.read_table(Path(args.graph) / 'nodes.feather')
    soma = np.array([v if v is not None else [np.nan]*3 for v in nodes['somaLocation'].to_pylist()])
    valid = np.flatnonzero(np.isfinite(soma).all(axis=1))
    np.savez_compressed(out / 'somata.npz', indices=valid, coordinates=soma[valid],
        body_ids=np.asarray(nodes['bodyId'])[valid])


if __name__ == '__main__':
    main()
