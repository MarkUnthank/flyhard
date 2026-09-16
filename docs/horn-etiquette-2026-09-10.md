# Horn etiquette: September 10, 2026

The requested behaviour is deliberately impatient: stay quiet with nobody ahead,
stay quiet when arriving at an already-green light, and beep immediately after
watching red become green behind a stopped car. The controller learned this narrow
task and the 25-second CARLA edit demonstrates all three cases. The one recorded
beep begins 0.15 seconds after the actual green light and lasts 0.65 seconds.

The final video is `Flyhard-horn-etiquette.mp4`, 1920×1080, 60 fps, 1,500 frames,
25 seconds, H.264 Constrained Baseline with stereo AAC. Its SHA-256 is
`0b84888c25c800e9f5f198c2336ac57fbead4e30b7ee402a3eb0e61278218d54`.
The local Desktop copy was checked against this hash. This verifies the handoff
file, not completion of iCloud synchronization.

## What was learned and what was engineered

The model retains the graph of 165,122 traced MaleCNS neurons and 25,563,197
neuron-pair edges. Training changes edge gains and neuron leak parameters. It is an
unsigned, count-normalized rate model; it does not recreate biological learning,
neurotransmitter dynamics, or a fly's mind.

Six structured observations enter inference: red, green, same-lane car presence,
gap, lead speed and ego speed. An engineered rolling buffer supplies 11 observations
at 10 Hz (one second of history). Initial padding repeats the first observation, so
arriving on green does not invent an earlier red light. Generic frozen random
features mix those observations before a fixed sensory interface. No scenario ID,
elapsed time, teacher label or explicit red-to-green transition flag enters the
policy. The network runs four recurrent steps from zero on each decision; the
history buffer, rather than learned recurrent memory, carries the past.

A random motor decoder is calibrated once using balanced training observations,
then held fixed. Its seven outputs command the right foreleg's joints. The trained
parameters are all inside the connectome core. Calibration, sensory/motor
populations, joint servos, the supervised target trajectory and observation buffer
are engineered interfaces, not learned biological capabilities.

The fly presses a passive spring-return button through an engineered forefoot point
grip. There is no button actuator. Button travel of at least 55% is the only source
of beep events; the synthesized sound does not read the light or scenario label.
The button moves 0.28 mm. Physics runs at 60 kHz, motor commands at 300 Hz, and camera
and control measurements at 60 Hz. The left foreleg holds the wheel near zero.
This rig does not simultaneously operate the indicator stalk or parking pedals.

CARLA provides structured observations. Approach and braking are conventional;
the measured wheel angle supplies steering around a fixed zero-angle request.
This is not visual autonomous driving. The experiment also does not establish that
the measured connectome topology is better than a small conventional network.

## Training and held-out evaluation

One seed (501), 900 Adam updates, batch size 24 and learning rate 0.04 took 555.1
seconds wall time on an NVIDIA RTX A6000. Validation loss fell from 0.20321 to
0.00536. The first gradient audit found finite, nonzero gradients on 3,052,285 edge
gains and 23,485 neuron leaks. Frozen interfaces were unchanged through optimization.
Peak PyTorch allocation was 3.04 GB; that excludes the simulator and renderers.

Training uses 40 cases per family, gaps of 3–6 m and transition times of 1.5–3 s.
Validation and test use disjoint seeds with gaps of 6.5–9.5 m and transition times
of 3.2–4.4 s. The six families are waiting for green, nobody ahead, arrival on green,
remaining red, a car leaving before green and a car in another lane. These are
synthetic structured-state sequences evaluated through the physical MuJoCo rig;
they are not 180 independently randomized CARLA traffic scenes.

The frozen checkpoint is
`4545700c58f5230a2f9719d14b66a706f1a2794a3287be72a84a5be67cf31bf2`.
It was not changed after observing the test results or CARLA recordings.

The final measurement uses 180 held-out cases, ten seconds each, measured at 60 Hz.
The declared gate is at least 90% timely single-beep positives and at most 5%
false-beep episodes in each negative family. A positive must start within 0.8 s,
have exactly one press onset, contain no early beep, and release within 1.6 s.

