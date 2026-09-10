# Fresh sponsor artwork for every recording

The live marketplace is authoritative. Historical checked-in sponsor directories
are frozen exports, not defaults for new recordings.

1. From the repository root run `python3 scripts/refresh_live_livery.py` before
   each CARLA capture, preview, or finished-video render. This downloads the live
   advertiser snapshot, transformed artwork, original vehicle and matching panel
   inventory, then builds packed Blender/glTF models and exact render meshes.
2. Read `work/latest-livery.json`. Each export has its own immutable directory,
   source manifest and SHA256 checksums. The small transfer archive contains the
   curved render meshes and paid PNGs required by the 60 fps renderer. The full
   packed models remain in the local export directory.
3. Transfer the archive to the GPU Pod and extract from `/workspace/flyhard` with
   `tar --no-same-owner -xzf ARCHIVE`. Pass its `relative_asset` as `--asset` to the
   renderer. For legacy Blender projections, transfer the full packed model too.
4. Recording/render entry points check the live revision, layout, paid surfaces
   and local checksums before starting. An unavailable production API, stale
   snapshot or modified file stops the command. Refresh if advertisers changed;
   never fall back to an old snapshot. Pre-rendered sponsor layers must match the
   selected packed model, so regenerate them when that model changes.
5. Review left-door and rear previews before the full export. Keep artwork UVs,
   alpha and physical dimensions. PNG transforms are already baked. Keep the
   selected snapshot fixed once rendering starts; another purchase is picked up
   by the next run.

The run stores `livery-preflight.json` and `livery-manifest.json`; the video receipt
and credits include the actual livery revision and layout. No advertiser billing,
email, payment or webhook secrets are downloaded by this workflow.

## Smooth directed replay

Use `scripts/render_smooth_roundabout.py --run SOURCE_RUN --out NEW_OUTPUT
--asset FRESH_ASSET` on the GPU Pod, after downloading that run's live artwork.
`--previews` checks six representative shots. The renderer reconstructs saved
CARLA world motion and MuJoCo joint poses at 60 output timestamps per second.
Neural activity is held from the original measured samples; it is not fabricated.
The current edit is 23 seconds of action plus 2 seconds of credits, with longer
stalk and indicator shots, website branding and all steering readouts.

The video is a replay of a recorded controller episode. The cabin fly and sponsor
surfaces are depth-aware composites, not newly packaged native Unreal actors.
