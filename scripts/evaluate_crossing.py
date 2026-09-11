#!/usr/bin/env python3
"""Native CARLA held-out trials for the pedestrian crossing, through measured pedals.

The learned policy chooses throttle and brake only. Offline IK drives the fly's
legs onto the pedals and CARLA receives the measured travel, never the demand.
Steering is a conventional lane-keeping request and is recorded as such.

With --record, each trial also writes wide/chase/cabin footage and registers a
take in the clip library, so one CARLA pass yields both the benchmark and the
film material.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from flyhard.clips import ClipLibrary, Take
from flyhard.crossing import FRONT_OVERHANG, cases, encode, metrics


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_policy(checkpoint, graph_dir, reset_core=False):
    from flyhard.crossing_policy import CrossingPolicy
    with gzip.open(checkpoint, 'rb') as handle:
        saved = torch.load(handle, map_location='cpu', weights_only=False)
    if sha(Path(graph_dir)/'graph.npz') != saved['config']['graph_sha256']:
        raise RuntimeError('Graph identity mismatch')
    state = saved['model']
    policy = CrossingPolicy(np.load(Path(graph_dir)/'graph.npz'), state['sensory_ids'],
                            state['motor_ids'], saved['config']['seed'])
    missing, extra = policy.load_state_dict(state, strict=False)
    assert set(missing) == {'core.crow', 'core.col', 'core.rows', 'core.base'} and not extra
    if reset_core:
        with torch.no_grad():
            policy.core.edge_gain.zero_()
            policy.core.leak.zero_()
    return policy.cuda().eval(), saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--graph', default='data/graph-traced-v1')
    parser.add_argument('--split', default='heldout')
    parser.add_argument('--count', type=int, default=8)
    parser.add_argument('--seconds', type=float, default=22.)
    parser.add_argument('--town', default='Town05')
    parser.add_argument('--record', help='Clip library root; records three camera angles per trial')
    parser.add_argument('--reset-core', action='store_true',
                        help='Zero the learned core as a control condition')
    parser.add_argument('--label', default='')
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    policy, saved = load_policy(args.checkpoint, args.graph, args.reset_core)

    from flyhard.crossing_world import CrossingWorld
    from flyhard.parking_rig import make_parking_rig
    env = CrossingWorld(town=args.town)
    rig = make_parking_rig()
    rig.prepare_controls()
    library = ClipLibrary(args.record) if args.record else None
    results = []
    try:
        (out/'site.json').write_text(json.dumps(env.metadata(), indent=2)+'\n')
        print(json.dumps({'site': env.metadata()}), flush=True)
        for case in cases(args.split, args.count):
            env.start(case)
            rig.reset()
            cameras = None
            if library:
                take_dir = library.root/'crossing'/'pending'/f'crossing-s{case.seed:05d}-a01'
                take_dir.mkdir(parents=True, exist_ok=True)
                from flyhard.scenario_cameras import ScenarioCameras
                cameras = ScenarioCameras(env, take_dir, env.site['centre'], env.approach_yaw)
            env.release()
            throttle = brake = 0.
            rows, trajectory, activity = [], [], []
            started = env.world.get_snapshot().timestamp.elapsed_seconds
            for step in range(round(args.seconds/.05)):
                now = env.world.get_snapshot().timestamp.elapsed_seconds-started
                pedestrian_y, lateral_speed, walking = env.step_walker(now)
                observation = env.observe(pedestrian_y, lateral_speed, throttle, brake)
                with torch.no_grad():
                    output, neural = policy(torch.tensor(encode(observation), device='cuda'),
                                            return_state=True)
                demand = output[0].cpu().numpy()
                activity.append(neural[:, 0].cpu().numpy().astype(np.float16))
                steer = env.lane_steer()
                # Offline IK presses the pedals; CARLA gets the measured travel only.
                targets = rig.diagnostic_drive_action(steer/.5, float(demand[0]), float(demand[1]), 1)
                for _ in range(10):
                    rig.step_drive(targets)
                measured = rig.parking.measured
                throttle, brake = measured['throttle'], measured['brake']
                env.apply_measured(throttle, brake, steer)
                frame = env.world.tick()
                state = env.scenario_state()
                if cameras:
                    snapshot = env.world.get_snapshot()
                    cameras.capture(step, frame, snapshot.timestamp.elapsed_seconds)
                trajectory.append({'state': state.copy(), 'pedestrian_y': pedestrian_y,
                                   'walking': walking})
                rows.append({'time': (step+1)*.05, 'carla_frame': frame,
                             'vehicle_matrix': env.ego.get_transform().get_matrix(),
                             'neural_index': len(activity)-1,
                             'observation': observation.tolist(),
                             'demand_throttle': float(demand[0]), 'demand_brake': float(demand[1]),
                             'measured_throttle': throttle, 'measured_brake': brake,
                             'lane_steer_request': steer,
                             'front_to_line': float(state[0]+FRONT_OVERHANG),
                             'speed_m_s': float(state[1]), 'pedestrian_y': float(pedestrian_y),
                             'pedestrian_walking': bool(walking)})
                if env.collision_events:
                    break
                if state[0]+FRONT_OVERHANG > case.walk_offset+14.:
                    break
            score = metrics(trajectory, case)
            score['native_collision_events'] = list(env.collision_events)
            score['contact'] = bool(score['contact'] or env.collision_events)
            score['passed'] = bool(score['passed'] and not env.collision_events)
            duration = rows[-1]['time']
            results.append({'seed': case.seed, 'split': case.split, 'duration_seconds': duration, **score})
            print(json.dumps({'seed': case.seed, 'passed': score['passed'],
                              'stop_required': score['stop_required'], 'contact': score['contact'],
                              'yielded': score['yielded_before_line'],
                              'unnecessary_stop': score['unnecessary_stop']}), flush=True)

            trial = out/str(case.seed)
            trial.mkdir()
            box = env.ego.bounding_box
            (trial/'config.json').write_text(json.dumps(
                {'fps': 20, 'policy_hz': 20, 'case': case.record(), **env.metadata(),
                 'vehicle_bounds': {'location': [box.location.x, box.location.y, box.location.z],
                                    'extent': [box.extent.x, box.extent.y, box.extent.z]},
                 'motion': 'Measured pedal travel drives CARLA; offline IK moves the fly legs. '
                           'Steering is a conventional lane-keeping request, not a learned output.'},
                indent=2)+'\n')
            (trial/'trace.json').write_text(json.dumps(rows)+'\n')
            np.savez_compressed(trial/'neural.npz', activity=np.asarray(activity))

            if cameras:
                cameras.close()
                outcome = 'success' if score['passed'] else 'failure'
                take = Take(scenario='crossing', seed=case.seed, attempt=1, outcome=outcome,
                            duration_seconds=duration, fps=20, cameras=cameras.relative_paths(),
                            metrics={k: v for k, v in score.items() if k != 'native_collision_events'},
                            label=args.label or ('yielded to pedestrian' if score['yielded_before_line']
                                                 else 'drove through' if not score['stop_required']
                                                 else 'did not yield'),
                            checkpoint_sha256=sha(args.checkpoint))
                final = library.directory(take)
                final.parent.mkdir(parents=True, exist_ok=True)
                if final.exists():
                    import shutil
                    shutil.rmtree(final)
                take_dir.rename(final)
                library.register(take)
    finally:
        env.close()

    passed = sum(r['passed'] for r in results)
    required = [r for r in results if r['stop_required']]
    summary = {'checkpoint': args.checkpoint, 'checkpoint_sha256': sha(args.checkpoint),
               'split': args.split, 'trials': len(results), 'passed': passed,
               'pass_rate': round(passed/max(len(results), 1), 4),
               'contacts': sum(r['contact'] for r in results),
               'entered_on_pedestrian': sum(r['entered_on_pedestrian'] for r in results),
               'stop_required_trials': len(required),
               'yielded_when_required': sum(r['yielded_before_line'] for r in required),
               'unnecessary_stops': sum(r['unnecessary_stop'] for r in results),
               'reset_core': args.reset_core, 'results': results,
               'environment': 'native CARLA with measured pedal travel',
               'claim': 'Scoped pedestrian-crossing benchmark on frozen held-out cases. '
                        'Not general autonomous driving, and steering is not learned.'}
    (out/'metrics.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}, indent=2), flush=True)
    if library:
        library.index()


if __name__ == '__main__':
    main()