| Learned condition | Correct / trials | Detail |
| --- | ---: | --- |
| Waiting behind a car, then green | 28 / 30 | All reacted promptly; two had a second press onset |
| Nobody ahead | 30 / 30 | Silent |
| Arriving on green | 30 / 30 | Silent |
| Light remains red | 30 / 30 | Silent |
| Car leaves before green | 30 / 30 | Silent |
| Car is in another lane | 30 / 30 | Silent |

Mean first reaction was 0.1186 s, maximum 0.1612 s. Seeds 130009 and 130021 each
crossed the button threshold twice, about 0.633 s apart, and count as failures.
No debounce, relabelling, retraining or selection was applied to hide them.
This passes the scoped gate with observed rates of 93.3% single-beep positives
and 0/150 false-beep negative episodes. Thirty trials per family do not establish
a population-wide false-positive bound or broad traffic competence.

The initial six-second, 20 Hz evaluation reported 30/30 positive successes. The
stronger 60 Hz measurement caught two extra press onsets, so the 28/30 result above
supersedes that earlier success rate. It uses the same held-out cases and checkpoint,
not a fresh independent replication. Both raw evaluations are retained.

The comparison conditions reset edge gains and leaks to their initialized values,
or replay the learned motor commands with both forefoot control grips disconnected.
The latter removes both wheel and horn grip constraints; it is not an isolated
right-foreleg intervention. Final condition totals and every trial are stored in
the [public report directory](../reports/2026-09-10-horn/).

| Comparison at 60 Hz | Timely single-beep positives | Quiet negative episodes |
| --- | ---: | ---: |
| Trained core, grips attached | 28 / 30 | 150 / 150 |
| Core reset to initialization | 0 / 30 | 150 / 150 |
| Learned commands, control grips disconnected | 0 / 30 | 150 / 150 |

Both interventions stayed quiet in all 180 of their episodes. The complete
540-trial evaluation took 1,325 seconds. These interventions support dependence
on learned core parameters and the mechanical connection in this rig; they do
not establish a benefit from connectome topology over alternative architectures.

## Actual CARLA episodes and video evidence

The three final captures use the same frozen policy, Town03, a green Mini and a
stationary lead car where applicable. Each episode keeps its native RGB camera,
lossless packed depth, separate traffic-light camera, CARLA recorder, body state,
joint commands, model activations and structured observations.

| Episode | Duration / frames | Measured beeps |
| --- | ---: | ---: |
| Empty lane, red becomes green | 6 s / 360 | 0 |
| Approach behind a car while already green | 7 s / 420 | 0 |
| Wait behind a car, red becomes green | 10 s / 600 | 1 |

The positive light becomes green at 3.616667 s and button travel crosses threshold
at 3.766667 s. Maximum body/camera clock error is below one microsecond. The edit
uses every frame of these three episodes in order, followed by two seconds of
credits. Its only beep spans output time 16.75–17.40 s. The uncompressed source
audio is exactly silent outside the measured press interval.

The first capture batch was invalid: the scene harness rewrote all lamps to red
before setting the intended lamp green on every frame. CARLA's asynchronous state
updates exposed those unintended transitions to both the neural observations and
the camera. The scene setter now writes only when its requested state changes.
A regression check rejects transient red observations in an already-green scene,
and checks both neural and displayed light histories. The original invalid batch
is retained; the model was not retrained to compensate for that harness bug.

The final render refresh used live sponsor revision 21, layout 5, exported at
2026-09-10 19:13:37.346 UTC. It includes all seven paid placements in that snapshot.
The exact sponsor surfaces use their existing UVs, alpha and transformed artwork.
They are composited against native CARLA camera matrices and depth, not imported
Unreal materials. Left-door and rear placements were inspected. A manifest and
preflight receipt accompany the export; later purchases require a fresh export.

