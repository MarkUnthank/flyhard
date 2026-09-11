# Selecting a cached CARLA runtime

This integration is local code, not a published image or verified native release.
The native Shipping package must finish cooking, pass its own simulator checks,
and receive visual review before promotion. An editor proof cannot promote it.

The container image supplies Python, rendering libraries and the launcher. A
separate manifest selects exact simulator files on the existing private volume.
Boot never downloads, extracts, cooks, installs, or promotes a simulator.

## Package and server interfaces

`scripts/runtime_manifest.py prepare-native --runtime <LinuxNoEditor> --package-receipt <json>`
hashes the complete immutable tree and writes `runtime-manifest.json` with status
`candidate`. Its JSON output includes `manifest`, `manifest_sha256`, `package_id`,
`root`, exact server/client versions, map, and native import identity. Existing
manifests are never overwritten. Generate each candidate only after cooking stops.

`deploy/native/package_runtime.sh` needs to retain its current receipt fields and
add these fields before calling preparation:

- `expected_server_version`: actual compiled version, currently `294096e-dirty`.
- `client_version`: compatible official client, `0.9.16`.
- `source_model_glb_sha256`: deterministic source GLB hash from the import receipt.
- `import_receipt_sha256`: hash of the copied `flyhard-native-import.json`.

The existing package status must remain exactly
`cooked; packaged-runtime simulator verification pending`. Preparation checks the
Shipping binary, imported mesh inventory, native file hashes, identity and Town03
cook selection. It does not claim the simulator renders those meshes correctly.

`deploy/native/server.sh` can resolve either candidate or promoted packages with:

```sh
python3 scripts/runtime_manifest.py resolve \
  --manifest /workspace/path/runtime-manifest.json --sha256 <selected-manifest-sha256>
```

Use the returned `root` to launch `CarlaUE4.sh`. Add `--allow-candidate` only for an
explicit proof run. The resolver verifies the manifest digest, launcher, actual
Shipping executable, native import receipt and cooked native files. It checks
the promoted proof digest too. Boot checks are capped at 256 files and 1 GiB.
Town03 must be the cooked default; do not rely on a positional Shipping map argument.

## Proof and promotion

Run the proof against that candidate's Shipping server, with fresh live sponsor
preflight as usual. The automated proof must have:

```json
{
  "status": "automated_checks_passed",
  "runtime_mode": "shipping",
  "runtime_manifest_sha256": "<candidate manifest SHA-256>",
  "carla_server_version": "294096e-dirty",
  "carla_client_version": "0.9.16",
  "map": "/Game/Carla/Maps/Town03",
  "import_receipt_sha256": "<copied native import receipt SHA-256>",
  "revision": 19,
  "layout": 5,
  "native_actor_count": 8,
  "physics_configuration_unchanged": true,
  "peak_speed_m_s": 4,
  "max_attachment_position_error_m": 0.001,
  "max_attachment_rotation_error": 0.0001,
  "camera_comparisons": []
}
```

The numbers above illustrate the schema; use actual measurements and the selected
livery's revision, layout and actor count. `camera_comparisons` must contain all
eight existing combinations of `left-door`, `right-billboard`, `rear`, `front-roof`
and `rgb`/`depth`, each with `changed_pixel_fraction` in `(0, 1]`. Peak speed must
be at least 1 m/s; attachment errors must be finite and no greater than 0.002 m
and 0.0002 for the rotation matrix. Inspect the captured native images and write
a separate review only after they pass:

```json
{
  "status": "passed",
  "runtime_manifest_sha256": "<candidate manifest SHA-256>",
  "proof_sha256": "<exact automated proof JSON SHA-256>"
}
```

Stop the owned candidate server before promotion so the immutable tree is stable.
Promotion rehashes every immutable file, rejecting changed, missing and extra
content; `CarlaUE4/Saved` remains mutable. On success it moves the candidate on
the same filesystem into `<releases>/<package_id>`, retains combined proof in
`runtime-proof.json`, and atomically replaces the manifest with status `verified`.
The resulting manifest digest changes; select the **returned** digest and path.
The original mutable `Dist/` directory no longer contains that runtime.

```sh
python3 scripts/runtime_manifest.py promote \
  --manifest /workspace/path/runtime-manifest.json --sha256 <candidate-sha256> \
  --proof /workspace/proof/native-proof.json \
  --visual-review /workspace/proof/visual-review.json \
  --releases /workspace/flyhard-runtime/native
```

Do not run another cook or edit candidate files during proof/promotion. Keep
source archives and editor/build trees separately; they are not boot dependencies.
Native packages and their source remain on private storage, outside public image
contexts. A fresh sponsor revision requires a fresh import/cook/proof; a previously
verified package must never silently substitute stale paid artwork.

## Official runtime migration and release selection

Official cached CARLA uses the same manifest model:

```sh
python3 scripts/runtime_manifest.py prepare-official \
  --runtime /workspace/flyhard-runtime/carla-0.9.16 \
  --archive /workspace/flyhard-runtime/downloads/carla-0.9.16.tar.gz
```

This verifies the original official archive's pinned SHA-256 and compares all
extracted immutable files to its contents. An old `asset-receipt.json` alone is
insufficient. The result is a candidate. Official promotion requires a Shipping
proof bound to its manifest, server/client `0.9.16`, map `Town10HD_Opt`, and an
integer `rgb_frames_received >= 1`; native-only metrics/review are not applicable.
The CLI promotion flow then retains the official proof in the same model.

Add the selected canonical manifest path and exact digest to the image release
JSON alongside its existing image/environment fields:

```json
{
  "runtime_layout": "network-volume",
  "runtime_manifest": "/workspace/flyhard-runtime/native/<package-id>/runtime-manifest.json",
  "runtime_manifest_sha256": "<returned promoted manifest SHA-256>"
}
```

`deploy/launch.py` passes `FLYHARD_RUNTIME_MANIFEST`,
`FLYHARD_RUNTIME_MANIFEST_SHA256`, and `FLYHARD_RUNTIME_CANDIDATE` to the container.
Candidate use requires `--validate-candidate` and remains capped at one hour.
The existing volume selection, account guard and independent Pod deadline remain.
Use a canonical path to the content directory, not a mutable `current` symlink.

Container startup sets `FLYHARD_CARLA_ROOT` from the verified selection. Health
checks use the selected exact server version, compatible client, expected map,
and native movable-mesh capability. `ready.json` records `runtime_asset`; the
launcher rejects mismatched manifest identity or a candidate outside explicit
validation mode. A ready candidate means the server/GPU started, not that native
camera proof and release validation have passed.

The image build receipt records only image/environment provenance for a volume
runtime; the selected simulator identity is recorded at startup. Publish and test
a new volume image before changing any validated release. This work does not yet
validate the image's Shipping shared-library compatibility or measure boot speed.
