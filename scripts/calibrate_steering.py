#!/usr/bin/env python3
"""Measure how the car actually turns at motorway speed, and fit the model to it.

The bicycle model's curvature is not the car's curvature: tyre slip, weight transfer
and CARLA's own steering curve all sit in between. The three-point turn needed this
correction at parking speed and there is no reason the same number holds at twenty
metres a second, so it is measured here rather than carried over.

Writes work/steering-calibration.json. flyhard.overtake.STEER_RATIO should match it.
"""
import argparse
import json
import math
from pathlib import Path

import carla
import numpy as np

from flyhard.overtake import MAX_STEER_DEG, WHEELBASE


def settle(world, vehicle, speed, seconds=2.5, dt=1/60):
    forward = vehicle.get_transform().get_forward_vector()
    vehicle.set_target_velocity(forward*speed)
    for _ in range(int(seconds/dt)):
        vehicle.apply_control(carla.VehicleControl(throttle=.6, steer=0.))
        world.tick()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='work/steering-calibration.json')
    parser.add_argument('--town', default='Town04')
    parser.add_argument('--speeds', default='12,20')
    parser.add_argument('--steers', default='0.04,0.08,0.15,0.25')
    args = parser.parse_args()

    from flyhard.overtake_world import OvertakeWorld
    env = OvertakeWorld(town=args.town)
    dt = env.dt
    measurements = []
    try:
        library = env.world.get_blueprint_library()
        blueprint = library.find('vehicle.mini.cooper_s_2021')
        blueprint.set_attribute('role_name', 'calibration')
        for speed in [float(v) for v in args.speeds.split(',')]:
            for steer in [float(v) for v in args.steers.split(',')]:
                vehicle = env.world.spawn_actor(blueprint, env.place(2., 0.))
                try:
                    settle(env.world, vehicle, speed)
                    start_yaw = vehicle.get_transform().rotation.yaw
                    held = 1.4
                    travelled = 0.
                    for _ in range(int(held/dt)):
                        vehicle.apply_control(carla.VehicleControl(throttle=.6, steer=steer))
                        env.world.tick()
                        travelled += vehicle.get_velocity().length()*dt
                    turned = math.radians((vehicle.get_transform().rotation.yaw-start_yaw+180)
                                          % 360-180)
                    measured_curvature = abs(turned)/max(travelled, 1e-6)
                    model_curvature = abs(math.tan(math.radians(MAX_STEER_DEG*steer)))/WHEELBASE
                    measurements.append({
                        'speed_target': speed, 'steer': steer,
                        'mean_speed': round(travelled/held, 3),
                        'yaw_change_rad': round(turned, 5),
                        'measured_curvature': round(measured_curvature, 6),
                        'model_curvature': round(model_curvature, 6),
                        'ratio': round(measured_curvature/max(model_curvature, 1e-9), 4)})
                    print(json.dumps(measurements[-1]), flush=True)
                finally:
                    vehicle.destroy()
    finally:
        env.close()

    usable = [m for m in measurements if m['mean_speed'] > 3. and m['steer'] >= .08]
    ratio = float(np.median([m['ratio'] for m in usable])) if usable else float('nan')
    receipt = {'map': args.town, 'vehicle': 'vehicle.mini.cooper_s_2021',
               'max_steer_angle_deg': MAX_STEER_DEG, 'wheelbase_m': WHEELBASE,
               'steer_ratio': round(ratio, 4), 'measurements': measurements,
               'note': 'Ratio of the curvature the car actually follows to the bicycle '
                       'model prediction, measured at motorway speed. Small steer angles '
                       'are excluded because yaw noise dominates them.'}
    Path(args.out).write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'steer_ratio': receipt['steer_ratio'], 'samples': len(usable)}, indent=2))


if __name__ == '__main__':
    main()
