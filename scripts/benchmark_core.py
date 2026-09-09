#!/usr/bin/env python3
"""E01: full retained graph system-identification test, not driving training."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import torch
from flyhard.connectome import SparseConnectome


def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--graph', default='data/graph-traced-v1')
    p.add_argument('--out', default='runs/e01-core')
    p.add_argument('--steps', type=int, default=80)
    p.add_argument('--seconds', type=int, default=900)
    p.add_argument('--batch', type=int, default=4)
    p.add_argument('--seed', type=int, default=1701)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    graph_dir = Path(args.graph)
    manifest = json.loads((graph_dir / 'manifest.json').read_text())
    config = {**vars(args), 'experiment': 'E01', 'device': device, 'rollout_steps': 4,
              'task': 'Fit a fixed synthetic teacher with the same measured graph; random initial states across all neurons.',
              'teacher_edge_gain_logit': 1.0, 'teacher_leak_logit': 0.8,
              'transmission': 'unsigned numerical proxy; acquired transmitter predictions not applied',
              'loss': 'mean squared next-state error divided by target variance',
              'threshold': 'at least 20% held-out loss reduction; finite nonzero core gradients; unchanged graph',
              'evaluation_seed': 99017, 'learning_rate': 0.08, 'graph_sha256': manifest['graph_sha256'],
              'claim': 'Numerical trainability only, not a learned motor skill, visual control, or driving.'}
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    start = time.perf_counter()
    arrays = np.load(graph_dir / 'graph.npz')
    net = SparseConnectome(arrays['crow'], arrays['col'], arrays['counts']).to(device)
    del arrays
    optimizer = torch.optim.Adam(net.parameters(), lr=config['learning_rate'])
    teacher_values = (net.base * (0.05 + 0.90 * torch.sigmoid(torch.tensor(1.0, device=device)))).detach()
    teacher_matrix = net.matrix(teacher_values)
    teacher_leak = 0.05 + 0.90 * torch.sigmoid(torch.tensor(0.8, device=device))
    def teacher(x):
        with torch.no_grad():
            for _ in range(config['rollout_steps']):
                x = (1-teacher_leak)*x + teacher_leak*torch.tanh(torch.sparse.mm(teacher_matrix, x))
        return x
    evaluation_rng = torch.Generator(device=device).manual_seed(config['evaluation_seed'])
    heldout = torch.randn(net.n, args.batch, generator=evaluation_rng, device=device) * 0.3
    heldout_target = teacher(heldout)
    scale = heldout_target.square().mean().clamp_min(1e-12)
    def evaluate():
        with torch.no_grad():
            prediction = net(heldout, steps=config['rollout_steps'])
            return float((prediction-heldout_target).square().mean()/scale)
    initial_loss = evaluate()
    sync()
    setup_seconds = time.perf_counter()-start
    if device == 'cuda':
        torch.cuda.reset_peak_memory_stats()
    history = []
    training_start = time.perf_counter()
    grad_stats = None
    for step in range(args.steps):
        if time.perf_counter()-training_start >= args.seconds:
            break
        x = torch.randn(net.n, args.batch, device=device) * 0.3
        target = teacher(x)
        optimizer.zero_grad(set_to_none=True)
        sync()
        tick = time.perf_counter()
        prediction = net(x, steps=config['rollout_steps'])
        loss = (prediction-target).square().mean()/scale
        sync()
        forward = time.perf_counter()-tick
        tick = time.perf_counter()
        loss.backward()
        sync()
        backward = time.perf_counter()-tick
        if grad_stats is None:
            grad_stats = {name: {'finite': bool(torch.isfinite(param.grad).all()),
                                'nonzero': int(torch.count_nonzero(param.grad)),
                                'total': param.numel(), 'norm': float(param.grad.norm())}
                          for name,param in net.named_parameters()}
            assert all(g['finite'] and g['nonzero'] > 0 for g in grad_stats.values())
        assert torch.isfinite(loss), 'Non-finite training objective'
        optimizer.step()
        sync()
        record = {'step': step+1, 'loss': float(loss.detach()), 'forward_s': forward,
                  'backward_s': backward, 'elapsed_s': time.perf_counter()-training_start}
        if (step+1) % 10 == 0 or step == 0 or step == args.steps-1:
            record['heldout_loss'] = evaluate()
            print(json.dumps(record), flush=True)
        history.append(record)
        (out / 'history.json').write_text(json.dumps(history, indent=2))
    final_loss = evaluate()
    graph_check = np.load(graph_dir / 'graph.npz')
    topology_unchanged = (np.array_equal(net.crow.cpu().numpy(), graph_check['crow'])
                          and np.array_equal(net.col.cpu().numpy(), graph_check['col']))
    assert topology_unchanged
    edge_change = float(net.edge_gain.detach().abs().mean())
    torch.save({'model': net.state_dict(), 'optimizer': optimizer.state_dict(), 'config': config,
                'graph_sha256': manifest['graph_sha256'], 'step': len(history)}, out / 'checkpoint.pt')
    with torch.no_grad():
        states = [heldout[:,0].cpu().numpy()]
        x = heldout
        for _ in range(config['rollout_steps']):
            x = net(x)
            states.append(x[:,0].cpu().numpy())
        np.savez_compressed(out / 'neural-trace.npz', body_ids=graph_check['body_ids'], activity=np.stack(states))
    steady = history[1:] or history
    metrics = {**config, 'neurons': net.n, 'edges': net.col.numel(), 'trainable_parameters': sum(x.numel() for x in net.parameters()),
               'initial_heldout_loss': initial_loss, 'final_heldout_loss': final_loss,
               'loss_reduction_fraction': 1-final_loss/initial_loss, 'optimizer_steps': len(history),
               'edge_gain_mean_absolute_update': edge_change, 'gradient_audit': grad_stats,
               'topology_unchanged': topology_unchanged, 'setup_seconds': setup_seconds,
               'training_wall_seconds': time.perf_counter()-training_start,
               'steady_forward_median_s': float(np.median([h['forward_s'] for h in steady])),
               'steady_backward_median_s': float(np.median([h['backward_s'] for h in steady])),
               'peak_allocated_gb': torch.cuda.max_memory_allocated()/1e9 if device == 'cuda' else None,
               'peak_reserved_gb': torch.cuda.max_memory_reserved()/1e9 if device == 'cuda' else None,
               'torch_version': torch.__version__, 'platform': platform.platform(),
               'gpu': torch.cuda.get_device_name() if device == 'cuda' else None,
               'status': 'passed' if final_loss <= 0.8*initial_loss and edge_change > 0 else 'failed'}
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == '__main__':
    main()
