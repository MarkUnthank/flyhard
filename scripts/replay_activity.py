#!/usr/bin/env python3
"""Replay a recorded take's neuron states from the observations it wrote down.

The recorder kept the neuron states beside the trial, not beside the take, so a clip
synced out of a pod arrives without them. It does arrive with every observation the
policy was given, and the policy settles from rest on each control step rather than
carrying state between them, so the whole trace replays in one pass and reproduces the
run exactly. That is checked against the control demands the trial recorded, not
assumed: if they do not match, this is not the policy that drove the take.

Also writes the per-neuron peak, which is what the anatomy export uses to choose which
neurons to draw, so the neurons on screen are the ones this policy actually drives.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

# The whole batch's neuron states have to be resident at once, which at full length is
# gigabytes, so the trace goes through in chunks.
CHUNK = 64
TOLERANCE = 2e-3


def replay(rows, checkpoint, graph, scenario, core, device='cuda'):
    """Neuron states for every control step, as (steps, neurons), and the demands."""
    from evaluate_scenario import load_policy
    policy, _ = load_policy(checkpoint, graph, scenario, core)
    features = torch.tensor(core.encode(np.asarray([r['observation'] for r in rows],
                                                   np.float32)), device=device)
    states, demands = [], []
    with torch.no_grad():
        for start in range(0, len(features), CHUNK):
            output, neural = policy(features[start:start+CHUNK], return_state=True)
            states.append(neural.T.cpu().numpy().astype(np.float16))
            demands.append(output.cpu().numpy())
    return np.concatenate(states), np.concatenate(demands)


def check(rows, demands):
    """The replay must reproduce the demands the trial recorded, or it is not the run."""
    recorded = np.asarray([[r['demand_throttle'], r['demand_brake']] for r in rows])
    worst = float(np.abs(recorded-demands[:, :2]).max())
    if worst > TOLERANCE:
        raise RuntimeError(f'Replayed demands differ from the recorded ones by {worst:.5f}, '
                           f'over the {TOLERANCE} tolerance; this is not the policy that '
                           'drove the take')
    return worst


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--take', required=True, help='A clip-library take directory')
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--graph', default='data/graph-traced-v1')
    parser.add_argument('--out', required=True, help='Where to write the replayed activity')
    parser.add_argument('--strength-out', help='Per-neuron peak only, for the anatomy export')
    args = parser.parse_args()

    take = Path(args.take)
    manifest = json.loads((take/'take.json').read_text())
    rows = json.loads((take/'trace.json').read_text())
    from flyhard.scenarios import get
    scenario = get(manifest['scenario'])
    core, _ = scenario.modules
    activity, demands = replay(rows, args.checkpoint, args.graph, scenario, core)
    worst = check(rows, demands)
    np.savez_compressed(args.out, activity=activity)
    digest = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    if args.strength_out:
        np.savez(args.strength_out, max_abs_state=np.max(np.abs(activity.astype(np.float32)),
                                                         axis=0), trace_sha256=digest)
    print(json.dumps({'take': take.name, 'steps': len(rows), 'neurons': int(activity.shape[1]),
                      'replay_max_demand_error': worst, 'out': args.out,
                      'trace_sha256': digest}))


if __name__ == '__main__':
    main()
