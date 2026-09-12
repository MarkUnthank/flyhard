# Roof billboard website release and CARLA handoff

Mark approved the double-sided taxi billboard, then requested a 15% reduction.
The approved accessory uses the existing `ad-59` roof placement and its existing
really nice advertiser. Layout 5 is deployed to https://thedrivingfly.com/.

## What shipped

- Editable `apps/mini-livery/roof-billboard.blend` accessory master, appended by
  `rebuild-layout.py` into the base vehicle. The web derivative is
  `/model/the-driving-fly-mini-v5.glb`.
- One slot, two correctly oriented advertising faces, with normalized UVs for
  future uploads. The current immutable roof PNG receives the reviewed centre
  crop in both the browser and the livery exporter, without stretching.
- Earlier requested 3D default, slow rotation until interaction, and green bid
  featured-sponsor callout.

The shared checkout contains unrelated pending site changes (media, email,
artwork editor, hover preview). To avoid publishing those, the release was built
in `work/roof-billboard-release/checkout` on `codex/roof-billboard-live`, based on
e4d2993 plus the model and this task's requested UI changes. Its
`worker/auction-live.mjs` is the exact downloaded currently deployed auction
implementation, preserving complimentary credits and payments. This release
worktree is a reproducibility artifact; coordinate the shared pending website
work before a subsequent broader deployment.

## Verification

- Release TypeScript, 23 integration/artwork tests and OpenNext production build
  passed. The shared working copy also passed TypeScript after model sync.
- Local browser checked both billboard faces, live advertiser artwork, roof
  checkout framing and green qualifying-bid message. No checkout was submitted.
- Production browser showed the billboard, 3D default and live WebSocket state.
- Production GLB checksum matches the local tested file; inventory is layout 5.
  All seven placement records and $18 paid revenue were identical before/after;
  European Defense Explorer remains $6 effective ($2 paid + $4 complimentary).
- Fresh production export `work/live-livery/20260910T091528551294Z` built the
  paid Blender/GLB successfully: revision 12, layout 5, seven sponsors. Exported
  roof has four triangles (two faces), UVs 0–1, and native car-body bounds exclude
  billboard structure so adding the sign does not shift the vehicle origin.
- Temporary local preview servers on ports 3002/3003 were stopped.

## CARLA is not rerun-ready

The FBX frame and separate artwork in `apps/mini-livery/carla-billboard-import`
passed Blender round-trip geometry and UV checks. They have NOT been imported,
cooked or verified in CARLA. The CARLA agent confirmed only packaged 0.9.16
runtimes are available; no matching Unreal 4.26 builder exists. The authenticated
GitHub account cannot access CarlaUnreal/UnrealEngine. No GPU was started.

The CARLA agent was informed that production exports now contain billboard
structure and that the old sponsor compositor must not be rerun unchanged. Its
strict body-mesh check currently rejects the new accessory. Native import and
material integration, cooking, installation, and camera/depth/drive checks are
still required. Refresh live artwork again before any future recording; neither
the earlier FBX export nor this report's snapshot is an authority for a later run.
