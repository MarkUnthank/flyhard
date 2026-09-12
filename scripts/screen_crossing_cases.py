#!/usr/bin/env python3
"""Roll the trained policy through every held-out crossing case, without CARLA.

Recording a case in the simulator costs minutes and a gigabyte; finding out what the
policy does in it costs a second. The scenario carries the same longitudinal model
used to build its training data, so the whole held-out split can be rolled out here
and only the interesting case need ever reach CARLA.

Every case steps in lockstep as one batch, because the policy settles from rest on
each control step rather than carrying state between them, so thirty-two cases cost
one forward pass per step rather than thirty-two.

This is the training diagnostic, not the simulator. It has no steering, no body rig
and no contact physics, so it says which case is worth recording, never what the
recorded take will score.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

CONTROL_DT = .05


def rollout(policy, core, cases, seconds, device='cuda'):
    """Step every case together. Returns one trajectory per case."""
    steps = round(seconds/CONTROL_DT)
    states = np.array([case.start for case in cases], float)
    triggered = [None]*len(cases)
    throttle = np.zeros(len(cases))
    brake = np.zeros(len(cases))
    trajectories = [[] for _ in cases]
    for step in range(steps):
        now = step*CONTROL_DT
        walkers = [core.pedestrian_state(case, triggered[i], now)
                   for i, case in enumerate(cases)]
        observations = np.stack([
            core.observation(states[i], case, walkers[i][0], walkers[i][1],
                             throttle[i], brake[i])
            for i, case in enumerate(cases)])
        for i, case in enumerate(cases):
            trajectories[i].append({'time': now, 'state': states[i].copy(),
                                    'pedestrian_y': float(walkers[i][0]),
                                    'walking': bool(walkers[i][2]),
                                    'throttle': float(throttle[i]),
                                    'brake': float(brake[i])})
        with torch.no_grad():
            demand = policy(torch.tensor(core.encode(observations.astype(np.float32)),
                                         device=device)).cpu().numpy()
        throttle = np.clip(demand[:, 0], 0., 1.)
        brake = np.clip(demand[:, 1], 0., 1.)
        for i, case in enumerate(cases):
            states[i] = core.kinematic_step(states[i], throttle[i], brake[i], CONTROL_DT)
            # The pedestrian steps out once the car's front bumper is inside the
            # trigger distance, which is how the world does it too.
            if triggered[i] is None:
                front = -(states[i][0]+core.FRONT_OVERHANG)
                if front <= case.trigger_distance:
                    triggered[i] = now
    return trajectories


def describe(case, score, trajectory):
    """A line a person can choose from, rather than a row of booleans."""
    speeds = [row['state'][1] for row in trajectory]
    slowest = min(speeds)
    if score['contact']:
        return 'HITS THE PEDESTRIAN'
    if score['entered_on_pedestrian']:
        return 'drives into the occupied crossing'
    if score['stopped_in_crossing']:
        return 'stops inside the crossing, on the paint'
    if score['unnecessary_stop']:
        return 'stops dead for nobody'
    if not score['cleared_crossing']:
        return 'stops and never goes again'
    if score['yielded_before_line']:
        gap = score['min_pedestrian_gap_m']
        return f'stops for the pedestrian, closest approach {gap} m'
    if not score['stop_required']:
        return 'drives on, crossing clear'
    return f'slows to {slowest:.1f} m/s and carries on through'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--graph', default='data/graph-traced-v1')
    parser.add_argument('--split', default='heldout')
    parser.add_argument('--count', type=int, default=32)
    parser.add_argument('--seconds', type=float, default=26.)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--out')
    args = parser.parse_args()

    from evaluate_scenario import load_policy
    from flyhard.scenarios import get
    scenario = get('crossing')
    core, _ = scenario.modules
    policy, _ = load_policy(args.checkpoint, args.graph, scenario, core)
    cases = core.cases(args.split, args.count)
    trajectories = rollout(policy, core, cases, args.seconds, args.device)

    report = []
    for index, (case, trajectory) in enumerate(zip(cases, trajectories)):
        score = core.metrics(trajectory, case)
        report.append({'index': index, 'seed': case.seed,
                       'trigger_distance_m': round(case.trigger_distance, 1),
                       'approach_speed_m_s': round(case.approach_speed, 1),
                       'walk_speed_m_s': round(case.walk_speed, 2),
                       'quiet': case.dwell_seconds > 100,
                       'outcome': describe(case, score, trajectory), **score})
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2)+'\n')
    for row in report:
        print(f"{row['index']:3d}  seed {row['seed']}  trigger {row['trigger_distance_m']:4.1f} m  "
              f"approach {row['approach_speed_m_s']:.1f} m/s  ->  {row['outcome']}", flush=True)


if __name__ == '__main__':
    main()
