#!/usr/bin/env python3
"""Build supervised crossing demonstrations on CPU.

Behaviour cloning from clean teacher rollouts alone only ever sees states the
teacher visits, so a student that drifts has never been shown a recovery. Each
case is therefore also rolled out from perturbed speeds and positions, with the
teacher relabelling from wherever the perturbation left it.

No GPU. The three-point equivalent builds ~32k rows in about two seconds.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from flyhard.crossing import OBSERVATION_FIELDS, cases, kinematic_step, metrics, observation, pedestrian_state
from flyhard.crossing_teacher import target


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rollout(case, rng, jitter=0., steps=460, dt=.05):
    """One labelled rollout. `jitter` perturbs the starting speed and position."""
    state = case.start.astype(float)
    if jitter:
        state[0] += rng.uniform(-6., 6.)*jitter
        state[1] = max(0., state[1]+rng.uniform(-3., 2.5)*jitter)
    triggered_at = None
    throttle = brake = 0.
    observations, targets, trajectory = [], [], []
    from flyhard.crossing import FRONT_OVERHANG
    for step in range(steps):
        now = step*dt
        front = state[0]+FRONT_OVERHANG
        if triggered_at is None and -front <= case.trigger_distance:
            triggered_at = now
        pedestrian_y, lateral_speed, walking = pedestrian_state(case, triggered_at, now)
        observations.append(observation(state, case, pedestrian_y, lateral_speed, throttle, brake))
        action = target(state, case, pedestrian_y, lateral_speed)
        targets.append(action)
        trajectory.append({'state': state.copy(), 'pedestrian_y': pedestrian_y, 'walking': walking})
        # Small actuation noise widens the visited set without changing the label.
        throttle = float(np.clip(action[0]+rng.normal(0, .04)*jitter, 0., 1.))
        brake = float(np.clip(action[1]+rng.normal(0, .04)*jitter, 0., 1.))
        state = kinematic_step(state, throttle, brake, dt)
        if front > case.walk_offset+12.:
            break
    return np.asarray(observations, np.float32), np.asarray(targets, np.float32), trajectory


def build(split, count, perturbed, seed):
    rng = np.random.default_rng(seed)
    observations, targets, scored = [], [], []
    for case in cases(split, count):
        clean = rollout(case, rng, 0.)
        observations.append(clean[0])
        targets.append(clean[1])
        scored.append({'seed': case.seed, **metrics(clean[2], case)})
        for _ in range(perturbed if split == 'train' else 0):
            noisy = rollout(case, rng, 1.)
            observations.append(noisy[0])
            targets.append(noisy[1])
    return np.concatenate(observations), np.concatenate(targets), scored


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--train-cases', type=int, default=420)
    parser.add_argument('--validation-cases', type=int, default=80)
    parser.add_argument('--perturbed', type=int, default=3,
                        help='Extra perturbed rollouts per training case')
    parser.add_argument('--seed', type=int, default=733)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)

    counts = {'train': args.train_cases, 'validation': args.validation_cases}
    receipt = {'observation_fields': OBSERVATION_FIELDS, 'splits': {}, 'seed': args.seed,
               'perturbed_per_training_case': args.perturbed}
    for split, count in counts.items():
        observations, targets, scored = build(split, count, args.perturbed, args.seed)
        np.savez_compressed(out/f'{split}.npz', observations=observations, targets=targets)
        passed = sum(row['passed'] for row in scored)
        receipt['splits'][split] = {
            'cases': count, 'rows': int(len(observations)),
            'teacher_passed': int(passed), 'teacher_pass_rate': round(passed/count, 4),
            'teacher_contacts': int(sum(row['contact'] for row in scored)),
            'stop_required_cases': int(sum(row['stop_required'] for row in scored)),
            'quiet_cases': int(count-sum(row['stop_required'] for row in scored))}
        if passed < count*.95:
            raise SystemExit(f'{split}: teacher passed only {passed}/{count}; fix the demonstrator first')

    (out/'cases.json').write_text(json.dumps(
        {split: [c.record() for c in cases(split, counts.get(split, 80))]
         for split in ['train', 'validation', 'heldout']}, indent=2)+'\n')
    receipt['cases_sha256'] = sha(out/'cases.json')
    receipt['data_sha256'] = {f'{s}.npz': sha(out/f'{s}.npz') for s in counts}
    receipt['source_sha256'] = {n: sha(n) for n in
                                ['src/flyhard/crossing.py', 'src/flyhard/crossing_teacher.py', __file__]}
    receipt['claim'] = ('Supervised pedestrian-crossing demonstrations from a longitudinal '
                        'kinematic diagnostic. Not a driving result, and the model needs '
                        'calibrating against measured CARLA walkers before native trials.')
    (out/'data-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
