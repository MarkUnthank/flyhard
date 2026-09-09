# Flyhard

*Six legs. One wheel. One very unusual driving instructor.*

A research experiment to train a neural model built from a fruit fly's measured connectome to operate a simulated body and drive a car in CARLA.

The fly drives a tiny **Flyat**: a battered old Fiat Panda in faded green, with a fly-adapted cockpit and physically operated steering wheel and pedals. See [the vehicle design brief](docs/flyat-design.md).

Intended GitHub home: `MarkUnthank/flyhard`.

## Status

Planning and feasibility stage. No driving capability or training performance has been demonstrated yet. The public repository has not been created.

## The experiment

Camera input → trained connectome-based model → limb actuation → physical contact with steering wheel and pedals → measured control positions → CARLA vehicle motion → new visual input.

The body must causally operate the controls. An animated driver following direct vehicle commands may support development, but does not satisfy the final goal.

The measured connectivity topology is the starting architectural constraint. Training must involve the connectome-based model, including connection strengths and neuronal dynamics where appropriate. Document measured, inferred, fixed, and learned parameters, sensory interfaces, and any separate body controller. This is not a claim to recreate the original fly's mind or biological learning.

## First milestone

Follow the [verifiable experiment plan](docs/experiment-plan.md). Each experiment has a narrow question, an evidence requirement, and a decision before proceeding.

Prepare a bounded pilot on one NVIDIA RTX A6000 using a Runpod on-demand Pod. Begin with a stationary cockpit task, then evaluate the proposed curriculum before integrated driving.

Record training progress, evaluation success, simulation throughput, GPU memory, and billed runtime. Save checkpoints and synchronized neural, body, contact, wheel, and pedal traces. Use the results to decide whether longer training or different hardware is justified. No infrastructure has been provisioned.

## Presentation

Driving footage, cockpit footage, body motion, and computed neuron activations on connectome geometry must come from the same recorded simulation run. Label engineered animation and model-derived activity accurately.

## Open-source preparation

Keep credentials, account-specific configuration, large datasets, checkpoints, and recordings outside version control. Provide reproducible acquisition and setup scripts as development progresses. Preserve source versions, attribution, licenses, and modification records for all third-party data, code, and body assets. Select a license for original code before public release; third-party materials retain their own terms.

## Research starting points

- [MaleCNS dataset and downloads](https://male-cns.janelia.org/download/)
- [FlyVis visual-system models](https://github.com/TuragaLab/flyvis)
- [NeuroMechFly / FlyGym](https://github.com/NeLy-EPFL/flygym)
- [FlyBody](https://github.com/TuragaLab/flybody)
- [FlyGM preprint](https://arxiv.org/abs/2602.17997)
- [CARLA](https://github.com/carla-simulator/carla)

These are research candidates, not yet validated project dependencies.