All three panels share the recorded causal clock. Neural colors show computed
model activity on measured CNS anatomy, held at the last 10 Hz decision. The body
replays the recorded 60 Hz state. No movement, activation, mistake or beep was
invented for the edit. Request, steering, stalk and button readouts and
`thedrivingfly.com` remain visible. The horn sound is original two-tone synthesis.
CARLA/CVC/UAB and MaleCNS/FlyGym credits remain in the video and repository.

## Reproduction

Use the graph acquisition and GPU environment documented in
[reproduce.md](reproduce.md) and [runtime-image.md](runtime-image.md). The pinned
graph SHA-256 is
`eff4093bf53c4dd17d7ee4f2f838f6ae5ede70570f9a91317dd8824cca5c771d`.
Large data, checkpoints, recordings, account credentials and provider logs are
excluded from Git. The source and compact public evidence are preserved in PRs.

```sh
export PYTHONPATH=src
python scripts/check_horn_rig.py --out work/horn-mechanics
python scripts/train_horn.py --mechanics work/horn-mechanics --out runs/horn-policy --steps 900
python scripts/evaluate_horn.py --checkpoint runs/horn-policy/checkpoint.pt.gz \
  --out runs/horn-held-out --split test --per-kind 30 --seconds 10 \
  --conditions learned reset_core disconnected --workers 8
```

Before **each** capture or finished render, run `scripts/refresh_live_livery.py`
and use that invocation's immutable `asset` from `work/latest-livery.json`.
Transfer the archive with `tar --no-same-owner` when using a remote GPU. Commands
verify current production artwork before starting; do not use a stale historical
asset path from this report. The CARLA server must be owned by this experiment.

```sh
python scripts/capture_horn.py --checkpoint runs/horn-policy/checkpoint.pt.gz \
  --asset "$HORN_ASSET" --kind no_car --seconds 6 --out recordings/horn/no-car
# Refresh artwork before the next capture and update HORN_ASSET.
python scripts/capture_horn.py --checkpoint runs/horn-policy/checkpoint.pt.gz \
  --asset "$HORN_ASSET" --kind arrive_green --seconds 7 --out recordings/horn/arrive-green
# Refresh artwork before the next capture and update HORN_ASSET.
python scripts/capture_horn.py --checkpoint runs/horn-policy/checkpoint.pt.gz \
  --asset "$HORN_ASSET" --kind wait_then_green --seconds 10 --out recordings/horn/wait-green
# Refresh artwork before this finished render and update HORN_ASSET.
python scripts/render_horn.py --runs recordings/horn/no-car recordings/horn/arrive-green \
  recordings/horn/wait-green --asset "$HORN_ASSET" --geometry data/cns-geometry-v1/geometry.npz \
  --out recordings/horn-edit
```

Sponsor-road, CNS and body rendering use separate processes so one EGL library
cannot destroy another renderer's shared context. On the selected A6000 host,
headless Vulkan required an ICD referencing `libEGL_nvidia.so.0`, an explicit
NVIDIA EGL vendor file, `libglu1-mesa`, and PyOpenGL 3.1.10. Pyrender must be installed
with `--no-deps` to avoid downgrading PyOpenGL. Actual NVIDIA rendering was checked
for CARLA, MuJoCo, VTK and the sponsor renderer; the initial Mesa fallback was
rejected. `FLYHARD_EGL_DEVICE_INDEX=0` selects VTK's registered GPU on this host.
These host repairs are not yet incorporated into the published runtime image.
Native Unreal integration and runtime packaging remain deferred.

The launch client accepts bounded per-session runtime, reserve, spend and hourly
limits. This run used a $2 cap and $4 reserve, without a top-up. The retained-Pod
resume helper is diagnostic: capacity was unavailable on the older hosts, so a
successful resume remains unverified. Existing startup deadline arguments must
be reconciled before using a previously configured image again.

## Next useful experiment

Keep this checkpoint and test set frozen. A follow-up can investigate the two
release-time threshold recrossings on development data, then use new held-out
seeds for an independent evaluation. No added steering antics are needed for the
current joke. Vision, moving traffic, different intersections and joint control
of horn, steering, gears and pedals remain separate untested tasks.
