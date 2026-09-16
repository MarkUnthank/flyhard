#!/usr/bin/env python3
"""Capture native billboard/sponsor proof from an owned CARLA test server.

This validates the model integration, not the fly's driving policy. RGB and
depth come directly from CARLA; no Blender sponsor layer is composited here.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import queue

import carla
import numpy as np

from flyhard.live_livery import verify_live_livery
from flyhard.native_livery import attach_livery, attachment_errors


def image_for(inbox, frame):
    while True:
        image = inbox.get(timeout=60)
        if image.frame >= frame:
            if image.frame != frame:
                raise RuntimeError('Native camera and world frames diverged')
            return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=2000)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--import-receipt', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--runtime-mode', choices=['editor', 'shipping'], default='editor')
    parser.add_argument('--runtime-manifest', type=Path)
    parser.add_argument('--runtime-manifest-sha256')
    args = parser.parse_args()
    runtime_digest = None
    if args.runtime_mode == 'shipping':
        if not args.runtime_manifest or not args.runtime_manifest_sha256:
            parser.error('Shipping proof requires the selected runtime manifest and its expected SHA-256')
        runtime_digest = hashlib.sha256(args.runtime_manifest.read_bytes()).hexdigest()
        if runtime_digest != args.runtime_manifest_sha256:
            raise RuntimeError('Selected runtime manifest checksum mismatch')
    elif args.runtime_manifest or args.runtime_manifest_sha256:
        parser.error('A runtime manifest is only applicable to Shipping proof')
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = verify_live_livery(args.asset, args.out)
    client = carla.Client(args.host, args.port)
    client.set_timeout(120)
    world = client.get_world()
    if world.get_map().name.rsplit('/', 1)[-1] != 'Town03':
        raise RuntimeError('Native verification requires Town03; check the server map argument order')
    if world.get_actors().filter('vehicle.*'):
        raise RuntimeError('Use an owned empty CARLA test server for native verification')
    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 1 / 60
    settings.substepping = True
    settings.max_substep_delta_time = 1 / 120
    settings.max_substeps = 2
    world.apply_settings(settings)
    world.set_weather(carla.WeatherParameters.ClearNoon)
    actors, sensors, native = [], [], []
    traces, comparisons = [], []
    try:
        blueprint = world.get_blueprint_library().find('vehicle.mini.cooper_s_2021')
        blueprint.set_attribute('role_name', 'flyhard_native_validation')
        spawn = world.get_map().get_spawn_points()[0]
        car = world.spawn_actor(blueprint, spawn)
        actors.append(car)
        car.apply_control(carla.VehicleControl(brake=1))
        for _ in range(120):
            world.tick()
        physics_before = str(car.get_physics_control())
        # Long side views and front/rear obliques reveal both billboard faces,
        # the mounts, the left-door placement and rear sponsor artwork.
        poses = {
            'left-door': ((0, -5.8, 2.2), (-9, 90, 0)),
            'right-billboard': ((0, 5.8, 2.2), (-9, -90, 0)),
            'rear': ((-5.8, -2.5, 2.9), (-15, 23, 0)),
            'front-roof': ((5.8, 2.5, 3.4), (-20, -157, 0)),
        }
        streams = []
        for name, (xyz, rotation) in poses.items():
            pose = carla.Transform(carla.Location(*xyz), carla.Rotation(*rotation))
            for kind in ['rgb', 'depth']:
                camera_bp = world.get_blueprint_library().find('sensor.camera.' + kind)
                camera_bp.set_attribute('image_size_x', '1280')
                camera_bp.set_attribute('image_size_y', '720')
                camera_bp.set_attribute('fov', '60')
                camera = world.spawn_actor(camera_bp, pose, attach_to=car,
                                          attachment_type=carla.AttachmentType.Rigid)
                inbox = queue.Queue()
                camera.listen(inbox.put)
                sensors.append(camera)
                streams.append((name, kind, inbox))
        baseline = {}
        for phase in ['stock', 'native']:
            if phase == 'native':
                native, offset = attach_livery(world, car, args.asset, args.import_receipt)
                actors.extend(native)
            for _ in range(30):
                frame = world.tick()
                for name, kind, inbox in streams:
                    image = image_for(inbox, frame)
            # Capture all camera channels from one synchronized world tick.
            frame = world.tick()
            for name, kind, inbox in streams:
                image = image_for(inbox, frame)
                image.save_to_disk(str(args.out / f'{phase}-{name}-{kind}.png'))
                pixels = np.frombuffer(image.raw_data, dtype=np.uint8).copy()
                if phase == 'stock':
                    baseline[(name, kind)] = pixels
                else:
                    changed = np.any(pixels.reshape(-1, 4) != baseline[(name, kind)].reshape(-1, 4), axis=1)
                    comparisons.append({'view': name, 'sensor': kind,
                                        'changed_pixel_fraction': float(changed.mean()), 'carla_frame': frame})
        for sensor in sensors:
            sensor.stop()
            sensor.destroy()
        sensors.clear()
        physics_after = str(car.get_physics_control())
        if physics_before != physics_after:
            raise RuntimeError('Native accessories changed vehicle physics configuration')
        for index in range(600):
            t = index / 60
            control = carla.VehicleControl(throttle=0.4 if t < 7 else 0,
                                          brake=0.7 if t >= 7 else 0,
                                          steer=0.35 * math.sin(t * 1.5))
            car.apply_control(control)
            car.set_light_state(carla.VehicleLightState.LeftBlinker if t < 5
                                else carla.VehicleLightState.RightBlinker)
            frame = world.tick()
            errors = attachment_errors(car, native, offset)
            velocity = car.get_velocity()
            record = {'frame': frame, 'time': t, 'vehicle_matrix': car.get_transform().get_matrix(),
                      'speed_m_s': math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2),
                      'steer': control.steer, 'brake': control.brake, 'accessories': errors}
            traces.append(record)
            with (args.out / 'native-motion.jsonl').open('a') as file:
                file.write(json.dumps(record) + '\n')
            if any(x['position_error_metres'] > 0.002 or x['rotation_matrix_error'] > 0.0002 for x in errors):
                raise RuntimeError('Native accessories drifted from the vehicle')
        result = {'status': 'automated_checks_passed',
                  'verification_scope': 'Visual review and runtime release promotion are separate gates',
                  'runtime_mode': args.runtime_mode,
                  'runtime_manifest_sha256': runtime_digest,
                  'carla_server_version': client.get_server_version(),
                  'carla_client_version': client.get_client_version(),
                  'map': world.get_map().name,
                  'revision': manifest['revision'], 'layout': manifest['layoutVersion'],
                  'import_receipt_sha256': hashlib.sha256(Path(args.import_receipt).read_bytes()).hexdigest(),
                  'native_actor_count': len(native), 'physics_configuration_unchanged': True,
                  'peak_speed_m_s': max(x['speed_m_s'] for x in traces),
                  'max_attachment_position_error_m': max(
                      a['position_error_metres'] for x in traces for a in x['accessories']),
                  'max_attachment_rotation_error': max(
                      a['rotation_matrix_error'] for x in traces for a in x['accessories']),
                  'camera_comparisons': comparisons,
                  'claim': 'Native CARLA model validation; no driving-policy evaluation in this run'}
        if result['peak_speed_m_s'] < 1:
            raise RuntimeError('Vehicle did not move enough to validate attachment')
        if any(x['changed_pixel_fraction'] <= 0 for x in comparisons):
            raise RuntimeError('A native camera view did not change from the stock vehicle')
        (args.out / 'native-proof.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    finally:
        for sensor in reversed(sensors):
            sensor.stop()
            sensor.destroy()
        for actor in reversed(actors):
            actor.destroy()
        world.apply_settings(original_settings)


if __name__ == '__main__':
    main()
