# Export the current sponsors for videos

From the repository root:

```sh
cd apps/website
npm run export:livery
```

This downloads one frozen production livery revision into a new `exports/livery-r…` directory. It needs no Stripe or Cloudflare keys. It includes each sponsor's transparent PNG fitted to the current panel, their separate original logo thumbnail, stable spot IDs, dimensions, mesh names, public sponsor details, the source model, and SHA-256 checksums. When a panel changes aspect ratio, the export removes transparent gutters and fits the visible artwork with a 5% margin, matching the website without stretching the logo. Later bids cannot change these downloaded files. Rerun the command for each new recording; keep the export with that recording.

To generate the model with all sponsor images embedded, run the command printed by the exporter. On this Mac:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
  --python "/absolute/path/to/export/apply-livery.py" -- "/absolute/path/to/export"
```

Use Blender 4.2 or newer. This creates `sponsored-mini.blend` and `sponsored-mini.glb`. Both preserve the original car and slot geometry. Only paid sponsor surfaces remain; all unclaimed and retired panels, borders and placeholder lettering are removed. Transparency reveals the car paint or glass underneath. Existing artwork scaling, rotation and positioning are already baked into the PNG: do not apply them again. The script runs only in background mode and refuses to overwrite a previously generated model.

## Publish assets in the repository

After generating the models, run `npm run package:livery -- /absolute/path/to/export`. This prepares `apps/mini-livery/sponsors/r<revision>-layout<version>/` with the two models, one panel PNG per current sponsor, a public-only sponsor manifest and checksums. Review and commit that directory. The raw export, logs, payment IDs and local configuration stay excluded. Each revision/layout pair is immutable; the command refuses to overwrite an existing release.

The repository's [sponsor asset handoff](../mini-livery/sponsors/README.md) identifies the checked-in revision ready for the CARLA agent.

## Give this to the driving/video agent

> Use this exported livery revision for the next sponsor video. Load `sponsored-mini.blend` for Blender rendering or `sponsored-mini.glb` in a renderer with glTF alpha-blending support. Keep all sponsor surfaces attached to the car, using their existing transforms and UVs. `livery.json` lists the advertisers and the exact PNG for each mesh. Use `textures/ad-XX.png` on the car, not the uncropped `-logo.png`. Remove no paid sponsors. Keep this frozen revision throughout the recording and record its revision number in the video manifest. Verify the left door and rear views before the full render. Retain CARLA vehicle attribution from `CREDITS.md`.

## Native CARLA rendering

There is **no single paint texture** behind the website: each sponsor is a separate, UV-mapped surface above the car. This export works directly for Blender and glTF rendering. Loading a GLB or these PNGs does not automatically change CARLA's built-in vehicle.

For native CARLA video, the agent must integrate these surfaces as attached decal/mesh components in the Unreal Mini vehicle asset, or bake them into the matching CARLA material UV maps, then rebuild/load that modified asset. Apply the body and glass artwork to their respective materials; preserve transparency and verify orientation. A call that replaces only the car's diffuse texture cannot place these independent 0–1 UV images correctly by itself. That simulator integration is separate from this export.
