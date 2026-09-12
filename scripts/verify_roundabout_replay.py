#!/usr/bin/env python3
"""Load the saved CARLA world log and compare its ego trajectory to capture."""
import argparse
import json
from pathlib import Path
import time

import carla
import numpy as np


def main():
    p = argparse.ArgumentParser(); p.add_argument('--run', required=True)
    args = p.parse_args(); root = Path(args.run)
    frames = json.loads((root / 'frames.json').read_text())
    recorded = np.asarray([f['vehicle_matrix'] for f in frames])[:, :3, 3]
    client = carla.Client('127.0.0.1', 2000); client.set_timeout(60)
    world = client.get_world(); original = world.get_settings()
    settings = world.get_settings(); settings.synchronous_mode = True
    settings.fixed_delta_seconds = .05; settings.no_rendering_mode = True
    world.apply_settings(settings)
    observed, light_states = [], []
    started = time.perf_counter()
    try:
        response = client.replay_file(str((root / 'world-recorder.log').resolve()), 0., 0., 0, False)
        for _ in range(len(frames)):
            world.tick()
            cars = [a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name') == 'hero']
            if not cars:
                continue
            assert len(cars) == 1
            pose = cars[0].get_transform().location
            observed.append([pose.x, pose.y, pose.z]); light_states.append(int(cars[0].get_light_state()))
        distances = np.linalg.norm(np.asarray(observed)[:, None, :] - recorded[None, :, :], axis=2)
        nearest = distances.argmin(axis=1); errors = distances.min(axis=1)
        # Ignore initialization and the final replayer-to-autopilot boundary.
        interior = (nearest >= 5) & (nearest < len(frames)-5)
        result = {'status': 'verified' if interior.sum() > 20 and np.quantile(errors[interior], .99) < .03 else 'needs_review',
                  'response': response, 'samples': len(observed), 'matched_samples': int(interior.sum()),
                  'median_position_error_m': float(np.median(errors[interior])),
                  'p99_position_error_m': float(np.quantile(errors[interior], .99)),
                  'maximum_position_error_m': float(errors[interior].max()),
                  'matched_source_indices': nearest.tolist(), 'observed_positions': observed,
                  'observed_light_states': light_states, 'wall_seconds': time.perf_counter()-started}
        (root / 'replay-verification.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({k: v for k, v in result.items() if not isinstance(v, list)}, indent=2))
        assert result['status'] == 'verified'
    finally:
        client.stop_replayer(False)
        for actor in world.get_actors().filter('vehicle.*'):
            actor.destroy()
        world.apply_settings(original)


if __name__ == '__main__':
    main()
