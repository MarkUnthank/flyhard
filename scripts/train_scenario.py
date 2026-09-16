#!/usr/bin/env python3
"""Train pedal demands for one scenario inside the measured graph.

Runs on a GPU pod: the traced connectome is ~300 MB and lives on the network
volume, not in the repository. Only edge gains and neuron leaks learn; the
sensory population code and motor decoder stay frozen and are checked at the end.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pyarrow.feather as feather
import torch

from flyhard.scenario_policy import PedalPolicy
from flyhard.scenarios import get


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_policy(checkpoint, graph_dir='data/graph-traced-v1', scenario=None, reset_core=False):
    with gzip.open(checkpoint, 'rb') as f:
        saved = torch.load(f, map_location='cpu', weights_only=False)
    if sha(Path(graph_dir)/'graph.npz') != saved['config']['graph_sha256']:
        raise RuntimeError('Graph identity mismatch')
    s = saved['model']
    policy = PedalPolicy(np.load(Path(graph_dir)/'graph.npz'), s['sensory_ids'], s['motor_ids'],
                         saved['config']['feature_count'], saved['config']['seed'],
                         outputs=len(s['decoder']),
                         signed_outputs=scenario.signed_outputs if scenario else 0)
    missing, extra = policy.load_state_dict(s, strict=False)
    assert set(missing) == {'core.crow', 'core.col', 'core.rows', 'core.base'} and not extra
    if reset_core:
        with torch.no_grad():
            policy.core.edge_gain.zero_()
            policy.core.leak.zero_()
    return policy.cuda().eval(), saved


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenario', required=True)
    p.add_argument('--data', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--graph', default='data/graph-traced-v1')
    p.add_argument('--steps', type=int, default=1200)
    p.add_argument('--batch', type=int, default=64)
    p.add_argument('--seed', type=int, default=733)
    p.add_argument('--lr', type=float, default=.04)
    p.add_argument('--brake-weight', type=float, default=2.0,
                   help='Braking errors matter more than throttle errors here')
    p.add_argument('--steer-weight', type=float, default=8.0,
                   help='Steering travel is small and signed, so its error needs weighting up')
    p.add_argument('--both-penalty', type=float, default=.5,
                   help='Discourage pressing both pedals at once')
    p.add_argument('--resume')
    p.add_argument('--save-interval', type=int, default=200)
    args = p.parse_args()

    scenario = get(args.scenario)
    core, _ = scenario.modules
    encode, OBSERVATION_FIELDS = core.encode, core.OBSERVATION_FIELDS
    root, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(8)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    train, val = np.load(root/'train.npz'), np.load(root/'validation.npz')
    tx = torch.tensor(encode(train['observations']), device='cuda')
    ty = torch.tensor(train['targets'], device='cuda')
    take = np.linspace(0, len(val['targets'])-1, min(2048, len(val['targets'])), dtype=int)
    vx = torch.tensor(encode(val['observations'][take]), device='cuda')
    vy = torch.tensor(val['targets'][take], device='cuda')

    nodes = feather.read_table(Path(args.graph)/'nodes.feather')
    classes = np.array(nodes['superclass'].fill_null('').to_pylist())
    if args.resume:
        policy, _ = load_policy(args.resume, args.graph, scenario)
        policy.train()
    else:
        policy = PedalPolicy(np.load(Path(args.graph)/'graph.npz'),
                             np.flatnonzero(classes == 'vnc_sensory'),
                             np.flatnonzero(classes == 'vnc_motor'),
                             tx.shape[1], args.seed, outputs=ty.shape[1],
                             signed_outputs=scenario.signed_outputs).cuda()
        policy.calibrate(tx[rng.choice(len(tx), 64, replace=False)])

    fixed = {n: b.detach().cpu().clone() for n, b in policy.named_buffers() if not n.startswith('core.')}
    config = {**vars(args), 'signed_outputs': scenario.signed_outputs, 'graph_sha256': sha(Path(args.graph)/'graph.npz'),
              'feature_count': int(tx.shape[1]), 'cases_sha256': sha(root/'cases.json'),
              'data_sha256': {n: sha(root/n) for n in ['train.npz', 'validation.npz']},
              'observation_fields': OBSERVATION_FIELDS,
              'claim': scenario.claim+' Native CARLA evaluation required.',
              'learned': 'Measured-edge gains and neuron leaks; fixed sensory population code and motor decoder.',
              'outputs': scenario.outputs,
              'motor_adapter': 'Offline IK moves the fly legs; only measured pedal travel drives CARLA.',
              'heldout_used_for_training': False, 'state_reset_each_decision': True,
              'source_sha256': {n: sha(n) for n in scenario.sources()
                                +['src/flyhard/scenario_policy.py', __file__]}}
    (out/'config.json').write_text(json.dumps(config, indent=2)+'\n')

    opt = torch.optim.Adam(policy.parameters(), lr=args.lr)
    history, best, start, gradient = [], float('inf'), time.monotonic(), None

    weights = torch.ones(policy.outputs, device='cuda')
    weights[1] = args.brake_weight
    if policy.outputs > 2:
        weights[2] = args.steer_weight

    def objective(features, targets):
        predicted = policy.training_outputs(features)
        loss = ((predicted-targets).square()*weights).sum(dim=1)
        # The teacher never presses both pedals; a trial that does is a real failure.
        return loss+args.both_penalty*(predicted[:, 0]*predicted[:, 1])

    def validate():
        total = 0.
        with torch.no_grad():
            for i in range(0, len(vx), args.batch):
                total += float(objective(vx[i:i+args.batch], vy[i:i+args.batch]).sum())
        return total/len(vx)

    initial = validate()
    print(json.dumps({'initial_validation_loss': initial}), flush=True)
    for step in range(1, args.steps+1):
        idx = rng.choice(len(tx), args.batch)
        opt.zero_grad(set_to_none=True)
        loss = objective(tx[idx], ty[idx]).mean()
        loss.backward()
        if gradient is None:
            gradient = {n: bool(torch.isfinite(p.grad).all() and torch.count_nonzero(p.grad) > 0)
                        for n, p in policy.named_parameters()}
            assert all(gradient.values())
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.)
        opt.step()
        if step == 1 or step % 100 == 0 or step == args.steps:
            score = validate()
            row = {'step': step, 'training_loss': float(loss.detach()), 'validation_loss': score,
                   'seconds': time.monotonic()-start}
            history.append(row)
            print(json.dumps(row), flush=True)
            (out/'history.json').write_text(json.dumps(history, indent=2)+'\n')
            if score < best:
                best = score
                with gzip.open(out/'checkpoint.tmp.gz', 'wb', compresslevel=3) as f:
                    torch.save({'model': policy.checkpoint_state(), 'config': config, 'step': step}, f)
                (out/'checkpoint.tmp.gz').replace(out/'checkpoint.pt.gz')
            if args.save_interval and step % args.save_interval == 0:
                with gzip.open(out/f'step-{step:04}.pt.gz', 'wb', compresslevel=3) as f:
                    torch.save({'model': policy.checkpoint_state(), 'config': config, 'step': step}, f)

    assert all(torch.equal(b.detach().cpu(), fixed[n]) for n, b in policy.named_buffers() if n in fixed)
    (out/'metrics.json').write_text(json.dumps(
        {'status': f'trained; native {scenario.name} evaluation pending', 'initial_validation_loss': initial,
         'best_validation_loss': best, 'training_seconds': time.monotonic()-start,
         'gradient_audit': gradient, 'frozen_interfaces_unchanged': True,
         'checkpoint_sha256': sha(out/'checkpoint.pt.gz')}, indent=2)+'\n')


if __name__ == '__main__':
    main()
