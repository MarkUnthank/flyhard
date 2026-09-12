#!/usr/bin/env python3
"""Generate behaviour-cloning labels for a scenario on the CPU.

Clean rollouts give the demonstrated trajectory; perturbed ones start from a jittered
state and carry small actuation noise, so the policy sees states a slightly wrong
earlier action would have produced. Nothing is written unless the teacher itself
clears the gate it is teaching.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from flyhard.scenarios import get


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(scenario, split, count, perturbed, seed):
    core, teacher = scenario.modules
    rng = np.random.default_rng(seed)
    observations, targets, scored = [], [], []
    for case in core.cases(split, count):
        clean = teacher.rollout(case)
        observations.append(clean[0])
        targets.append(clean[1])
        scored.append({'seed': case.seed, **core.metrics(clean[2], case)})
        for _ in range(perturbed if split == 'train' else 0):
            noisy = teacher.rollout(case, rng=rng, jitter=1.)
            observations.append(noisy[0])
            targets.append(noisy[1])
    return np.concatenate(observations), np.concatenate(targets), scored


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--train-cases', type=int, default=420)
    parser.add_argument('--validation-cases', type=int, default=90)
    parser.add_argument('--perturbed', type=int, default=4)
    parser.add_argument('--seed', type=int, default=733)
    parser.add_argument('--min-pass-rate', type=float, default=.95)
    args = parser.parse_args()

    scenario = get(args.scenario)
    core, _ = scenario.modules
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)

    summary = {}
    for split, count in [('train', args.train_cases), ('validation', args.validation_cases)]:
        observations, targets, scored = build(scenario, split, count, args.perturbed, args.seed)
        passed = sum(row['passed'] for row in scored)
        rate = passed/max(len(scored), 1)
        # Scenarios name their own failure modes, so report whichever flags this one has
        # rather than assuming the crossing's.
        flags = sorted({key for row in scored for key, value in row.items()
                        if isinstance(value, bool)})
        summary[split] = {'cases': len(scored), 'passed': passed, 'pass_rate': round(rate, 4),
                          'rows': int(len(observations)),
                          'flags': {key: sum(bool(row.get(key)) for row in scored) for key in flags},
                          'control_activity': {
                              index: round(float((np.abs(targets[:, index]) > .02).mean()), 4)
                              for index in range(targets.shape[1])}}
        if rate < args.min_pass_rate:
            raise SystemExit(f'{split}: teacher passed only {passed}/{len(scored)}; '
                             'labels would teach the wrong behaviour')
        np.savez_compressed(out/f'{split}.npz', observations=observations, targets=targets)
        (out/f'{split}-cases.json').write_text(json.dumps(scored, indent=2)+'\n')

    (out/'cases.json').write_text(json.dumps(
        [c.record() for c in core.cases('train', args.train_cases)], indent=2)+'\n')
    receipt = {'scenario': scenario.name, 'splits': summary, 'perturbed_per_case': args.perturbed,
               'observation_fields': core.OBSERVATION_FIELDS, 'seed': args.seed,
               'teacher': 'training-only demonstrator; never imported by learned inference',
               'source_sha256': {path: sha(path) for path in scenario.sources()+[__file__]}}
    (out/'data-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main()
