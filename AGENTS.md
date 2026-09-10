# Recording and sponsor artwork

Before **every** CARLA recording or finished-video render (including previews), download and build
the latest paid advertiser livery from production:

```sh
python3 scripts/refresh_live_livery.py
```

Read `work/latest-livery.json` for that run's immutable asset directory and transfer
its archive to the GPU Pod with `tar --no-same-owner`. Pass the selected directory
as `--asset` to recording/rendering commands. Each command must run
`flyhard.live_livery.verify_live_livery` before starting expensive work. If the live
revision changed, refresh again. Never fall back to a checked-in historical livery
when production is unavailable or the check fails.

Keep the snapshot fixed during a run. Save its manifest, source and checksums with
the recording. Verify the left door and rear view before exporting the full video.
Preserve separate sponsor meshes, existing UVs and alpha. Artwork transforms are
already baked into the PNGs; do not apply them again. Rebuild cached sponsor layers
when the source model changes. Credits and receipts must use the selected revision
and layout, with no hardcoded sponsor count.

For video iterations, retain visible request-left, request-right, wheel angle,
CARLA steering and stalk readouts. Keep `thedrivingfly.com` in the black header.
Use the saved causal simulation data; describe presentation interpolation accurately
and never invent neural activations or claim visual autonomous driving.
