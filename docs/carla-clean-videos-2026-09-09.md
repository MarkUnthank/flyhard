# Flyhard: calm and faster recordings

These recordings update the first connected steering demo with a minimal black 16:9 layout: CARLA on the left, anatomical neural activity above the physical fly on the right. The overlay contains only the panel labels and measured vehicle speed. The calm run was recorded first, followed by a faster, more frequent steering sequence. Both play at normal simulation speed.

## What changed

The neural controller remains the original seed-123 steering checkpoint. It outputs seven left foreleg joint targets. That foreleg transmits force through an assisted grip to a passive wheel, whose measured angle determines CARLA steering. A second, passive grip attaches the right foreleg to the opposite rim. Its position servos are disabled, so the wheel moves that leg mechanically. The second grip changes the physical load; it does not add another learned skill.

Requested wheel angles and vehicle speed are scripted. The policy has no camera input, CARLA autopilot is disabled, and the supported cockpit does not receive vehicle acceleration forces. The car remains the stock green Mini Cooper proxy; the battered Panda shell, learned pedals and indicators are still separate work.

The old soma point cloud has been replaced with actual MaleCNS v1.0 neuron skeletons and neuropil surfaces from [the public dataset](https://male-cns.janelia.org/download/) linked by [Google Research](https://research.google/blog/a-connectomics-milestone-mapping-the-complete-male-fruit-fly-brain/). The view draws a fixed subset of 512 neurons in 114 neuropil regions. Half the neurons in each class were selected by strongest states in the previous calm recording, and half by seeded random sampling. The full model still computes all 165,122 retained neurons.

Orange and blue show positive and negative computed model states, not measured biological spikes. Each neuron uses a fixed range from the 95th percentile of its absolute states, sampled every fourth decision over the episode, with a 1e-5 floor and an asinh mapping. This makes weaker responses visible without inventing activity. Brightness indicates changes within a neuron and cannot be compared between neurons or recordings. Zero states remain gray. Source URLs, geometry transforms and hashes are saved in the geometry manifest; third-party attribution remains in `THIRD_PARTY.md`.

## Recording and verification

Neural decisions run at 20 Hz, joint commands at 200 Hz, body physics at 20 kHz and CARLA at 25 Hz. The coordinator reads the wheel at each interval's start, applies its steering mapping to CARLA, and advances both simulators to the same endpoint. The anatomical layer, physical fly and camera all use that recorded frame map. VTK and MuJoCo render in separate GPU processes because their EGL context lifetimes conflict in one process.

The calm episode has 600 frames over 24 seconds. It travels 45.58 metres, peaks at 7.11 km/h and records zero collisions. A matched grip-disabled episode reduces peak steering by more than 99.97%. Replaying the saved neural actions in a fresh physical simulation reproduces all recorded joint positions and commands exactly in both episodes. Maximum camera/body clock mismatch is below one microsecond.

The faster episode peaks at 60.76 km/h. A parked motorcycle is contacted at 5.96 seconds, followed by a pole at 12.36 seconds. The full recording lasts 24 seconds; the delivered cut ends at 14 seconds to remove the stationary tail. It retains the first 350 consecutive frames of the complete composite, including both collisions, with no panel retiming. Its 37 contact events comprise one motorcycle event and 36 repeated pole contacts; they are not 37 separate crashes. The full recording retains all 524 repeated contact events for inspection.

Fresh physical replay of the faster episode also reproduces all 4,800 joint-position and command samples exactly. Every camera/world frame and steering readback passes, with maximum steering-mapping error below 1.9e-9. This validates the recorded causal chain; it does not establish road awareness or safe driving.

Capture and rendering use a Runpod Secure Cloud A40 with 48 GB GPU memory in CA-MTL-1. The A6000 was unavailable at launch. The observed total rate is $0.518/hour including configured storage. These are historical measurements, not current availability or pricing guarantees. Neural inference uses CUDA, CARLA uses Epic-quality offscreen Unreal rendering, and both anatomical and fly rendering use NVIDIA EGL. Encoding and composition run on the remote CPU. No new training was performed.

Capture takes 92.25 wall seconds for the calm recording and 94.16 seconds for the faster recording. Anatomical rendering takes 22.11 and 24.34 seconds; subsequent fly rendering/composition takes 44.99 and 47.09 seconds. These are recording and rendering measurements, not training-time estimates. Loading each recorded array once avoids repeatedly reading the complete neural matrix from NFS for every frame.

## Reproduction

Follow `docs/reproduce.md` to install the simulation and restore the original pilot checkpoint and graph. Install the visualization extra as well:

```bash
.venv/bin/pip install -e '.[video]'
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl PYTHONPATH=src
bash scripts/start_carla.sh > work/carla-server.log 2>&1 &
.venv/bin/python scripts/capture_carla_cockpit.py --out runs/carla-calm-v2 --support-hand
.venv/bin/python scripts/capture_carla_cockpit.py --out runs/carla-calm-grip-disabled-v2 --support-hand --disable-grip
.venv/bin/python scripts/validate_carla_cockpit.py --run runs/carla-calm-v2 --control runs/carla-calm-grip-disabled-v2
.venv/bin/python scripts/acquire_cns_geometry.py --selection-trace runs/carla-cockpit-v1/neural-trace.npz
.venv/bin/python scripts/render_carla_cockpit.py --run runs/carla-calm-v2
.venv/bin/python scripts/capture_carla_cockpit.py --out runs/carla-new-yorker-v1 --support-hand --mode new-yorker --speed 18
.venv/bin/python scripts/validate_carla_cockpit.py --run runs/carla-new-yorker-v1
.venv/bin/python scripts/render_carla_cockpit.py --run runs/carla-new-yorker-v1
.venv/bin/python scripts/export_carla_video.py --run runs/carla-new-yorker-v1 --end-frame 350
```

Use new output directories for new captures. The geometry selection references the archived first recording to keep the neuron subset identical across both new videos; another selection trace makes a different display subset. Assembled anatomy is about 113 MB, with an additional cached display surface of about 17 MB. Raw downloads can be reconstructed from the acquisition manifest.

After copying the complete runs, geometry and export manifest, verify the content hashes and decode both videos with `scripts/qc_carla_video.py --run <directory>`. Terminate the Pod only after local exports are verified. Never add account credit automatically.

For the shorter export, run:

```bash
.venv/bin/python scripts/qc_carla_video.py --run runs/carla-new-yorker-v1 --video social-16x9.mp4 --metrics social-export.json --output runs/carla-new-yorker-v1/social-video-qc.json
```

## Delivery and shutdown

Both delivered files are silent H.264 MP4s at 1920 by 1080 and 25 fps. Every delivered frame decoded successfully after download, every panel remained nonblank, and every panel changed during each recording. The full 24-second faster recording also passed its separate decode check.

| File | Duration | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `flyhard-calm-clean-16x9.mp4` | 24 s | 30,227,696 | `80e6888cf42a5740f852c6c43c7a336ea93a97896d135a22c03b462023c47b03` |
| `flyhard-new-yorker-16x9.mp4` | 14 s | 21,112,392 | `0d0e330f3f33e0cae70deeb0cba80465d395e160adcd21cf6a4f64ebf16d85ca` |

The export manifest verifies 65 files totalling 2,383,418,764 bytes, including both complete episodes, the grip intervention, original checkpoint and graph, and assembled anatomical geometry. The Pod was terminated only after these exports and final videos passed local checks. The account readback shows no remaining Pods and $0/hour spending. This session used about $0.51, leaving about $18.55 from the original $20. No credit was added.

Compact evidence, source hashes, the package inventory and lifecycle receipt are in `reports/2026-09-09-clean-videos/`. Full states and video layers remain in the ignored run directories. The next scientific work is to train choices from road input or introduce learned pedal/indicator operation; the video refresh does not resolve those uncertainties.
