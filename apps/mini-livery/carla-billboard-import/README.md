# Native CARLA billboard handoff

**Status: interchange assets verified; NOT ready for a CARLA recording rerun.**
No Unreal import, Linux cooking, installation or native camera test has been completed.

## Approved design

The approved Blender model is `../taxi-billboard-smaller/taxi-billboard.blend`.
It reduces the original sign by 15%: core 1.4025 m wide by 0.408 m tall.
The existing roof placement `ad-59` occupies both billboard faces. It remains one
sponsor placement, with production revision 12 artwork at the time of export.

`SM_TaxiBillboardFrame.fbx` contains 17 structural meshes, excluding the studio
floor and car. `SM_TaxiBillboardAd59.fbx` contains one separate advertising mesh
with two opposing faces and one `M_RoofAd59` material. `ad-59.png` is the unchanged
live texture, also embedded in the artwork FBX. Retain its alpha and the supplied
UVs; do not apply artwork transforms a second time.

`export-receipt.json` records source hashes, dimensions and round-trip errors.
Both FBXs were reimported into Blender; bounds agree within 0.000001 m, and both
artwork faces and all artwork UVs survived. This does not validate Unreal's import.

## Import and integrate

Use the CARLA-specific Unreal 4.26 fork compatible with CARLA 0.9.16, on a Linux
build environment for the project's Linux runtime. The packaged simulator alone
cannot cook an FBX. Do not switch the project to UE5.

1. Import both FBXs as **static meshes**, not a new skeletal vehicle. Combine
   the frame's pieces on import, while keeping the artwork mesh separate. Preserve
   baked vertex positions and material slots. Use FBX unit conversion; validate
   the frame width is 143.31 cm including bezel, not metres or millimetres in UE.
2. Make a project-specific variant of `vehicle.mini.cooper_s_2021` and add both
   meshes as movable static mesh components parented to the chassis. Preserve the
   existing skeletal mesh, wheel rig, suspension and vehicle movement setup.
   Disable billboard collision/physics for this visual accessory; it must not
   collide with its parent or alter driving dynamics. Keep native camera shadows.
3. The exported vertices use the original Blender car coordinates. Its body bounds
   and centre are recorded in the receipt. Match that frame to the native Mini
   before finalizing component transforms: the current compositor uses native
   vehicle bounding-box centre minus source body centre. Account for Blender
   Y-left vs Unreal Y-right and metre/centimetre conversion exactly once. Inspect
   both roof pads at close range; zero relative transform is not yet verified.
4. Assign opaque charcoal/rubber frame materials and a lit artwork material using
   the existing UVs and PNG alpha, with white backing already present in the frame.
   Keep the ad material independently replaceable. Verify text on both sides.
5. Register the variant with CARLA's vehicle factory and cook/package it with the
   Linux CARLA build. Record the actual resulting blueprint ID, mesh/material
   paths, cooked package checksum and build revision. Do not invent these IDs in
   recording code before inspecting the actual packaged blueprint library.
6. Install into a derived runtime or writable asset layer, preserving the verified
   immutable base runtime. Restart CARLA and verify the variant exists and spawns.

## Recording integration and release gate

Before **every** CARLA recording or finished-video render, including a test preview:

```sh
python3 scripts/refresh_live_livery.py
```

Read `work/latest-livery.json`, transfer that archive with `tar --no-same-owner`,
pass the selected directory as `--asset`, and run
`flyhard.live_livery.verify_live_livery` before expensive work. Refresh the native
billboard material from this selected snapshot; r12 in this package is not an
authority for future runs. Save the snapshot and hashes with the recording.

Update recording code to spawn the *verified* variant. Refresh ad59 on the native
material before cameras start. Suppress only the old flat-roof ad59 surface in
the sponsor compositor; preserve all other sponsor surfaces. Rebuild cached
layers when source geometry changes. Include native billboard depth in occlusion.

A rerun is ready only after a short native test proves:

- correct roof contact, scale, text orientation and readable artwork on both sides;
- billboard moves rigidly with the chassis through a turn and braking;
- native RGB and depth contain the billboard, with correct scene occlusion;
- no doubled flat roof ad or duplicate billboard, and all other sponsors intact;
- existing wheel, stalk, CARLA steering and causal recording checks still pass.

Retain front-left/left-door and rear-right images and a machine-readable readiness
receipt identifying the cooked package, blueprint, livery and validation result.
Do not mark `ready_for_carla_recording` true based on the FBX round-trip alone.

## Current build prerequisite

On September 10, local `gh api user` succeeded as MarkUnthank, while
`gh api repos/CarlaUnreal/UnrealEngine` returned 404. No Unreal editor was found
in local `/Applications`. The documented GPU runtime contains packaged CARLA,
not an editor/source build. The current recorded Runpod session is stopped.
Mark referred us to task `01a08669-29bf-7070-b678-37c10fddd4ea` to check for an
existing build environment; that task has been asked. No GPU was started here.

References:
- https://github.com/carla-simulator/carla/blob/0.9.16/Docs/build_linux.md
- https://github.com/carla-simulator/carla/blob/0.9.16/Docs/tuto_A_add_vehicle.md
- https://github.com/carla-simulator/carla/blob/0.9.16/Docs/tuto_A_create_standalone.md
