# Sponsor artwork for the CARLA/video agent

Current checked-in snapshot: **revision 7, layout 4**, exported September 10, 2026. It contains all seven paid placements present at export time. Website purchases after that revision require a fresh export.

After `git pull`, use these repository paths directly:

- `apps/mini-livery/sponsors/r7-layout4/sponsored-mini.blend` — Blender model with all images packed.
- `apps/mini-livery/sponsors/r7-layout4/sponsored-mini.glb` — equivalent glTF model with embedded sponsor textures.
- `apps/mini-livery/sponsors/r7-layout4/textures/ad-XX.png` — transparent sponsor artwork fitted to each current panel, one PNG per paid surface.
- `apps/mini-livery/sponsors/r7-layout4/manifest.json` — maps each sponsor to the correct mesh, PNG, and physical dimensions.
- `apps/mini-livery/sponsors/r7-layout4/sha256.json` — verifies every model, artwork PNG, and manifest.

All seven paid surfaces use the enlarged layout 4 geometry with 0–1 UVs. All seven spaces are occupied. Supertask stays on the rear window; Safemate uses the right door, Blueshake the left front window, and Flycoin the bonnet, roof and grille. The owner approved redistribution of existing paid placements. No unclaimed panels or placeholder lettering are included in the sponsored models. Each PNG is ready for its corresponding mesh. When a panel changed shape, transparent gutters were removed and the logo fitted with a 5% margin, without stretching. Do not apply the original editor transforms again. Keep the surfaces parented to the car and preserve alpha blending. Check the left door and rear views before rendering the full video.

## Native CARLA

The sponsor model is render-ready in Blender/glTF. It is not a drop-in replacement for CARLA's existing skeletal vehicle asset, and there is no single combined paint map: each sponsor uses a separate UV-mapped overlay surface.

For native CARLA, integrate the exported sponsor surfaces into the Mini's Unreal vehicle as attached mesh/decal components, or bake them into the corresponding CARLA paint/glass UV maps and rebuild the vehicle materials. Preserve the mapping in `manifest.json`. Simply assigning one of these PNGs to the car's full diffuse material will place it incorrectly.

Record livery revision **7**, layout **4**, with any video using this snapshot. See [export instructions](../../website/LIVERY-EXPORT.md) to refresh the assets for another recording.

## Public data and attribution

This directory contains public sponsor names, website links, and artwork. It contains no billing details, email addresses, payment/session IDs, API keys, or webhook secrets. The raw checkout database and local exports are not committed.

Sponsor names, logos, and artwork belong to their respective owners; inclusion does not relicense them under the software license or imply endorsement. Vehicle geometry/textures originate from CARLA 0.9.16, Computer Vision Center (CVC), Universitat Autònoma de Barcelona; retain the vehicle credit in published videos. See [the model attribution](../README.md#source-and-attribution). Barlow Condensed uses the SIL Open Font License, included with the assets.
