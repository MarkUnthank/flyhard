# Flyhard

*Six legs. One wheel. One very unusual driving instructor.*

A research experiment to train a neural model built from a fruit fly's measured connectome to operate a simulated body and drive a car in CARLA.

The planned **Flyat** is a battered old Fiat Panda in faded green, with a fly-adapted cockpit and physically operated steering wheel and pedals. The current CARLA recordings use a stock green Mini Cooper while the Panda shell remains to be built. See [the vehicle design brief](docs/flyat-design.md).

GitHub: [MarkUnthank/flyhard](https://github.com/MarkUnthank/flyhard).

## Status

The first bounded A6000 pilot is complete (2026-09-09). A model retaining 165,122 traced MaleCNS neurons and 25,563,197 measured neuron-pair connections learned to turn a passive wheel through the simulated fly's foreleg.

- Stationary steering: **100/100 held-out targets passed after training; 0/100 before**. One training seed, 600 optimizer updates, 186 seconds of training. The worst final hold error was 4.85 degrees against a predeclared 7.45-degree limit.
- Mechanics: wheel and pedal each passed 20 paired trials with grip/contact interventions. Pedal contact also reproduced on the A6000; fine timestep sensitivity remains documented.
- Infrastructure: actual body rendering and CARLA 0.9.16 offscreen cameras work on the selected Runpod host.
- Connected steering: the saved model now operates the physical wheel **while driving CARLA** through a 24-second instructed sequence. All 600 video frames share the neural/body/CARLA clock. Disconnecting the foot grip removes over 99% of the steering response. See the [video experiment](docs/carla-video-2026-09-09.md).
- Updated recordings use a minimal black layout, actual MaleCNS neuron skeletons and neuropil surfaces, and a passive second foreleg grip. The [calm and faster video report](docs/carla-clean-videos-2026-09-09.md) explains the current setup and reproduction commands.

This is a requested-angle steering skill with engineered interfaces. Visual driving, combined wheel/pedal control, the Panda shell, and three-seed replication remain untested.

The [packaged GPU runtime](docs/runtime-image.md) is published and validated on a fresh Runpod A40. It includes CARLA and the Python/graphics environment, with no installation at startup. Run `python3 deploy/launch.py` from this checkout to launch the tested image with a one-hour limit; your Runpod API key stays in the local `.env`. See the [runtime validation report](reports/2026-09-09-runtime/).

Read the [pilot report](docs/pilot-2026-09-09.md), [measured results](reports/2026-09-09/), [connected steering results](reports/2026-09-09-carla-video/), and [reproduction instructions](docs/reproduce.md).

## The experiment

Camera input → trained connectome-based model → limb actuation → physical contact with steering wheel and pedals → measured control positions → CARLA vehicle motion → new visual input.

The body must causally operate the controls. An animated driver following direct vehicle commands may support development, but does not satisfy the final goal.

The measured connectivity topology is the starting architectural constraint. Training must involve the connectome-based model, including connection strengths and neuronal dynamics where appropriate. Document measured, inferred, fixed, and learned parameters, sensory interfaces, and any separate body controller. This is not a claim to recreate the original fly's mind or biological learning.

## Current experiments and next gate

The September 10 source includes physical indicator control, roundabout capture,
parallel-parking training/evaluation, and the video replay/edit pipeline. Start
with the [source preservation guide](docs/source-preservation-2026-09-10.md) for
entry points and the limits of this snapshot.

The [parking benchmark](reports/2026-09-10-parking/RESULTS.md) used structured
relative geometry and measured wheel, pedal and gear controls. Neither the learned
core nor its reset comparison passed a park in 50 held-out trials. Collision flags
were 10/50 and 12/50 respectively. The proposed gate remains 40/50 collision-free
parks inside the bay, within 0.3 m and 10 degrees. Training changes now need a fresh
held-out set; these outcomes must not be reused for an independent success claim.

The [indicator experiment](reports/2026-09-10-indicators/roundabout-results.md)
records a narrower learned control task. It does not establish visual autonomous
driving. Native CARLA sponsor import/cooking and the smaller persistent runtime's
GPU startup validation remain unfinished; the stored scripts and candidate image
are progress toward those gates.

## Presentation

Driving footage, cockpit footage, body motion, and computed neuron activations on connectome geometry must come from the same recorded simulation run. Label engineered animation and model-derived activity accurately.

Before every recording or finished-video render, download and build the latest live sponsor artwork with `python3 scripts/refresh_live_livery.py`; pass that immutable snapshot as `--asset`. Stale or mismatched artwork now blocks the run. See the [live-livery recording workflow](docs/live-livery-recording.md).

Keep the left/right request indicators, requested angle, measured wheel angle and applied CARLA steering visible in presentation renders. They make the control response readable when the fly's leg movements are subtle. Use the last recorded neural request and the matching camera-frame measurements. Retain the minimal black layout and panel/speed labels.

## Open-source preparation

Original project code is MIT licensed, copyright Mark Unthank. Third-party materials retain their own terms; see [attribution and provenance](THIRD_PARTY.md). Credentials, private account configuration, large data, checkpoints, and raw recordings remain outside Git. Curated public website media and attributed historical model snapshots are included. Acquisition scripts verify the pinned source hashes.

## Research starting points

- [MaleCNS dataset and downloads](https://male-cns.janelia.org/download/)
- [FlyVis visual-system models](https://github.com/TuragaLab/flyvis)
- [NeuroMechFly / FlyGym](https://github.com/NeLy-EPFL/flygym)
- [FlyBody](https://github.com/TuragaLab/flybody)
- [FlyGM preprint](https://arxiv.org/abs/2602.17997)
- [CARLA](https://github.com/carla-simulator/carla)

MaleCNS, FlyGym/NeuroMechFly, and CARLA are exercised dependencies. FlyVis, FlyBody, and FlyGM remain research references and are not part of the current controller.
