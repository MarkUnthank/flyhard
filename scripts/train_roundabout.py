#!/usr/bin/env python3
"""Train one connectome to command the wheel and infer when to use the stalk."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pyarrow.feather as feather
import torch

from flyhard.cockpit import WheelRig
from flyhard.indicator_policy import IndicatorPolicy, encode_context
from flyhard.roundabout_metrics import episode_complete


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load_policy(checkpoint, graph_dir="data/graph-traced-v1", device="cuda"):
    with gzip.open(checkpoint, "rb") as f:
        saved = torch.load(f, map_location="cpu", weights_only=False)
    assert sha(Path(graph_dir) / "graph.npz") == saved["config"]["graph_sha256"]
    s = saved["model"]
    policy = IndicatorPolicy(np.load(Path(graph_dir) / "graph.npz"), s["sensory_ids"], s["motor_ids"],
                             s["neutral"], s["action_scale"], saved["config"]["seed"])
    missing, unexpected = policy.load_state_dict(s, strict=False)
    assert set(missing) == {"core.crow", "core.col", "core.rows", "core.base"} and not unexpected
    return policy.to(device).eval(), saved


def dataset(root, split):
    contexts, signals, names = [], [], []
    for episode in json.loads((root / "episodes.json").read_text()):
        if episode["split"] != split or not episode_complete(episode):
            continue
        with np.load(root / (episode["name"] + ".npz")) as data:
            contexts.append(data["context"][::3])
            signals.append(data["teacher_right"][::3])
        names.append(episode["name"])
    if not contexts:
        raise RuntimeError(f"No completed {split} episodes")
    return np.concatenate(contexts), np.concatenate(signals), names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="runs/roundabout-data-v1")
    parser.add_argument("--out", default="runs/roundabout-policy-v1")
    parser.add_argument("--graph", default="data/graph-traced-v1")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--batch", type=int, default=24)
    parser.add_argument("--seed", type=int, default=123)
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    torch.set_num_threads(4); torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    context, signal, train_names = dataset(Path(args.data), "train")
    val_context, val_signal, val_names = dataset(Path(args.data), "validation")
    rig = WheelRig(indicator_stalk=True)
    rig.prepare_diagnostic_ik(); rig.stalk.prepare_diagnostic_ik()
    neutral = np.r_[rig.neutral_actions, rig.stalk.neutral_actions]
    scale = np.r_[np.max(np.abs(rig.ik_actions - rig.neutral_actions), axis=0),
                  np.max(np.abs(rig.stalk.ik_actions - rig.stalk.neutral_actions), axis=0)]
    scale = np.maximum(scale, .05) * 1.15
    nodes = feather.read_table(Path(args.graph) / "nodes.feather")
    classes = np.array(nodes["superclass"].fill_null("").to_pylist())
    policy = IndicatorPolicy(np.load(Path(args.graph) / "graph.npz"), np.flatnonzero(classes == "vnc_sensory"),
                             np.flatnonzero(classes == "vnc_motor"), neutral, scale, args.seed).cuda()
    config = {**vars(args), "graph_sha256": sha(Path(args.graph) / "graph.npz"),
              "data_episodes_sha256": sha(Path(args.data) / "episodes.json"),
              "train_episodes": train_names, "validation_episodes": val_names,
              "training_seed_count": 1, "learning_rate": .04,
              "claim": "Supervised connectome control using GPS/navigation and traffic, plus requested wheel angle. Not vision or autonomous route planning.",
              "learned": "Only measured-edge gains and neuron leaks; frozen sensory interface and motor readout.",
              "target": "14 joint targets: left foreleg grips passive wheel; right foreleg grips passive indicator stalk.",
              "teacher": "Route-derived right/off labels and offline IK; neither supplied to inference.",
              "inputs_exclude": ["time", "progress", "teacher_right", "signal_request", "stalk_target"],
              "state_reset_each_decision": True, "neural_steps": 4,
              "completion_rule": "Reach the route goal within 3.01m, with maximum route error below 5m.",
              "code_sha256": {p: sha(p) for p in [__file__, "src/flyhard/indicator_policy.py", "src/flyhard/cockpit.py", "src/flyhard/stalk.py", "src/flyhard/roundabout_metrics.py"]}}
    (out / "config.json").write_text(json.dumps(config, indent=2))
    np.savez_compressed(out / "ik-teacher.npz", wheel_angles=rig.ik_angles, wheel_actions=rig.ik_actions,
                        stalk_angles=rig.stalk.ik_angles, stalk_actions=rig.stalk.ik_actions, neutral=neutral, scale=scale)

    def labels(wheel, right):
        return np.stack([np.r_[rig.diagnostic_action(w), rig.stalk.diagnostic_action(.35 if r else 0.)]
                         for w, r in zip(wheel, right)]).astype(np.float32)

    def tensors(c, s, w):
        return torch.tensor(encode_context(c, w), device="cuda"), torch.tensor(labels(w, s), device="cuda")

    take = rng.choice(len(context), min(64, len(context)), replace=False)
    calibration, _ = tensors(context[take], signal[take], rng.uniform(-.45, .45, len(take)))
    policy.calibrate(calibration)
    fixed = {name: tensor.detach().cpu().clone() for name, tensor in policy.named_buffers()
             if not name.startswith("core.")}
    torch.save(fixed, out / "frozen-interface.pt")
    val_take = np.linspace(0, len(val_context) - 1, min(768, len(val_context)), dtype=int)
    val_x, val_y = tensors(val_context[val_take], val_signal[val_take], rng.uniform(-.45, .45, len(val_take)))
    positive, negative = np.flatnonzero(signal), np.flatnonzero(~signal)
    assert len(positive) and len(negative)
    optimizer = torch.optim.Adam(policy.parameters(), lr=.04)
    history, best, gradient = [], float("inf"), None

    def validate():
        total = 0.
        with torch.no_grad():
            for i in range(0, len(val_x), args.batch):
                prediction = policy(val_x[i:i + args.batch])
                total += float(((prediction - val_y[i:i + args.batch]) / policy.action_scale).square().sum())
        return total / (len(val_x) * 14)

    initial_loss = validate()
    print(json.dumps({"initial_validation_loss": initial_loss, "train_rows": len(context), "val_rows": len(val_context)}), flush=True)
    train_started = time.perf_counter()
    for step in range(1, args.steps + 1):
        idx = np.r_[rng.choice(positive, args.batch // 2), rng.choice(negative, args.batch - args.batch // 2)]
        x, y = tensors(context[idx], signal[idx], rng.uniform(-.45, .45, len(idx)))
        optimizer.zero_grad(set_to_none=True)
        prediction = policy(x)
        loss = ((prediction - y) / policy.action_scale).square().mean()
        assert torch.isfinite(loss)
        loss.backward()
        if gradient is None:
            gradient = {n: {"finite": bool(torch.isfinite(p.grad).all()), "nonzero": int(torch.count_nonzero(p.grad))}
                        for n, p in policy.named_parameters()}
            assert all(g["finite"] and g["nonzero"] > 0 for g in gradient.values())
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.)
        optimizer.step()
        if step == 1 or step % 100 == 0:
            value = validate()
            row = {"step": step, "loss": float(loss.detach()), "validation_loss": value,
                   "training_seconds": time.perf_counter() - train_started}
            history.append(row)
            print(json.dumps(row), flush=True)
            (out / "history.json").write_text(json.dumps(history, indent=2))
            if value < best:
                best = value
                temporary = out / "checkpoint.tmp.gz"
                with gzip.open(temporary, "wb", compresslevel=3) as f:
                    torch.save({"model": policy.checkpoint_state(), "config": config, "step": step,
                                "validation_loss": value}, f)
                temporary.replace(out / "checkpoint.pt.gz")
    assert all(torch.equal(t.detach().cpu(), fixed[n]) for n, t in policy.named_buffers() if n in fixed)
    metrics = {**config, "status": "trained_pending_physical_evaluation", "initial_validation_loss": initial_loss,
               "best_validation_loss": best, "gradient_audit": gradient, "frozen_interfaces_unchanged": True,
               "trainable_parameters": sum(p.numel() for p in policy.parameters()),
               "training_seconds": time.perf_counter() - train_started, "wall_seconds": time.perf_counter() - started,
               "peak_gpu_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
               "checkpoint_sha256": sha(out / "checkpoint.pt.gz")}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
