# Flyhard: connected steering video

The requested 16:9 video places CARLA on the left, computed CNS activity at the top right, and the simulated fly operating its wheel below. This experiment also connects the previously stationary learned steering skill to a moving CARLA vehicle. It is a 24-second instructed steering demonstration, not visual autonomous driving.

## What runs

The unchanged E03 seed-123 checkpoint receives a requested wheel angle, measured wheel angle, and foreleg joint positions. Its connectome-based neural computation produces seven foreleg joint targets. Joint servos move the leg, an explicit assisted point grip transmits force to the passive wheel, and the wheel's measured angle determines CARLA steering. The wheel has no actuator. Vehicle speed and the sequence of turn requests are scripted; CARLA autopilot is disabled.

The model retains the original pilot's 165,122 traced neurons and 25,563,197 measured neuron-pair edges. Its trainable gains and leaks operate on normalized, unsigned connectivity with signed rate states. This is a connectome-based computational model, not a reconstruction of the original animal's physiological activity.

The supported cockpit does not receive CARLA acceleration forces. The car is CARLA's stock green Mini Cooper proxy; the battered Panda/Flyat shell remains future work. This run does not exercise learned pedals or indicators.

## One recording clock

Neural decisions run at 20 Hz, joint commands at 200 Hz, body physics at 20 kHz, and CARLA cameras/world ticks at 25 Hz. At the start of each 40 ms interval, the coordinator reads the physical wheel and holds the derived steering command through that CARLA tick. Both simulators then advance to the same endpoint. The on-screen neural timestamp identifies the most recent decision.

The video uses CARLA's recorded camera frames, recorded body states rendered through MuJoCo, and the actual model state associated with each body sample. It has 600 frames at 1920 by 1080, 25 fps, and normal playback speed. The maximum camera/body clock mismatch is 0.537 microseconds. Every restored body pose exactly matches the saved pose.

The CNS image projects all 140,024 retained neurons with annotated soma coordinates; 25,098 model neurons lack those coordinates and cannot be positioned in this view. Orange and blue represent positive and negative computed rate states using one fixed nonlinear color scale for the episode. These are not spike recordings. At overlapping pixels, the strongest absolute state supplies the entire color so opposing signs cannot create a false third color.

## Evidence

The connected run moves 45.63 metres, reaches wheel angles from -15.92 to +17.18 degrees, and has zero recorded collisions. Its lateral displacement reaches 1.18 metres. Applied CARLA steering agrees with the mapping from recorded physical wheel position to within 1.86e-9.

A matched second run uses the same checkpoint, route, requested angles, and scripted speed with the grip disabled. Peak steering falls from 0.04605 to 0.000007279, a reduction of more than 99.98%. Grip force becomes zero and the resulting lateral trajectory differs by up to 1.183 metres. This intervention supports the causal role of the fly-to-wheel connection for this sequence. It is not a general driving success rate.

The validator checks every camera/world frame, every steering readback, decision/body alignment, and a fresh physical replay driven solely by the recorded neural actions. The fresh replay reproduces every joint position and actuator command exactly in both runs, with zero numerical difference. Compact configurations and results are in `reports/2026-09-09-carla-video/`; full camera frames, neural states, body traces, and output video remain in the ignored run directories and verified local exports.

## Remote execution and reproduction

The capture and body rendering ran on a fresh Runpod Secure Cloud RTX A6000 in US-TX-1, with 48 GB GPU memory, 18 vCPUs, and 71 GB host RAM. The bootstrap, eight existing tests, CARLA archive verification, and checkpoint inference passed on this second host. Neural inference uses CUDA; MuJoCo body rendering uses NVIDIA EGL; CARLA uses offscreen Unreal rendering. Video encoding/compositing runs on the remote CPU. No new training was performed.

The connected capture took 82.9 wall seconds, including model loading and recording, for 24 simulated seconds. Composite rendering took 40.5 seconds. These are capture timings, not a forecast for training visual driving.

After following `docs/reproduce.md` to install dependencies and restore the archived pilot checkpoint and graph, start CARLA and run:

```bash
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl PYTHONPATH=src
.venv/bin/python scripts/capture_carla_cockpit.py
.venv/bin/python scripts/capture_carla_cockpit.py --disable-grip --out runs/carla-cockpit-grip-disabled-v1
.venv/bin/python scripts/validate_carla_cockpit.py
.venv/bin/python scripts/render_carla_cockpit.py
```

The recorder checks the exact checkpoint and graph SHA-256 hashes. The named output directories must not already exist. A newly trained checkpoint is a different experiment; the recorder deliberately rejects it until its provenance is reviewed and configured.

The spending ceiling for this video session was an additional $3, with a three-hour deadline and a $4 reserve. Local and remote shutdown guards were active. The final export and lifecycle receipts record the verified downloads, remaining balance, and termination of the paid Pod. No credit was added.

## Next uncertainty

The fly can follow requested steering angles while its physical wheel drives CARLA. It has not learned to choose those angles from road images, operate pedals as part of this driving loop, or use indicators. Those remain separate experiments with their own success checks.

## Final delivery and cost

The delivered MP4 is `flyhard-carla-cns-fly-16x9.mp4`: 1920 by 1080, 25 fps, 24 seconds, H.264, 69,569,565 bytes. SHA-256: `98155643b14718fb0d4e64b095d142579cb3e7ca25c6f03165e806470c368e74`. All 600 frames decoded successfully after download.

The video session spent approximately $0.24. The original $20 balance now has $19.09 remaining. The Pod was terminated, the account has no remaining Pods, and the API reports $0/hour spending. The export manifest verified 27 files totalling 2,017,230,125 bytes, including the checkpoint and graph used by both runs. No credit was added.
