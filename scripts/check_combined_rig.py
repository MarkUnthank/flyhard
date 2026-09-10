#!/usr/bin/env python3
"""Independent wheel/stalk motion and removal-of-grip interventions."""
import json
from pathlib import Path
import time

import numpy as np

from flyhard.cockpit import WheelRig

root = Path("runs/combined-rig-v1"); root.mkdir(parents=True, exist_ok=True)
started = time.perf_counter()
rig = WheelRig(indicator_stalk=True)
rig.prepare_diagnostic_ik(); rig.stalk.prepare_diagnostic_ik()
records = []
for wheel_grip, stalk_grip in [(True, True), (False, True), (True, False)]:
    rig.reset(grip=wheel_grip, stalk_grip=stalk_grip)
    for wheel, stalk in [(.30, .35), (-.30, .35), (.30, -.35), (-.30, -.35), (0., 0.)]:
        before_w, before_s = rig.angle, rig.stalk.angle
        samples = []
        for i in range(300):
            mix = min((i + 1) * rig.command_period / .5, 1.)
            action = np.r_[rig.diagnostic_action(before_w + mix * (wheel - before_w)),
                           rig.stalk.diagnostic_action(before_s + mix * (stalk - before_s))]
            rig.step_both(action)
            samples.append([rig.angle, rig.stalk.angle])
        expected = np.array([wheel if wheel_grip else 0., stalk if stalk_grip else 0.])
        errors = np.max(np.abs(np.array(samples)[-60:] - expected), axis=0)
        row = {"wheel_grip": wheel_grip, "stalk_grip": stalk_grip, "wheel_target": wheel,
               "stalk_target": stalk, "measured": samples[-1], "hold_errors_rad": errors.tolist(),
               "passed": bool(np.all(errors < [.13 if wheel_grip else .02, .08 if stalk_grip else .02]))}
        records.append(row); print(json.dumps(row), flush=True)
        (root / "trials.json").write_text(json.dumps(records, indent=2))
metrics = {"passed": sum(r["passed"] for r in records), "trials": len(records),
           "wheel_ik_max_error_mm": rig.ik_max_error_mm, "stalk_ik_max_error_mm": rig.stalk.ik_max_error_mm,
           "wall_seconds": time.perf_counter() - started, "passive_controls": True,
           "claim": "Diagnostic joint commands; mechanical verification before learning."}
(root / "metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics), flush=True)
assert all(r["passed"] for r in records)
