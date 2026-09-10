# Three-point-turn quick pilot

A single 400-step run trained a fresh goal-conditioned connectome controller in
136.9 seconds on the retained A6000. It uses the full 165,122-node / 25,563,197-edge
measured graph. Only measured-edge gains and neuron leaks are learned; encoding,
motor decoder and body interfaces stay fixed. Inputs are structured goal/road
geometry, signed velocity, selector position and measured wheel. Outputs are
wheel target, speed magnitude and reverse/neutral/forward logits. No planner,
route phase, time or steering instruction enters learned inference.

Training uses 64 cases with road widths 9.5 or 10.5 m. Eight separate validation
cases select the checkpoint. The eight predeclared held-out cases use a 10 m
road, new seeds, start offsets and goal poses. The planner labels training and
validation only. The training-only teacher selects collision-free F/R/F
Reeds–Shepp paths from pinned rsplan 1.0.10. An early development data draft with
a target-wheel input was stopped and excluded before any held-out evaluation;
V2 was trained from scratch with independently randomized wheel observations.

The frozen gate is a stationary 0.5 s hold within 0.6 m and 12° of the opposite
heading target, an actual forward/reverse/forward sequence with exactly two
direction changes, and no road-boundary crossing or native contact. This is a
small scoped diagnostic, not a broad autonomous-driving benchmark.

## Fast vehicle-model test

| Eight held-out cases | Learned | Reset core |
| --- | ---: | ---: |
| Full gate | 0/8 | 0/8 |
| Road-boundary collisions | 0/8 | 0/8 |
| Mean final position error | 0.985 m | 7.663 m |
| Mean final heading error | 3.854° | 178.882° |
| Mean direction changes | 2.0 | 1.75 |

All eight learned runs made F/R/F and turned to the opposite heading, but stopped
outside the target tolerance. Resetting the learned edge gains and leaks removed
the turn. The simple bicycle model uses a speed/gear interlock and wheel rate
limit; it is explicitly not CARLA or the measured body rig. No controller changes
were made after seeing these held-out results.

Checkpoint SHA-256:
`32ad3ab136737256747f9c341832405aa1e6ae33cb1a7625b03ca09ab4c3f4a9`.

## Reproduction

```sh
PYTHONPATH=src python scripts/prepare_three_point_data.py --out runs/three-point-data
PYTHONPATH=src python scripts/train_three_point.py --data runs/three-point-data \
  --out runs/three-point-policy --steps 400 --batch 24
PYTHONPATH=src python scripts/evaluate_three_point.py \
  --checkpoint runs/three-point-policy/checkpoint.pt.gz --data runs/three-point-data \
  --out runs/three-point-kinematic --count 8
```

Add `--reset-core` for the frozen-core baseline. Native evaluation adds `--native`
and a freshly exported live `--asset`; it reuses the existing passive wheel,
pedals and selector, driven by 28 fly joint targets through fixed IK and speed
regulation. CARLA receives measured physical control positions only. Native
recordings preserve body states, decisions and applied controls at 20 Hz; this
pilot does not render a social video or claim native Unreal fly integration.

The Pod was resumed with a new 30-minute provider timer, local credit guard,
$1 maximum session spend and $4 reserve. No top-up was requested by this run. The headless runtime
requires an EGL-based NVIDIA Vulkan ICD after restart; retained CARLA binaries
were reused without downloading the simulator again.

## Native CARLA result

Both fixed held-out cases made F/R/F through the body-operated controls, but both
crossed the virtual road boundary before reaching the final heading. **0/2
passed.** Mean terminal position error was 5.087 m, heading error 70.872°, duration
17.875 s, with two direction changes each. The boundary crossings were 1.6 cm and
3.2 cm; neither source reported a native collision impulse. The 100% collision
rate here denotes the benchmark's boundary violations, not two impacts.

The native scene is Town10HD_Opt, road 17, four contiguous driving lanes totalling
14 m. The scored corridor is 10 m wide. The first setup attempt crashed while
loading a map and produced no trial. A subsequent scene check rejected a
same-direction-only lane search before any trial; the final search includes
contiguous opposing driving lanes and verifies straight clearance. These are
setup failures, not omitted driving outcomes. No model weights or held-out cases
were changed in response.

The learned recording audit verified 715 consecutive native ticks, the body
clock, measured wheel/pedal/selector values against applied CARLA controls, and
20 recomputed frozen-checkpoint outputs. Maximum applied-control error was
2.98e-8, and maximum recomputed-action error was 1.20e-7. These establish control
causality; they do not make the manoeuvre successful.

The fast-model result has not transferred reliably through the body and native
vehicle dynamics. A follow-up should measure that steering/speed response and
train against the resulting dynamics, with new held-out seeds after any changes.
This run stays frozen. No artificial steering corrections were inserted and no
finished social video was generated.


The matching native reset baseline also passed 0/2, with no meaningful movement
or direction changes, no boundary violations or native impacts, mean position
error 7.234 m and heading error 178.747° after the full 35 s limit. Both conditions
used the same two cases, measured interface and native scene. All four trials
are retained, including failures.

## Validation and preservation

The reset audit verified another 1,400 ticks and 20 recomputed decisions: 2,115
native ticks and 40 model decisions across both conditions. The focused geometry,
parking and recorded-horn tests passed (17 tests); native runs exercise the
corridor search and measured controls. A visual path comparison is in `paths.png`
and copied to `~/Desktop/Flyhard-three-point-turn-pilot.png`.

All 124 data, checkpoint, diagnostic and native-trace files were downloaded and
checksum-verified against the remote copy. The backup receipt lists their hashes.
All Runpod pods were confirmed stopped. Retained storage, old videos, earlier
checkpoints, native-build work and unrelated website changes are preserved.
