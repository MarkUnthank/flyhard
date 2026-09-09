#!/usr/bin/env python3
"""E00: upstream NeuroMechFly motion targets, physical simulation, exact replay.

This is a dependency test. It contains no connectome controller and no car.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw

from flygym import Simulation
from flygym.anatomy import Skeleton, AxisOrder, JointPreset, ActuatedDOFPreset
from flygym.compose import NeuroMechFly, KinematicPosePreset, ActuatorType, FlatGroundWorld
from flygym.utils.math import Rotation3D
from flygym_demo.spotlight_data import MotionSnippet


def build():
    fly = NeuroMechFly()
    skeleton = Skeleton(axis_order=AxisOrder.YAW_PITCH_ROLL, joint_preset=JointPreset.LEGS_ONLY)
    fly.add_joints(skeleton, neutral_pose=KinematicPosePreset.NEUTRAL)
    dofs = skeleton.get_actuated_dofs_from_preset(ActuatedDOFPreset.LEGS_ACTIVE_ONLY)
    fly.add_actuators(dofs, actuator_type=ActuatorType.POSITION, kp=150.0,
                      neutral_input=KinematicPosePreset.NEUTRAL)
    fly.colorize()
    camera = fly.add_tracking_camera()
    fly.add_leg_adhesion()
    world = FlatGroundWorld()
    world.add_fly(fly, [0, 0, 0.7], Rotation3D("quat", [1, 0, 0, 0]))
    sim = Simulation(world, timestep=1e-4)
    return fly, camera, sim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runs/e00-body")
    parser.add_argument("--seconds", type=float, default=1.5)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    fly, camera, sim = build()
    model, data = sim.mj_model, sim.mj_data
    snippet = MotionSnippet()
    targets = snippet.get_joint_angles(output_timestep=1e-4,
               output_dof_order=fly.get_actuated_jointdofs_order(ActuatorType.POSITION))
    steps = min(int(args.seconds / sim.timestep), len(targets))
    predeclared = {"experiment": "E00", "source": "FlyGym upstream experimental motion replay",
                  "claim": "Body dependency and replay only; no neural training or driving",
                  "steps": steps, "dt_s": sim.timestep, "threshold": "finite states; exact saved state replay",
                  "playback_speed": 0.1, "seed": 0, "timeout_seconds": 300}
    (out / "config.json").write_text(json.dumps(predeclared, indent=2))
    sim.reset()
    sim.set_leg_adhesion_states(fly.name, np.ones(6, dtype=bool))
    sim.warmup()
    setup_s = time.perf_counter() - start
    qpos = np.empty((steps, model.nq))
    controls = np.empty((steps, model.nu), np.float32)
    times = np.empty(steps)
    contacts = np.empty(steps, np.int32)
    begin = time.perf_counter()
    for i in range(steps):
        sim.set_actuator_inputs(fly.name, ActuatorType.POSITION, targets[i])
        sim.step()
        qpos[i] = data.qpos
        controls[i] = data.ctrl
        times[i] = data.time
        contacts[i] = data.ncon
    physics_s = time.perf_counter() - begin
    assert np.isfinite(qpos).all(), "Non-finite physical state"
    assert np.allclose(np.diff(times), sim.timestep, rtol=0, atol=1e-12)
    np.savez_compressed(out / "trace.npz", time=times, qpos=qpos, ctrl=controls, contacts=contacts)
    loaded = np.load(out / "trace.npz")
    assert np.array_equal(loaded["qpos"], qpos)
    assert np.array_equal(loaded["time"], times)
    # Replay uses the saved clock and physical states, not a separate animation.
    replay = mj.MjData(model)
    renderer = mj.Renderer(model, height=540, width=960)
    camera_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_CAMERA, fly.name + "/" + camera.name)
    if camera_id < 0:
        assert model.ncam == 1
        camera_id = 0
    every = max(1, round(0.1 / (30 * sim.timestep)))
    replay_errors = []
    with imageio.get_writer(out / "body-baseline.mp4", fps=30, macro_block_size=1, quality=8) as video:
        for i in range(0, steps, every):
            replay.qpos[:] = loaded["qpos"][i]
            replay.time = float(loaded["time"][i])
            mj.mj_forward(model, replay)
            replay_errors.append(float(np.max(np.abs(replay.qpos - qpos[i]))))
            renderer.update_scene(replay, camera=camera_id)
            frame = Image.fromarray(renderer.render())
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, 960, 48), fill=(17, 22, 27))
            draw.text((18, 12), f"FLYHARD / E00  |  Body simulator test  |  t={times[i]:.3f}s  |  playback 0.1x", fill="white")
            draw.rectangle((0, 506, 960, 540), fill=(17, 22, 27))
            draw.text((18, 516), "Recorded upstream leg targets -> MuJoCo joint physics. No connectome control or driving yet.", fill=(208, 213, 218))
            video.append_data(np.asarray(frame))
            if i == 0:
                frame.save(out / "preview.png")
    renderer.close()
    metrics = {**predeclared, "setup_seconds": setup_s, "physics_wall_seconds": physics_s,
               "physics_steps_per_second": steps / physics_s, "simulation_seconds": steps * sim.timestep,
               "nq": model.nq, "actuators": model.nu, "replay_max_qpos_error": max(replay_errors),
               "finite": True, "trace_sha256": hashlib.sha256((out / "trace.npz").read_bytes()).hexdigest(),
               "versions": {n: importlib.metadata.version(n) for n in ["flygym", "mujoco", "numpy"]},
               "platform": platform.platform(), "status": "passed"}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
