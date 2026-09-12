# Dynamic horn videos

The requested edit contains moving approaches to traffic lights, a quiet drive
through an already-green light, and two side-road pull-outs in different native
CARLA layouts. A separate road-rage clip adds repeated encounters with moving
cars. The green Mini carries a freshly exported production livery. Narrative
subtitles are removed; request, wheel, CARLA steering, horn and site readouts stay
visible.

## Controller and claim

One connectome-constrained rate model emits fourteen joint targets: seven left
foreleg joints for the wheel and seven right foreleg joints for the horn button.
Only its measured-edge gains and neuron leaks are trained. Sensory assignments,
motor readout and generic random features are frozen. The core has 165,122 nodes
and 25,563,197 measured edges. This is a simplified rate model, not a biological
simulation of a living fly.

Inputs are structured traffic state, current requested wheel angle and an explicit
road-rage task cue. Four seconds of raw traffic observations are sampled at eleven
fixed lags, with denser recent samples. Historical steering requests are excluded
from the horn context. There is no scenario name, clock, teacher label or
precomputed green-transition flag in inference.

CARLA BasicAgent supplies the route requests and longitudinal controls. Other
vehicles use native CARLA physics. The fly's measured wheel position supplies
applied steering; the measured horn button supplies all beep events. Cut-in and
road-rage scenes deliberately disable braking as scenario direction. They do not
demonstrate a learned decision to honk instead of braking, learned navigation, or
visual autonomous driving.

The button has a fixed switch margin: close at 55% travel and open below 45%.
This suppresses contact chatter without creating an onset below the press
threshold. The forefoot grips, servos and switch are engineered interfaces.

The model runs at 10 Hz, joints receive commands at 300 Hz, and body physics runs
at 60 kHz. Native cameras and recorded body states share a 60 Hz clock. Neural
images hold the actual corresponding model sample. Sponsor meshes use the native
camera and lossless depth; they remain a compositing layer, not native Unreal
vehicle materials.

## Scenarios and checks

| Scene | Required observed result |
| --- | --- |
| Empty road | Approach, stop on red, depart on green; no horn |
| Arrive on green | Moving lead and fly car drive through; no horn |
| Wait behind a car | Both stop on red; horn follows green; lead moves after physical press |
| T-junction pull-out | Side-road car joins the route; sustained horn; zero commanded braking |
| Four-way pull-out | Same problem at a different junction; sustained horn; zero commanded braking |
| Road rage | At least three encountered cars, horn while near every encountered car, continuing motion |

Lane presence is measured by projecting actual vehicle positions onto the provided
route centreline. This handles curved junctions without making a lead car vanish
when the fly corrects its steering. Nearby-car distance is Euclidean.
The lamp is selected from native stop waypoints matching that scene's approach;
directed cut-in/rage routes hold their own lamps green. An earlier capture bound
the observation to the original light-scene junction while the visible local
lamps stayed red. Those captures were rejected and retained as development data.

Development recordings and failed checkpoints are retained. An early controller
honked before green; another briefly honked on an empty road at the transition.
These remain failures of the quiet-case requirement. The final direction accepts
genuine imperfect takes; retaining a false chirp does not turn it into a pass.
The training sampler balances short green-light presses with longer positive
holds and focuses some negative examples around potential event times.

Structured held-out trials use disjoint seeds with the same parameter ranges.
They are not held-out CARLA roads or general traffic benchmarks. Learned-core
reset and disconnected-foot baselines must be reported alongside learned results.

## Reproduction

Run commands from the repository root with the graph in `data/graph-traced-v1`
and the documented GPU Python environment. The published runtime image used for
this session required its recorded EGL/dependency setup; native packaging remains
deferred.

```sh
PYTHONPATH=src python scripts/train_driving_horn.py --out runs/driving-horn --steps 1500
PYTHONPATH=src python scripts/evaluate_driving_horn.py \
  --checkpoint runs/driving-horn/checkpoint.pt.gz --out runs/driving-horn-evaluation
```

Before **each** recording and render, including previews, run
`python3 scripts/refresh_live_livery.py`, transfer its immutable archive, and pass
that directory with `--asset`. Each capture and render verifies the live revision.

```sh
PYTHONPATH=src python scripts/capture_dynamic_horn.py \
  --checkpoint runs/driving-horn/checkpoint.pt.gz --kind cut_in_t \
  --seconds 11 --asset work/live-livery/SELECTED_EXPORT --out runs/cut-in-t
PYTHONPATH=src python scripts/render_dynamic_horn.py \
  --runs runs/cut-in-t --asset work/live-livery/FRESH_SELECTED_EXPORT \
  --out runs/horn-edit --preview-only
```

The full renderer accepts one `start:end` range per source. It cuts recorded
frames without fabricating control errors or neural samples. It prepares
independent source layers in separate processes, then composes the synchronized
body and readouts. Exact camera/depth preview frames avoid decoding an entire
take merely to inspect placements.

`scripts/verify_dynamic_horn_video.py --run runs/horn-edit` checks full MP4 decoding,
1080p60 timing, source-frame continuity, the shared causal clock, a single frozen
checkpoint and silence outside measured horn intervals. Preserve raw captures,
model checkpoints, current source receipts and sponsor snapshots with the exports.
Export integrity is independent of behavioural perfection: a genuine messy take
can be rendered with its actual score intact. No horn events or steering errors
are inserted to improve the story.

The pull-out and road-rage sources also record native cabin RGB and lossless depth
at the same 60 Hz frame numbers. Sustained physical presses motivate the interior
cuts: a short exterior reaction, a close view of the actual foreleg/button state,
then the exterior again. The calibrated MuJoCo fly is depth-composited into that
native cabin and the image is cropped for readability. This is the same recorded
body state, not a newly animated press or a native Unreal fly asset.

## Recorded horn and attribution

The sound is [05 Horn.wav by 15HPanska_Ruttner_Jan](https://freesound.org/people/15HPanska_Ruttner_Jan/sounds/461679/),
released under CC0. The original recording, source URL, license and checksum are
in `assets/audio`. A recorded attack and a crossfaded segment of the real steady
horn sustain longer physical presses. No oscillator creates the horn sound.

Touching or overlapping measured press spans are merged at sample boundaries
before laying out the recording, so an edit within a continuous hold does not
introduce a fresh horn attack. `scripts/remux_dynamic_horn_audio.py` can finalize
audio while copying the compressed picture stream unchanged. It still requires
a fresh live-livery export and refuses reuse if the revision, layout, texture or
panel checksums differ. A changed sponsor requires a fresh visual render.

Retain CARLA 0.9.16 / CVC / Universitat Autònoma de Barcelona, MaleCNS / Janelia,
and NeuroMechFly / FlyGym / EPFL credits. Sponsor artwork remains the property of
its owners and is not relicensed under the software license.
