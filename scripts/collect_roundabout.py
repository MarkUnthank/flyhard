#!/usr/bin/env python3
"""Collect clock-free navigation/traffic observations from controlled CARLA routes."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from flyhard.roundabout import RoundaboutWorld, DT, route_metadata, set_signal
from flyhard.indicator_policy import CONTEXT_FIELDS
from flyhard.roundabout_metrics import episode_complete


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="runs/roundabout-data-v1")
    p.add_argument("--per-route", type=int, default=4)
    p.add_argument("--route-limit", type=int, default=12)
    p.add_argument("--seconds", type=float, default=70)
    p.add_argument("--traffic", type=int, default=10)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    env = RoundaboutWorld(render=False)
    records = []
    config = {**vars(args), "context_fields": CONTEXT_FIELDS, "dt": DT,
              "claim": "CARLA navigation and traffic data; route controller supplies motion, no learned policy yet.",
              "teacher": "Right signal from 30m before to 10m after the selected roundabout exit boundary.",
              "policy_excluded_fields": ["progress", "teacher_right", "exit_s", "start_s", "end_s", "time", "frame"],
              "map": env.world.get_map().name,
              "skipped_route_combinations": env.skipped_routes,
              "code_sha256": {n: hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
                              ["scripts/collect_roundabout.py", "src/flyhard/roundabout.py", "src/flyhard/indicator_policy.py"]}}
    (out / "config.json").write_text(json.dumps(config, indent=2))
    (out / "routes.json").write_text(json.dumps([route_metadata(r) for r in env.routes], indent=2))
    try:
        for route_index, route in enumerate(env.routes[:args.route_limit]):
            for repeat in range(args.per_route):
                split = "test" if repeat == args.per_route - 1 else "validation" if repeat == args.per_route - 2 else "train"
                seed = 41000 + route_index * 137 + repeat * 19
                speed = [20., 28., 23., 25.5][repeat % 4]
                traffic = env.start(route, seed, speed, args.traffic + repeat % 3)
                contexts, annotations = [], []
                for _ in range(round(args.seconds / DT)):
                    context, annotation = env.observe()
                    contexts.append(context)
                    annotations.append(annotation)
                    # Collection lamps are explicitly the training teacher. No
                    # collection footage is presented as a learned-policy run.
                    set_signal(env.ego, "right" if annotation["teacher_right"] else "off")
                    env.tick_route()
                    if annotation["progress"] >= route["length"] - 3:
                        break
                    if annotation["route_error_m"] > 6:
                        break
                name = f"{route['id']}-seed{seed}"
                np.savez_compressed(out / (name + ".npz"), context=np.array(contexts),
                                    **{k: np.array([a[k] for a in annotations]) for k in annotations[0]})
                meta = {"name": name, "split": split, "seed": seed, "speed_kmh": speed,
                        "traffic_spawned": traffic, **route_metadata(route),
                        "frames": len(contexts), "completed": annotations[-1]["progress"] >= route["end_s"] + 12 and max(a["route_error_m"] for a in annotations) < 5,
                        "max_progress": annotations[-1]["progress"],
                        "max_route_error_m": max(a["route_error_m"] for a in annotations),
                        "traffic_within_25m_frames": sum(a["nearest_traffic_m"] < 25 for a in annotations)}
                records.append(meta)
                meta["completed"] = episode_complete(meta)
                (out / "episodes.json").write_text(json.dumps(records, indent=2))
                print(json.dumps(meta), flush=True)
    finally:
        env.close()
    print(json.dumps({"episodes": len(records), "completed": sum(r["completed"] for r in records),
                      "wall_seconds": time.perf_counter() - started}), flush=True)


if __name__ == "__main__":
    main()
