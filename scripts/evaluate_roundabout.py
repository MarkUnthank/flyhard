#!/usr/bin/env python3
"""Held-out traffic observations drive a fresh physical fly, without teacher commands."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

from flyhard.cockpit import WheelRig
from flyhard.indicator_policy import encode_context
from train_roundabout import load_policy, sha
from flyhard.roundabout_metrics import score_signals, episode_complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data", default="runs/roundabout-data-v3")
    parser.add_argument("--out", required=True)
    parser.add_argument("--split", choices=["validation", "test"], default="test")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--condition", choices=["trained", "core-reset", "no-stalk-grip"], default="trained")
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter(); torch.set_num_threads(4)
    policy, saved = load_policy(args.checkpoint)
    if args.condition == "core-reset":
        with torch.no_grad():
            policy.core.edge_gain.zero_(); policy.core.leak.zero_()
    rig = WheelRig(indicator_stalk=True)
    episodes = [r for r in json.loads((Path(args.data) / "episodes.json").read_text()) if r["split"] == args.split][:args.limit]
    for episode in episodes:
        episode["completed"] = episode_complete(episode)
    results = []
    for episode in episodes:
        with np.load(Path(args.data) / (episode["name"] + ".npz")) as archive:
            data = {k: archive[k] for k in archive.files}
        t = np.arange(len(data["context"])) * .05
        requested = .20 * np.sin(.65 * t) + .07 * np.sin(2.1 * t)
        features = torch.tensor(encode_context(data["context"], requested), device="cuda")
        commands = []
        with torch.no_grad():
            for i in range(0, len(features), 32):
                commands.extend(policy(features[i:i + 32]).cpu().numpy())
        rig.reset(stalk_grip=args.condition != "no-stalk-grip")
        wheel, stalk, signal, qpos = [], [], [], []
        for action in commands:
            for _ in range(10):
                rig.step_both(action)
            wheel.append(rig.angle); stalk.append(rig.stalk.angle); signal.append(rig.stalk.signal)
            qpos.append(rig.data.qpos.copy())
        result = {**episode, **score_signals(data["progress"], signal, episode), "condition": args.condition,
                  "wheel_rmse_rad": float(np.sqrt(np.mean((np.array(wheel) - requested) ** 2))),
                  "max_stalk_angle_rad": float(np.max(np.abs(stalk))),
                  "signal_frame_accuracy": float(np.mean((np.array(signal) == "right") == data["teacher_right"]))}
        results.append(result)
        np.savez_compressed(out / (episode["name"] + ".npz"), time=t + .05, qpos=qpos, wheel=wheel, stalk=stalk,
                            signal=signal, requested=requested, action=commands, progress=data["progress"])
        (out / "episodes.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(result), flush=True)
    metrics = {**vars(args), "checkpoint_sha256": sha(args.checkpoint), "selected_step": saved["step"],
               "passed": sum(r["passed"] for r in results), "episodes": len(results),
               "route_completed": sum(r["completed"] for r in episodes),
               "mean_signal_frame_accuracy": float(np.mean([r["signal_frame_accuracy"] for r in results])),
               "mean_wheel_rmse_rad": float(np.mean([r["wheel_rmse_rad"] for r in results])),
               "wall_seconds": time.perf_counter() - started,
               "claim": "Real physical fly replay of held-out CARLA navigation/traffic observations. Vehicle trajectory was controlled during collection; live coupled recording is separate.",
               "score": "Right activation 40–16m before exit boundary; hold 14m before through 5m after; cancel by 20m after; no left signal; route completion required."}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
