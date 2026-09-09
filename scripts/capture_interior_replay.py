#!/usr/bin/env python3
"""Record native cabin RGB/depth while replaying verified learned actions.

The body is simulated again from reset. CARLA steering comes from its measured
passive wheel. This camera experiment does not run fresh neural inference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

import carla
import mujoco as mj
import numpy as np
from PIL import Image
import queue

from flyhard.cockpit import WheelRig
from interior_camera_spike import camera_blueprint, receive


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',default='runs/interior-replay-v1')
    parser.add_argument('--actions',default='work/interior-actions')
    parser.add_argument('--seconds',type=float,default=7)
    parser.add_argument('--camera',nargs=5,type=float,default=[-.45,.08,1.35,-12,-23])
    args = parser.parse_args()
    assert 0 < args.seconds <= 10
    out = Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    (out/'rgb').mkdir(); (out/'depth').mkdir()
    action_root = Path(args.actions)
    provenance = json.loads((action_root/'source.json').read_text())
    assert sha(action_root/'actions.npz') == provenance['extract_sha256']
    with np.load(action_root/'actions.npz') as archive:
        actions,decision_times = archive['action'],archive['time']
    source_root = Path(provenance['source_run'])
    with np.load(source_root/'body-trace.npz') as archive:
        expected_qpos,expected_ctrl = archive['qpos'],archive['ctrl']
    shutil.copy2(action_root/'actions.npz',out/'actions.npz')
    shutil.copy2(action_root/'source.json',out/'action-source.json')
    source_config = provenance['source_config']
    width,height,fov,dt = 1280,720,90,0.04
    rig = WheelRig(support_hand=source_config['support_hand'])
    client = carla.Client('127.0.0.1',2000); client.set_timeout(40)
    world = client.get_world()
    original_settings,original_weather = world.get_settings(),world.get_weather()
    actors,records,collisions = [],[],[]
    body = {key:[] for key in ['time','qpos','qvel','ctrl','wheel','decision_index']}
    config = {'experiment':'Native cabin camera with a physics replay of previously learned actions',
        'native_carla_camera':True,'fly_in_carla':False,'fresh_neural_inference':False,
        'display':'Fly composited separately from synchronized MuJoCo poses with native depth occlusion.',
        'carla_version':client.get_server_version(),'map':world.get_map().name,
        'vehicle':'vehicle.mini.cooper_s_2021','spawn_index':source_config['spawn_index'],
        'width':width,'height':height,'fov_horizontal':fov,'camera_relative':args.camera,
        'camera_attachment':'Rigid','lens_k':0,'lens_kcube':0,'fps':25,
        'seconds':args.seconds,'support_hand':rig.support_hand,
        'speed_target_m_s':source_config['speed'],'steer_gain':source_config['steer_gain'],
        'coupling':'Wheel sampled at interval start; RGB, depth and body saved at same interval end.',
        'source_body_trace_sha256':sha(source_root/'body-trace.npz'),
        'script_sha256':sha(__file__),'cockpit_sha256':sha('src/flyhard/cockpit.py')}
    (out/'config.json').write_text(json.dumps(config,indent=2))
    start = time.monotonic(); step = 0; qpos_error = 0.; ctrl_error = 0.; error = None
    try:
        settings = world.get_settings(); settings.synchronous_mode = True
        settings.fixed_delta_seconds = dt; settings.no_rendering_mode = False
        settings.substepping = True; settings.max_substep_delta_time = .01; settings.max_substeps = 4
        world.apply_settings(settings); world.set_weather(carla.WeatherParameters.ClearNoon)
        bp = world.get_blueprint_library().find(config['vehicle']); bp.set_attribute('color','48,84,43')
        vehicle = world.spawn_actor(bp,world.get_map().get_spawn_points()[config['spawn_index']])
        actors.append(vehicle); vehicle.set_autopilot(False)
        impact = world.spawn_actor(world.get_blueprint_library().find('sensor.other.collision'),carla.Transform(),attach_to=vehicle)
        actors.append(impact)
        impact.listen(lambda event:collisions.append({'frame':event.frame,'other':event.other_actor.type_id}))
        vehicle.apply_control(carla.VehicleControl(brake=1))
        for _ in range(50):world.tick()
        x,y,z,pitch,yaw = args.camera
        pose = carla.Transform(carla.Location(x=x,y=y,z=z),carla.Rotation(pitch=pitch,yaw=yaw))
        channels = {kind:queue.Queue() for kind in ['rgb','depth']}; sensors = {}
        for kind in channels:
            sensor = world.spawn_actor(camera_blueprint(world,kind,width,height,fov),pose,
                attach_to=vehicle,attachment_type=carla.AttachmentType.Rigid)
            actors.append(sensor); sensors[kind] = sensor; sensor.listen(channels[kind].put)
        for _ in range(30):
            tick = world.tick()
            for channel in channels.values():receive(channel,tick)
        base = world.get_snapshot().timestamp.elapsed_seconds
        collisions.clear()
        for index in range(round(args.seconds/dt)):
            source_angle,source_time = rig.angle,rig.data.time
            steer = float(np.clip(config['steer_gain']*source_angle/.65,-1,1))
            velocity = vehicle.get_velocity()
            speed = float(np.linalg.norm([velocity.x,velocity.y,velocity.z]))
            speed_error = config['speed_target_m_s']-speed
            throttle = float(np.clip(.18+.30*speed_error,0,1))
            brake = float(np.clip(-.25*speed_error,0,.25)) if speed_error < -.25 else 0.
            if brake:throttle = 0.
            vehicle.apply_control(carla.VehicleControl(steer=steer,throttle=throttle,brake=brake))
            for _ in range(8):
                decision = step//10
                assert decision_times[decision] <= rig.data.time+1e-9
                rig.step(actions[decision])
                qpos_error = max(qpos_error,float(np.max(np.abs(rig.data.qpos-expected_qpos[step]))))
                ctrl_error = max(ctrl_error,float(np.max(np.abs(rig.data.ctrl-expected_ctrl[step]))))
                assert qpos_error < 1e-10 and ctrl_error < 1e-12, 'Original action/body replay diverged'
                for key in ['qpos','qvel','ctrl']:body[key].append(getattr(rig.data,key).copy())
                body['time'].append(rig.data.time); body['wheel'].append(rig.angle)
                body['decision_index'].append(decision); step += 1
            tick = world.tick()
            images = {kind:receive(channel,tick) for kind,channel in channels.items()}
            snapshot = world.get_snapshot(); assert snapshot.frame == tick
            camera_time = images['rgb'].timestamp-base
            assert abs(camera_time-rig.data.time) < 1e-4
            assert images['rgb'].timestamp == images['depth'].timestamp
            for kind,image in images.items():
                pixels = np.frombuffer(image.raw_data,np.uint8).reshape(height,width,4)[:,:,:3][:,:,::-1].copy()
                Image.fromarray(pixels).save(out/kind/f'{index:04}.png')
            applied = vehicle.get_control(); assert abs(applied.steer-steer) < 1e-7
            velocity = vehicle.get_velocity(); position = vehicle.get_location()
            camera_matrix = np.linalg.inv(vehicle.get_transform().get_matrix())@sensors['rgb'].get_transform().get_matrix()
            records.append({'index':index,'frame':tick,'rgb_frame':images['rgb'].frame,'depth_frame':images['depth'].frame,
                'camera_time':camera_time,'body_time':rig.data.time,'body_index':step-1,'decision_index':decision,
                'wheel_read_time':source_time,'wheel_read_angle':source_angle,'applied_steer':applied.steer,
                'expected_steer':steer,'wheel_angle':rig.angle,'camera_car_matrix':camera_matrix.tolist(),
                'speed_m_s':float(np.linalg.norm([velocity.x,velocity.y,velocity.z])),
                'position_m':[position.x,position.y,position.z]})
            if index%25 == 0:print(json.dumps({'frame':index,'body_time':rig.data.time,'wheel':rig.angle}),flush=True)
    except BaseException as exc:
        error = f'{type(exc).__name__}: {exc}'; raise
    finally:
        for actor in reversed(actors):
            if isinstance(actor,carla.Sensor):actor.stop()
            actor.destroy()
        world.apply_settings(original_settings); world.set_weather(original_weather)
        np.savez_compressed(out/'body-trace.npz',**body)
        (out/'frames.json').write_text(json.dumps(records,indent=2))
        (out/'collisions.json').write_text(json.dumps(collisions,indent=2))
        metrics = {'status':'complete' if error is None else 'failed','error':error,'frames':len(records),
            'body_samples':step,'source_body_replay_qpos_error':qpos_error,'source_body_replay_ctrl_error':ctrl_error,
            'max_clock_error_s':max((abs(r['camera_time']-r['body_time']) for r in records),default=None),
            'max_steer_mapping_error':max((abs(r['expected_steer']-r['applied_steer']) for r in records),default=None),
            'collisions':len(collisions),'wall_seconds':time.monotonic()-start}
        (out/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2),flush=True)


if __name__ == '__main__':main()
