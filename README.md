# Flyhard

*Six legs. One wheel. One very unusual driving instructor.*

A research experiment to train a neural model built from a fruit fly's measured connectome to operate a simulated body and drive a car in CARLA.

The fly drives a tiny **Flyat**: a battered old Fiat Panda in faded green, with a fly-adapted cockpit and physically operated steering wheel and pedals. See [the vehicle design brief](docs/flyat-design.md).

Intended GitHub home: `MarkUnthank/flyhard`.

## Status

The first bounded A6000 pilot is complete (2026-09-09). A model retaining 165,122 traced MaleCNS neurons and 25,563,197 measured neuron-pair connections learned to turn a passive wheel through the simulated fly's foreleg.

- Stationary steering: **100/100 held-out targets passed after training; 0/100 before**. One training seed, 600 optimizer updates, 186 seconds of training. The worst final hold error was 4.85 degrees against a predeclared 7.45-degree limit.
- Mechanics: wheel and pedal each passed 20 paired trials with grip/contact interventions. Pedal contact also reproduced on the A6000; fine timestep sensitivity remains documented.
- Infrastructure: actual body rendering and CARLA 0.9.16 offscreen cameras work on the selected Runpod host.

This is a requested-angle steering skill with engineered interfaces. Visual driving, combined wheel/pedal control, the Panda shell, and three-seed replication remain untested. The public GitHub repository has not been created.

Read the [pilot report](docs/pilot-2026-09-09.md), [measured results](reports/2026-09-09/), and [reproduction instructions](docs/reproduce.md).

## The experiment

Camera input → trained connectome-based model → limb actuation → physical contact with steering wheel and pedals → measured control positions → CARLA vehicle motion → new visual input.

The body must causally operate the controls. An animated driver following direct vehicle commands may support development, but does not satisfy the final goal.

The measured connectivity topology is the starting architectural constraint. Training must involve the connectome-based model, including connection strengths and neuronal dynamics where appropriate. Document measured, inferred, fixed, and learned parameters, sensory interfaces, and any separate body controller. This is not a claim to recreate the original fly's mind or biological learning.

## Next milestone

Follow the [verifiable experiment plan](docs/experiment-plan.md). Each experiment has a narrow question, an evidence requirement, and a decision before proceeding.

Keep the A6000. Replicate the steering skill across two additional training seeds, refine and teach the pedal skill, then verify physical control positions driving CARLA on one coordinated clock.

The first pilot saved resumable checkpoints, all held-out scores, source hashes, numerical checks, and synchronized neural/body/wheel recordings. Its approximately 3 GB peak training allocation does not justify a GPU upgrade. Integrated driving throughput has not been measured.

## Presentation

Driving footage, cockpit footage, body motion, and computed neuron activations on connectome geometry must come from the same recorded simulation run. Label engineered animation and model-derived activity accurately.

## Open-source preparation

Original project code is MIT licensed, copyright Mark Unthank. Third-party materials retain their own terms; see [attribution and provenance](THIRD_PARTY.md). Credentials, account configuration, large data, checkpoints, and videos are excluded from Git. Acquisition scripts verify the pinned source hashes.

## Research starting points

- [MaleCNS dataset and downloads](https://male-cns.janelia.org/download/)
- [FlyVis visual-system models](https://github.com/TuragaLab/flyvis)
- [NeuroMechFly / FlyGym](https://github.com/NeLy-EPFL/flygym)
- [FlyBody](https://github.com/TuragaLab/flybody)
- [FlyGM preprint](https://arxiv.org/abs/2602.17997)
- [CARLA](https://github.com/carla-simulator/carla)

MaleCNS, FlyGym/NeuroMechFly, and CARLA are exercised dependencies. FlyVis, FlyBody, and FlyGM remain research references and are not part of the current controller.
