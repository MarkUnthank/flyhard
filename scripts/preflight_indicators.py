#!/usr/bin/env python3
"""Record native CARLA lamp behavior before implementing a learned indicator skill.

This is an explicitly scripted infrastructure check. It contains no fly policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import queue
import time

import carla
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def camera_frame(inbox, tick):
    frame = inbox.get(timeout=30)
    while frame.frame < tick:
        frame = inbox.get(timeout=30)
    if frame.frame != tick:
        raise RuntimeError(f"Camera frame {frame.frame} differs from world frame {tick}")
    rgb = np.frombuffer(frame.raw_data, np.uint8).reshape(frame.height, frame.width, 4)
    return frame, rgb[:, :, :3][:, :, ::-1].copy()


def font(size):
    for path in (Path("assets/fonts/Geist-Regular.ttf"),
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="runs/indicators-preflight-v1")
    parser.add_argument("--vehicle", default="vehicle.mini.cooper_s_2021")
    parser.add_argument("--map", default="Town03")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "trace.json").exists():
        raise FileExistsError("Use a new output directory for each preflight")
    client = carla.Client("127.0.0.1", 2000)
    client.set_timeout(90)
    maps = client.get_available_maps()
    requested = next((m for m in maps if m.rsplit("/", 1)[-1] == args.map), None)
    world = client.get_world()
    if requested and world.get_map().name != requested:
        world = client.load_world(requested)
    original_settings = world.get_settings()
    original_weather = world.get_weather()
    actors = []
    config = {
        "claim": "Scripted lamp infrastructure check; no fly or neural controller.",
        "vehicle": args.vehicle, "requested_map": args.map, "available_maps": maps,
        "map": world.get_map().name, "version": client.get_server_version(),
        "fixed_delta_seconds": 0.05, "frames_per_phase": 60,
        "phases": ["off", "left", "right", "cancelled"],
        "automatic_route_lights": False,
        "sponsor_livery_applied": False,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 0.05
        settings.no_rendering_mode = False
        settings.substepping = True
        settings.max_substep_delta_time = 0.01
        settings.max_substeps = 5
        world.apply_settings(settings)
        weather = carla.WeatherParameters.ClearNoon
        weather.sun_altitude_angle = 30
        world.set_weather(weather)
        library = world.get_blueprint_library()
        names_before = set(world.get_names_of_all_objects())
        blueprint = library.find(args.vehicle)
        if blueprint.has_attribute("color"):
            blueprint.set_attribute("color", "48,84,43")
        blueprint.set_attribute("role_name", "flyhard_indicator_preflight")
        vehicle = None
        for pose in world.get_map().get_spawn_points():
            vehicle = world.try_spawn_actor(blueprint, pose)
            if vehicle:
                break
        if vehicle is None:
            raise RuntimeError("No clear spawn position")
        actors.append(vehicle)
        vehicle.set_autopilot(False)
        vehicle.apply_control(carla.VehicleControl(brake=1, hand_brake=True))
        world.tick()
        names_after = set(world.get_names_of_all_objects())
        (out / "texture-object-inventory.json").write_text(json.dumps({
            "new_object_names_after_vehicle_spawn": sorted(names_after - names_before),
            "mini_matching_names": sorted(n for n in names_after if "mini" in n.lower() or "cooper" in n.lower()),
            "total_named_objects": len(names_after),
            "note": "An object name is not proof that independent sponsor UV surfaces can be applied.",
        }, indent=2) + "\n")
        cameras = []
        for name, transform in [
            ("rear", carla.Transform(carla.Location(x=-6, z=1.7), carla.Rotation(pitch=-6))),
            ("front", carla.Transform(carla.Location(x=6, z=1.7), carla.Rotation(pitch=-6, yaw=180))),
        ]:
            bp = library.find("sensor.camera.rgb")
            for key, value in {"image_size_x": "640", "image_size_y": "480", "fov": "55", "sensor_tick": "0"}.items():
                bp.set_attribute(key, value)
            sensor = world.spawn_actor(bp, transform, attach_to=vehicle)
            actors.append(sensor)
            inbox = queue.Queue()
            sensor.listen(inbox.put)
            cameras.append((name, inbox))
        for _ in range(30):
            tick = world.tick()
            for _, inbox in cameras:
                camera_frame(inbox, tick)
        states = [carla.VehicleLightState.NONE, carla.VehicleLightState.LeftBlinker,
                  carla.VehicleLightState.RightBlinker, carla.VehicleLightState.NONE]
        trace, phase_ranges, strips = [], {}, []
        first_baseline = None
        start = time.perf_counter()
        with imageio.get_writer(out / "indicator-lamps.mp4", fps=20, quality=8, macro_block_size=1) as writer:
            for phase, state in zip(config["phases"], states):
                vehicle.set_light_state(state)
                rear_sequence, peak_score, peak_canvas = [], -1, None
                for index in range(config["frames_per_phase"]):
                    tick = world.tick()
                    samples = [camera_frame(inbox, tick) for _, inbox in cameras]
                    actual_state = int(vehicle.get_light_state())
                    if actual_state != int(state):
                        raise AssertionError(f"Requested {int(state)}, received {actual_state}")
                    rear = samples[0][1]
                    rear_sequence.append(rear)
                    if first_baseline is None:
                        first_baseline = rear.astype(np.float32)
                    canvas = Image.new("RGB", (1280, 720), "#000000")
                    draw = ImageDraw.Draw(canvas)
                    draw.text((32, 24), "Indicator camera test", font=font(30), fill="white")
                    draw.text((32, 69), "Scripted inputs / parked car / no fly controller", font=font(18), fill="#aaa")
                    for col, ((name, _), (_, rgb)) in enumerate(zip(cameras, samples)):
                        canvas.paste(Image.fromarray(rgb), (640 * col, 120))
                        draw.text((640 * col + 24, 128), name.upper(), font=font(20), fill="white", stroke_width=1, stroke_fill="black")
                    draw.text((32, 623), "REQUEST LEFT", font=font(23), fill="white" if phase == "left" else "#555")
                    draw.text((300, 623), "REQUEST RIGHT", font=font(23), fill="white" if phase == "right" else "#555")
                    draw.text((635, 623), "LAMPS: " + phase.upper(), font=font(23), fill="white")
                    draw.text((1000, 623), "STEERING 0.0°", font=font(23), fill="white")
                    draw.text((32, 673), f"{world.get_map().name.rsplit('/', 1)[-1]}  /  frame {tick}  /  native CARLA lamps", font=font(18), fill="#999")
                    writer.append_data(np.asarray(canvas))
                    score = float(np.abs(rear.astype(np.float32) - first_baseline)[140:380, 160:480].mean())
                    if score > peak_score:
                        peak_score, peak_canvas = score, canvas.copy()
                    trace.append({
                        "phase": phase, "phase_frame": index, "world_frame": tick,
                        "camera_frames": {name: frame.frame for (name, _), (frame, _) in zip(cameras, samples)},
                        "time": samples[0][0].timestamp, "requested_light_flags": int(state),
                        "measured_light_flags": actual_state, "applied_steer": float(vehicle.get_control().steer),
                        "rear_delta_from_initial_mean": score,
                    })
                stack = np.stack(rear_sequence).astype(np.int16)
                temporal_range = (stack.max(axis=0) - stack.min(axis=0)).astype(np.uint8)
                Image.fromarray(temporal_range).save(out / f"{phase}-temporal-range.png")
                peak_canvas.save(out / f"{phase}-preview.png")
                strips.append(peak_canvas.resize((640, 360)))
                phase_ranges[phase] = {
                    "max_delta_from_initial_mean": peak_score,
                    "temporal_range_mean": float(temporal_range.mean()),
                    "visually_verified": False,
                }
        sheet = Image.new("RGB", (1280, 720))
        for i, frame in enumerate(strips):
            sheet.paste(frame, (i % 2 * 640, i // 2 * 360))
        sheet.save(out / "contact-sheet.png")
        (out / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
        metrics = {**config, "status": "api_and_capture_passed", "matching_camera_pairs": len(trace),
                   "wall_seconds": time.perf_counter() - start, "phase_metrics": phase_ranges,
                   "visual_review_required": True}
        (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        print(json.dumps(metrics, indent=2))
    finally:
        for actor in reversed(actors):
            try:
                if isinstance(actor, carla.Sensor):
                    actor.stop()
                actor.destroy()
            except RuntimeError:
                pass
        world.apply_settings(original_settings)
        world.set_weather(original_weather)


if __name__ == "__main__":
    main()
