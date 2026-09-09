# Attribution and provenance

Original Flyhard code: Copyright 2026 Mark Unthank, MIT license. This does not relicense third-party data, simulators, or assets. No affiliation or endorsement is implied.

## MaleCNS v1.0

The measured connectivity, annotations, and soma locations come from the MaleCNS collaboration: FlyEM at HHMI Janelia, University of Cambridge, MRC Laboratory of Molecular Biology, and Google Research. The [official download page](https://male-cns.janelia.org/download/) links the [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/).

Changes: retain annotations with `status == "Traced"`; retain edges between those IDs; aggregate neuron-pair counts; store a postsynaptic-row sparse matrix; normalize incoming counts; add trained gains and rate dynamics. The explicit filter produces 165,122 neurons and is not the published 166,691-neuron census. IDs and exclusions are saved. The model is an engineering interpretation, not supplied biological dynamics.

The neural replay projects measured soma coordinates and colors them with computed model states. It displays a fixed sample of 12,000 of 140,024 retained neurons with soma annotations. It does not synthesize axons or represent rate states as observed spikes. Graph-derived artifacts and checkpoints containing connectivity must retain this attribution and the data license.

Sources and SHA-256 hashes are stored in `reports/2026-09-09/graph-manifest.json`. Transmitter predictions were acquired but do not set excitation/inhibition in the present unsigned connection model.

## FlyGym / NeuroMechFly

[FlyGym](https://github.com/NeLy-EPFL/flygym) 2.1.0, commit `38c8ec61034cd59bc5ba0de20688d4a3c0000d60`, provides the NeuroMechFly body, meshes, anatomy helpers, and upstream experimental motion example. Its pinned [repository license](https://github.com/NeLy-EPFL/flygym/blob/38c8ec61034cd59bc5ba0de20688d4a3c0000d60/LICENSE) and package metadata specify Apache 2.0. Keep the upstream license and notices with any redistribution of those materials.

The upstream package is installed unchanged. Flyhard constructs a supported seat, joint servos, a passive steering wheel, a disclosed forefoot grip constraint, and a passive spring pedal with an engineered contact sole. E00 replays upstream motion targets. E02 uses diagnostic inverse kinematics. E03 instead applies the trained connectome policy's joint commands. These stages must not be mislabeled.

## MuJoCo, PyTorch, CARLA

MuJoCo 3.9.0 provides body/contact physics; PyTorch 2.8.0+cu128 provides the trained graph. They are installed dependencies, not vendored source. Preserve their distributed licenses if bundling them.

CARLA 0.9.16 is downloaded from its official release server. [CARLA source](https://github.com/carla-simulator/carla/blob/0.9.16/LICENSE) is MIT licensed; Unreal Engine and distributed content have their own terms. The simulator and stock vehicle assets are not included in this repository or relicensed as Flyhard code. The smoke clip uses a stock green Mini Cooper proxy, not the eventual Flyat.

## Flyat

The user-supplied stock photograph is a design reference only and is not included in the repository. No Panda mesh, stock texture, logo, or likeness asset has been acquired or redistributed. The final worn green Panda-inspired shell remains to be built with documented asset provenance.
