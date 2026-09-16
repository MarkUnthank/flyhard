#!/usr/bin/env python3
"""I00: twenty physical left/off/right/off cycles and a disabled-grip control."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw, ImageFont

from flyhard.indicator_rig import IndicatorRig


def cycles(rig, count, grip, progress_path):
    rig.reset(grip=grip)
    targets = [-rig.target_angle, 0., rig.target_angle, 0.]
    names = ["left", "off", "right", "off"]
    results, trace = [], []
    for cycle in range(count):
        for target, requested in zip(targets, names):
            before = rig.angle
            observations = []
            for step in range(200):
                ramped = before + (target - before) * min((step + 1) * rig.command_period / 0.4, 1)
                rig.step(rig.diagnostic_action(ramped))
                observations.append(rig.angle)
                if cycle < 2:
                    trace.append({"time": float(rig.data.time), "request": requested,
                                  "target": target, "angle": rig.angle, "signal": rig.signal,
                                  "qpos": rig.data.qpos.copy()})
            hold = np.array(observations[-40:])
            max_error = float(np.max(np.abs(hold - target)))
            passed = max_error < 0.08 if grip else bool(np.max(np.abs(observations)) < 0.02)
            results.append({"cycle": cycle, "requested": requested, "target": target,
                            "final_angle": rig.angle, "max_hold_error": max_error,
                            "max_motion": float(np.max(np.abs(observations))), "passed": passed})
            with progress_path.open("a") as stream:
                stream.write(json.dumps({"grip": grip, **results[-1]}) + "\n")
        print(json.dumps({"grip": grip, "cycle": cycle, "passed": all(r["passed"] for r in results[-4:])}), flush=True)
    return results, trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="runs/i00-stalk-v1")
    parser.add_argument("--cycles", type=int, default=20)
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("cycles must be positive")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "metrics.json").exists():
        raise FileExistsError("Use a fresh output directory")
    started = time.perf_counter()
    rig = IndicatorRig()
    rig.prepare_diagnostic_ik()
    config = {"stage": "I00", "claim": "Diagnostic joint commands; no trained indicator policy.",
              "coupling": "Engineered point-grip constraint; removal is tested.",
              "mechanism": "Counterbalanced spring-centred passive hinge; three measured zones; no latch.",
              "integrated_steering_wheel": False, "stalk_has_actuator": False,
              "cycles": args.cycles, "target_radians": rig.target_angle,
              "hold_error_limit_rad": 0.08, "disabled_motion_limit_rad": 0.02,
              "ik_max_error_mm": rig.ik_max_error_mm,
              "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               [Path(__file__), Path("src/flyhard/indicator_rig.py")]}}
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    enabled, trace = cycles(rig, args.cycles, True, out / "transitions.jsonl")
    np.savez_compressed(out / "body-trace.npz", time=[t["time"] for t in trace],
                        qpos=[t["qpos"] for t in trace], requested=[t["target"] for t in trace],
                        angle=[t["angle"] for t in trace], signal=[t["signal"] for t in trace])
    disabled, _ = cycles(rig, args.cycles, False, out / "transitions.jsonl")
    renderer = mj.Renderer(rig.model, height=720, width=1280)
    gpu = GL.glGetString(GL.GL_RENDERER).decode()
    assert "NVIDIA" in gpu, gpu
    camera = mj.MjvCamera()
    camera.lookat[:] = [0.3, 0.2, 1.2]
    camera.distance = 5.0
    camera.azimuth = 125
    camera.elevation = -25
    replay = mj.MjData(rig.model)
    text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 23)
    with imageio.get_writer(out / "stalk-proof.mp4", fps=25, quality=8, macro_block_size=1) as writer:
        for i, sample in enumerate(trace[::8]):
            replay.qpos[:] = sample["qpos"]
            replay.time = sample["time"]
            mj.mj_forward(rig.model, replay)
            renderer.update_scene(replay, camera=camera)
            renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
            frame = Image.fromarray(renderer.render())
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, 1280, 72), fill="black")
            draw.text((28, 24), "Physical indicator stalk / diagnostic leg commands", font=text_font, fill="white")
            draw.rectangle((0, 630, 1280, 720), fill="black")
            draw.text((28, 641), "REQUEST LEFT", font=text_font, fill="white" if sample["request"] == "left" else "#555")
            draw.text((290, 641), "REQUEST RIGHT", font=text_font, fill="white" if sample["request"] == "right" else "#555")
            draw.text((610, 641), f"STALK {np.degrees(sample['angle']):+.1f}°", font=text_font, fill="white")
            draw.text((940, 641), "SIGNAL " + sample["signal"].upper(), font=text_font, fill="white")
            draw.text((28, 685), "Passive lever. Engineered foot grip. No neural learning yet. Real-time playback.", font=text_font, fill="#aaa")
            writer.append_data(np.asarray(frame))
            if i in (20, 45, 70):
                frame.save(out / f"preview-{i:03}.png")
    renderer.close()
    metrics = {**config, "enabled_passed": sum(r["passed"] for r in enabled),
               "disabled_passed": sum(r["passed"] for r in disabled),
               "transitions_per_condition": len(enabled), "gpu_renderer": gpu,
               "status": "passed" if args.cycles == 20 and all(r["passed"] for r in enabled + disabled) else "preliminary",
               "wall_seconds": time.perf_counter() - started, "enabled": enabled, "disabled": disabled}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k not in ["enabled", "disabled"]}, indent=2))


if __name__ == "__main__":
    main()
