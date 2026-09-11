# Attribution and provenance

Original Flyhard code: Copyright 2026 Mark Unthank, MIT license. This does not relicense third-party data, simulators, or assets. No affiliation or endorsement is implied.

## MaleCNS v1.0

The measured connectivity, annotations, and soma locations come from the MaleCNS collaboration: FlyEM at HHMI Janelia, University of Cambridge, MRC Laboratory of Molecular Biology, and Google Research. The [official download page](https://male-cns.janelia.org/download/) links the [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/).

Changes: retain annotations with `status == "Traced"`; retain edges between those IDs; aggregate neuron-pair counts; store a postsynaptic-row sparse matrix; normalize incoming counts; add trained gains and rate dynamics. The explicit filter produces 165,122 neurons and is not the published 166,691-neuron census. IDs and exclusions are saved. The model is an engineering interpretation, not supplied biological dynamics.

The first pilot neural replay projected measured soma coordinates. The current video renderer instead uses actual MaleCNS neuron skeletons and neuropil meshes from the public data sources linked above. It displays a fixed, class-stratified subset of 512 neurons within 114 measured neuropil compartments. Skeleton coordinates are converted from nanometres to micrometres and downsampled with branch endpoints preserved. Surface meshes are simplified for display. Recorded signed model states color the selected neurons; they are not observed biological spikes. Each neuron has a fixed color range derived from its sampled absolute states over that episode, with a floor of 1e-5. Orange denotes positive states and blue denotes negative states; brightness is relative within a neuron and cannot be compared between neurons or videos. Zero states remain gray. Download URLs, selection rules, and source hashes are retained in the geometry manifest. Graph-derived artifacts and checkpoints containing connectivity must retain this attribution and the data license.

Sources and SHA-256 hashes are stored in `reports/2026-09-09/graph-manifest.json`. Transmitter predictions were acquired but do not set excitation/inhibition in the present unsigned connection model.

## FlyGym / NeuroMechFly

[FlyGym](https://github.com/NeLy-EPFL/flygym) 2.1.0, commit `38c8ec61034cd59bc5ba0de20688d4a3c0000d60`, provides the NeuroMechFly body, meshes, anatomy helpers, and upstream experimental motion example. Its pinned [repository license](https://github.com/NeLy-EPFL/flygym/blob/38c8ec61034cd59bc5ba0de20688d4a3c0000d60/LICENSE) and package metadata specify Apache 2.0. Keep the upstream license and notices with any redistribution of those materials.

The upstream package is installed unchanged. Flyhard constructs a supported seat, joint servos, a passive steering wheel, a disclosed forefoot grip constraint, and a passive spring pedal with an engineered contact sole. E00 replays upstream motion targets. E02 uses diagnostic inverse kinematics. E03 instead applies the trained connectome policy's joint commands. These stages must not be mislabeled.

The two-foreleg video rig adds a passive right forefoot grip on the opposite rim. Its position servos are disabled; the second foreleg follows the wheel mechanically. The learned policy still controls the left foreleg only. This is an engineered supporting grip, not a second newly learned skill.

## Geist typeface

The minimal video overlay uses Geist, sourced from the [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/geist). The font is distributed under the SIL Open Font License; the original license and copyright notices are retained in `assets/fonts/Geist-OFL.txt`.

## MuJoCo, PyTorch, CARLA

MuJoCo 3.9.0 provides body/contact physics; PyTorch 2.8.0+cu128 provides the trained graph. They are installed dependencies, not vendored source. Preserve their distributed licenses if bundling them.

CARLA 0.9.16 is downloaded from its official release server. [CARLA source](https://github.com/carla-simulator/carla/blob/0.9.16/LICENSE) is MIT licensed; Unreal Engine and distributed content have their own terms. The simulator is not included in this repository. The Mini model and derived sponsor/billboard assets under `apps/mini-livery/` retain the CARLA content attribution and terms documented in that directory; they are not relicensed as Flyhard code. The current clips use a green Mini Cooper proxy, not the eventual Flyat.

## Flyat

The user-supplied stock photograph is a design reference only and is not included in the repository. No Panda mesh, stock texture, logo, or likeness asset has been acquired or redistributed. The final worn green Panda-inspired shell remains to be built with documented asset provenance.

## Native integration patches

`deploy/native/carla-native.patch` and `carla-movable-props.patch` modify CARLA's
MIT-licensed source. Its copyright/license notice is retained in
`deploy/native/CARLA-LICENSE`. The full simulator, Unreal source tree, editor
binaries, content archives and private build workspace remain outside Git.

`deploy/native/engine-lifecycle.patch` is a small Unreal Engine patch snippet
(16 code/context lines) supplied for supporting the FBX shutdown fix. The one-line
USD startup guard in `patch_editor_python.py` is also an engine-specific patch.
These snippets retain Epic's rights and are not covered by Flyhard's MIT grant.
Applying or building them requires separately licensed access to the pinned
engine. See [Unreal Engine EULA, section 5(a)(ii)](https://www.unrealengine.com/eula/unreal).
Native import, cooking and simulator validation remain unfinished.

## Mozart recording and sponsor artwork

The Mozart recording in `assets/music/mozart-k525/` includes its source, public-domain
status and checksum in that directory. The recording status was checked separately
from the composition. Sponsor names and artwork remain their owners' property;
owner-approved inclusion does not relicense them under MIT or imply endorsement.
Historical model snapshots are retained for provenance; refresh the live livery
before a new recording unless the user explicitly requests an edit of existing
footage with its original artwork.
