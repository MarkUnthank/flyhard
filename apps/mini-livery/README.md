# The Driving Fly — Mini advertising livery

The actual CARLA Mini Cooper S 2021. **Layout 5 has seven advertising spaces:** two on the left, one right door, bonnet, a double-sided roof billboard, front grille, and rear window. The billboard uses the existing `ad-59` placement and owner. Every paid placement is retained, including Blueshake and Supertask. The source retains all 59 historical IDs; the website hides inactive groups and the sponsor exporter removes them.

`roof-billboard.blend` is the editable, artwork-free accessory master taken from the approved smaller design. Its advertising mesh has two outward-facing quads with normalized UVs; one texture fills both faces. `rebuild-layout.py` appends it into the base vehicle for website exports. The immutable current roof texture has an explicit centre crop in `layout.json`, shared by browser display and paid-livery export; subsequent uploaded artwork uses the full billboard dimensions. Native CARLA import/cooking remains separate and is not complete; see `carla-billboard-import/README.md`.

## Rebuild the active layout

`layout.json` defines the panel locations and sizes in Blender Z-up coordinates. Run `blender --background --python-exit-code 1 --python apps/mini-livery/rebuild-layout.py -- apps/mini-livery`, then `cd apps/website && npm run assets`. The script reprojects panels and placeholder lettering onto the original car, verifies surface coverage, and regenerates the Blender model, compressed GLB and glTF Y-up inventory. `layout-checks.json` records the checks.

## Files

- [`custom-wrap/`](./custom-wrap/README.md) — downloadable bodywork paint texture and design starting points for custom-wrap buyers.

- [`sponsors/`](./sponsors/README.md) — generated sponsor textures and models ready for the driving/video agent. Use this for paid artwork; the base model below contains the original inventory placeholders.

- `the-driving-fly-mini.blend` — editable Blender 5.2 scene. Source textures are packed. The studio, car and ad spaces are separate collections.
- `the-driving-fly-mini.glb` — compact web derivative, with embedded textures and Draco mesh compression. It contains the car and ad spaces; the studio and cameras are excluded.
- `ad-spaces.json` — the authoritative spot inventory, matching the GLB node names and IDs. Positions use glTF's Y-up coordinate system, in metres.
- `mini-livery-front.png`, `mini-livery-rear.png`, `mini-livery-top.png` — rendered previews.
- `asset-checks.json` — export validation results.

## Connecting this to thedrivingfly.com

Load the GLB with a glTF loader that supports Draco, such as Three.js `GLTFLoader` with `DRACOLoader`. Give the car environment lighting for its metallic paint and glass.

Each ad has a parent node carrying `slot_id`, `title`, `status`, `width_m`, `height_m` and `color` in glTF extras. Its children also carry `slot_id`.

The child named in the inventory's `panel` field is the **full-area picking target and logo surface**. It has a 0–1 UV layout and `role: "logo_surface"`. Assign a new, individual material with the advertiser's artwork to this mesh. Preserve its geometry so the artwork follows the bodywork.

Dashed borders and text have `role: "availability_marker"`. Hide those children when displaying a purchased placement. The site should store pricing, reservations and purchases separately, using `slot_id` as the stable key. The asset's `available` values are the initial display state.

The Blender master retains full-resolution textures. The web derivative uses 2K paint and up to 1K detail maps. Body geometry, windows, wheels and all spot groups remain separate. Placeholder text is mesh geometry, so browser rendering does not depend on installed fonts.

## Source and attribution

Vehicle geometry and original textures: **CARLA 0.9.16**, Computer Vision Center (CVC), Universitat Autònoma de Barcelona. Blueprint: `vehicle.mini.cooper_s_2021`. Main mesh: `SK_Mini2021`, with the matching door, light and glass assets. Exported from CARLA's Unreal assets using [UE Viewer](https://github.com/gildor2/UEViewer).

CARLA's [upstream license statement](https://github.com/carla-simulator/carla/tree/0.9.16#licenses) identifies CARLA-specific assets as CC-BY. Retain the vehicle attribution when publishing the model. The livery layout, web preparation and reconstructed Blender materials are modifications for Mark Unthank's The Driving Fly project.

Lettering uses [Barlow Condensed](https://github.com/google/fonts/tree/main/ofl/barlowcondensed), under the SIL Open Font License; a copy is included as `BarlowCondensed-OFL.txt`.

## Verification

The exported GLB was reimported into Blender and rendered. Its inventory has 59 unique slot groups, 59 UV logo surfaces, and matching node names. The front, rear and top layouts were visually checked. The asset is ready for website integration; checkout and availability storage are separate website work.
