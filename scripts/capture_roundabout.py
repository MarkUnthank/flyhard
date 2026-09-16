#!/usr/bin/env python3
"""Record causal fly controls, CARLA traffic, anatomy states and camera frames."""
import argparse
import json
import math
from pathlib import Path
import queue
import time

import carla
import imageio.v2 as imageio
import numpy as np
from PIL import Image
import torch

from flyhard.cockpit import WheelRig
from flyhard.live_livery import verify_live_livery
from flyhard.indicator_policy import encode_context
from flyhard.roundabout import DT, RoundaboutWorld, route_metadata, set_signal
from train_roundabout import load_policy, sha
from flyhard.roundabout_metrics import score_signals
from agents.navigation.basic_agent import BasicAgent
from flyhard.shot_cameras import ShotCameras


def next_image(inbox, frame):
    while True:
        result = inbox.get(timeout=45)
        if result.frame >= frame:
            assert result.frame == frame
            return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--asset", required=True, help="Fresh live sponsor export from refresh_live_livery.py")
    p.add_argument("--out", required=True)
    p.add_argument("--mode", choices=["indicators", "combined"], default="indicators")
    p.add_argument("--route", default="entry2-exit3")
    p.add_argument("--seconds", type=float, default=45)
    p.add_argument("--speed", type=float, default=25)
    p.add_argument("--seed", type=int, default=62031)
    p.add_argument("--traffic", type=int, default=14)
    p.add_argument("--erratic", type=float, default=0.)
    p.add_argument("--camera", choices=["rear-left", "front-right"], default="rear-left")
    p.add_argument("--directed", action="store_true", help="Also capture orbit, indicator and cabin cameras")
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=False)
    manifest = verify_live_livery(args.asset, out)
    (out / "depth").mkdir()
    torch.set_num_threads(4)
    policy, saved = load_policy(args.checkpoint)
    rig = WheelRig(indicator_stalk=True)
    env = RoundaboutWorld(render=True)
    route = next(r for r in env.routes if r["id"] == args.route)
    env.start(route, args.seed, args.speed, args.traffic)
    if args.mode == "combined":
        env.ego.set_autopilot(False, env.port)
    agent = BasicAgent(env.ego, target_speed=args.speed, map_inst=env.map, grp_inst=env.planner,
                      opt_dict={"dt": DT, "ignore_traffic_lights": True, "use_bbs_detection": True})
    agent.set_global_plan(route["plan"], stop_waypoint_creation=True, clean_queue=True)
    # Rear-left view keeps the left door and rear placements in shot together.
    camera_pose = carla.Transform(carla.Location(x=-5.2, y=-3.8, z=2.9),
                                  carla.Rotation(pitch=-16.4, yaw=36.2))
    if args.camera == "front-right":
        camera_pose = carla.Transform(carla.Location(x=5.2, y=3.8, z=2.9),
                                      carla.Rotation(pitch=-16.4, yaw=-143.8))
    cameras, inboxes = [], []
    library = env.world.get_blueprint_library()
    for kind in ["rgb", "depth"]:
        blueprint = library.find("sensor.camera." + kind)
        for name, value in {"image_size_x": "1248", "image_size_y": "960", "fov": "65", "sensor_tick": "0.0"}.items():
            blueprint.set_attribute(name, value)
        blueprint.set_attribute("lens_k", "0.0")
        blueprint.set_attribute("lens_kcube", "0.0")
        if kind == "rgb":
            blueprint.set_attribute("motion_blur_intensity", "0.0")
        sensor = env.world.spawn_actor(blueprint, camera_pose, attach_to=env.ego,
                                       attachment_type=carla.AttachmentType.Rigid)
        inbox = queue.Queue(); sensor.listen(inbox.put)
        env.actors.append(sensor); cameras.append(sensor); inboxes.append(inbox)
    collisions = []
    collision = env.world.spawn_actor(library.find("sensor.other.collision"), carla.Transform(), attach_to=env.ego)

    def collided(event):
        impulse = event.normal_impulse
        collisions.append({"frame": event.frame, "timestamp": event.timestamp,
                           "other_actor": event.other_actor.type_id,
                           "impulse": math.sqrt(impulse.x ** 2 + impulse.y ** 2 + impulse.z ** 2)})

    collision.listen(collided); env.actors.append(collision)
    shots = ShotCameras(env, out) if args.directed else None
    # CARLA writes this on the server, under a directory writable by its user.
    out.chmod(0o777)
    recorder_path = str((out / "world-recorder.log").resolve())
    recorder_result = env.client.start_recorder(recorder_path, True)
    config = {**vars(args), "fps": 20, "width": 1248, "height": 960,
              "checkpoint_sha256": sha(args.checkpoint), "checkpoint_step": saved["step"],
              "route": route_metadata(route), "livery_revision": manifest["revision"], "livery_layout": manifest["layoutVersion"],
              "camera_relative_matrix": camera_pose.get_matrix(), "fov_degrees": 65,
              "vehicle_blueprint": env.ego.type_id,
              "ego_actor_id": env.ego.id, "world_recorder": recorder_path,
              "recorder_start_result": recorder_result, "recorder_additional_data": True,
              "vehicle_bounds": {"location": [getattr(env.ego.bounding_box.location, k) for k in "xyz"],
                                 "extent": [getattr(env.ego.bounding_box.extent, k) for k in "xyz"]},
              "steer_gain": 1.7, "claim": "Fly learns when to indicate from structured navigation. " +
              ("CARLA BasicAgent drives the route; the fly controls the real indicator stalk." if args.mode == "indicators" else
               "A conventional route controller requests steering angles; one connectome commands both forelegs, and measured wheel/stalk positions alone supply steering/signalling. Speed is scripted."),
              "clock": "Neural state commands the next 50ms of fly motion. Current measured controls are held in CARLA over the same interval; both simulations are captured at its endpoint.",
              "source_sha256": {s: sha(s) for s in [__file__, "src/flyhard/cockpit.py", "src/flyhard/stalk.py", "src/flyhard/roundabout.py", "src/flyhard/indicator_policy.py"]}}
    (out / "config.json").write_text(json.dumps(config, indent=2))
    frames, body, activity, contexts, requests = [], [], [], [], []
    start_timestamp = env.world.get_snapshot().timestamp.elapsed_seconds
    started = time.perf_counter()
    writer = imageio.get_writer(out / "carla-camera.mp4", fps=20, codec="libx264", macro_block_size=1,
                                ffmpeg_params=["-crf", "15", "-preset", "fast"])
    try:
        for i in range(round(args.seconds / DT)):
            if shots:
                shots.advance(i * DT)
            context, annotation = env.observe()
            navigator = agent.run_step()
            request = float(np.clip(navigator.steer / 1.7, -.45, .45))
            if args.erratic:
                request = float(np.clip(request + args.erratic * (math.sin(i * DT * 3.5) + .45 * math.sin(i * DT * 8.1)), -.45, .45))
            with torch.no_grad():
                action, state = policy(torch.tensor(encode_context(context, request)[None], device="cuda"), return_state=True)
            command = action[0].cpu().numpy()
            applied_wheel, applied_signal = rig.angle, rig.stalk.signal
            light_bits = set_signal(env.ego, applied_signal)
            steer = float(np.clip(applied_wheel * 1.7, -.85, .85))
            if args.mode == "combined":
                speed_error = args.speed / 3.6 - context[5]
                throttle = float(np.clip(.3 + .18 * speed_error, 0., 1.))
                brake = float(np.clip(-.15 * speed_error, 0., .7)) if speed_error < -1 else 0.
                env.ego.apply_control(carla.VehicleControl(throttle=throttle, brake=brake, steer=steer))
            else:
                env.ego.apply_control(navigator)
                steer = float(navigator.steer)
            for _ in range(10):
                rig.step_both(command)
            frame_id = env.world.tick()
            rgb, depth = [next_image(inbox, frame_id) for inbox in inboxes]
            pixels = np.frombuffer(rgb.raw_data, np.uint8).reshape(960, 1248, 4)[:, :, :3][:, :, ::-1].copy()
            writer.append_data(pixels)
            # Preserve the native depth bytes losslessly for sponsor occlusion.
            dp = np.frombuffer(depth.raw_data, np.uint8).reshape(960, 1248, 4)[:, :, :3][:, :, ::-1].copy()
            Image.fromarray(dp).save(out / "depth" / f"{i:05}.png", compress_level=1)
            if i in [0, 40, 100, 200, 400]:
                Image.fromarray(pixels).save(out / f"carla-preview-{i:04}.png")
            after, score_annotation = env.observe()
            native_light_bits = int(env.ego.get_light_state())
            blinker_mask = int(carla.VehicleLightState.LeftBlinker) | int(carla.VehicleLightState.RightBlinker)
            assert (native_light_bits & blinker_mask) == (light_bits & blinker_mask)
            pose, camera_world = env.ego.get_transform(), cameras[0].get_transform()
            camera_time = rgb.timestamp - start_timestamp
            assert abs(camera_time - rig.data.time) < 1e-4
            record = {"index": i, "carla_frame": frame_id, "depth_frame": depth.frame,
                      "camera_time": camera_time, "body_time": float(rig.data.time), "body_index": i, "neural_index": i,
                      "speed_m_s": float(after[5]), "requested_angle": request, "wheel_angle": rig.angle,
                      "wheel_at_interval_start": applied_wheel, "stalk_angle": rig.stalk.angle,
                      "applied_signal": applied_signal, "signal": rig.stalk.signal, "light_bits": light_bits,
                      "native_light_bits": native_light_bits,
                      "applied_steer": steer, "vehicle_matrix": pose.get_matrix(), "camera_matrix": camera_world.get_matrix(),
                      **score_annotation}
            if shots:
                record['cameras'] = shots.capture(i, frame_id, rgb.timestamp)
            # A readable parallel world trace makes actor/camera auditing easy.
            record['world_vehicles'] = [{'id': actor.id, 'blueprint': actor.type_id,
                'matrix': actor.get_transform().get_matrix(), 'light_bits': int(actor.get_light_state())}
                for actor in [env.ego, *env.traffic] if actor.is_alive]
            frames.append(record)
            body.append({"time": float(rig.data.time), "qpos": rig.data.qpos.copy(), "qvel": rig.data.qvel.copy(),
                         "ctrl": rig.data.ctrl.copy(), "decision_index": i})
            activity.append(state[:, 0].cpu().numpy()); contexts.append(context); requests.append(request)
            with (out / "frames.jsonl").open("a") as f:
                f.write(json.dumps(record) + "\n")
            if i % 100 == 0:
                print(json.dumps({"frame": i, "speed_kmh": float(after[5] * 3.6), "progress": score_annotation["progress"],
                                  "signal": rig.stalk.signal, "collisions": len(collisions)}), flush=True)
            if score_annotation["progress"] >= route["length"] - 3:
                break
    finally:
        writer.close()
        if shots:
            shots.close()
        env.client.stop_recorder()
        (out / 'recorder-info.txt').write_text(env.client.show_recorder_file_info(recorder_path, False))
        (out / "collisions.json").write_text(json.dumps(collisions, indent=2))
        (out / "frames.json").write_text(json.dumps(frames, indent=2))
        if body:
            np.savez_compressed(out / "body-trace.npz", **{k: np.array([b[k] for b in body]) for k in body[0]})
            np.savez_compressed(out / "neural-trace.npz", time=np.arange(len(activity)) * DT,
                                activity=np.array(activity), requested_angle=requests, context=contexts)
        env.close()
    metrics = {"status": "capture_complete", "frames": len(frames), "duration_seconds": len(frames) * DT,
               "same_episode": True, "native_camera_depth_frame_matches": all(f["carla_frame"] == f["depth_frame"] for f in frames),
               "max_clock_error_seconds": max(abs(f["body_time"] - f["camera_time"]) for f in frames),
               "collision_events": len(collisions), "peak_speed_kmh": max(f["speed_m_s"] * 3.6 for f in frames),
               "score": score_signals([f["progress"] for f in frames], [f["applied_signal"] for f in frames], route),
               "wall_seconds": time.perf_counter() - started}
    assert Path(recorder_path).is_file() and Path(recorder_path).stat().st_size > 1000
    metrics['recorder_bytes'] = Path(recorder_path).stat().st_size
    metrics['recorder_sha256'] = sha(recorder_path)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2)); print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
