# Native CARLA livery build

The target is CARLA 0.9.16 with the matching Unreal 4.26 fork. The web model is
not a cooked CARLA vehicle. Native readiness requires the import, cook, and
simulator checks below.

Pinned source:

- `CarlaUnreal/UnrealEngine`, branch `carla`, commit
  `e9d9e60c85f643e10eeb03f42f61554d18dcb30f`.
- `carla-simulator/carla`, tag `0.9.16`, commit
  `294096eb1c38eabf246e4f3a9cdab704e33a7f4c`.
- Matching CARLA content archive: `20250912_2171890.tar.gz`, selected by that
  checkout's `Util/ContentVersions.txt`.

Unreal access requires the operator's Epic/GitHub linkage. Keep engine source,
dependencies, binaries, and temporary download credentials in ignored local
`work/` or private persistent storage. Never put them in a public image context.

## Builder

Use Ubuntu 22.04, at least 16 build workers, sufficient RAM for those workers,
and roughly 250 GB of durable workspace for the engine, CARLA, runtime cache,
and intermediate files. The first build is substantial; later builds reuse it.

Runpod launch configuration must set `startSsh: true` with the project's public
key registered to the account. This enables the basic SSH gateway before the
container's own SSH server is installed. `PUBLIC_KEY` alone configures the
in-container server; it did not enable the gateway in the verified setup.

`bootstrap.sh` uses IPv4 and the official US Ubuntu mirror. During the September
10 setup, the default mirror transferred about 292 KB in 12 seconds, while the
US mirror transferred 1.4 MB in about a second on the same machine. Re-measure
when placing a builder in another region; this is an observation, not a universal
mirror-speed guarantee.

Use `FLYHARD_SESSION_DIR` to isolate native build state from recording Pods.
`scripts/runpod_control.py` prices CPU/GPU configurations using the live catalog
and maintains a separate budget/deadline watcher. It never adds credit. The
on-Pod deadline helper uses only the provider-injected Pod credential. Verify
its log after launch; do not treat launching the helper as proof that it works.

The private build package lives under `/workspace/flyhard-build` on the network
volume. Retain both the extracted trees and their original archives:

- `content/20250912_2171890.tar.gz` and `content/archive.sha256` hold the matching
  CARLA source assets. `prepare_content.sh` reuses this archive without contacting
  the download server. A completed extracted tree is checked using its version
  and a checksum of Town03 before reuse.
- `downloads/v17_clang-10.0.1-centos7.tar.gz` holds the Unreal compiler toolchain;
  `build_engine.sh` connects Unreal's cache to that retained archive.
- `apt-archives/` holds the verified Ubuntu compiler/dependency packages.
- `proof_environment.sh` retains Python client wheels in `wheelhouse/`; its
  installation step uses those local files.
- The Unreal and CARLA source, dependency caches, and build outputs remain in
  their respective checkout directories. Replacement Pods attach this same
  volume and continue from these files.
- `editor.sh` sends Unreal's shader/derived-data cache to
  `cache/DerivedDataCache` on the same volume, so native previews also reuse it.

The original archives are part of durable storage, not the container layer that
Runpod pulls for every new host. Keep this build package private because it
contains the authenticated Unreal source checkout. Live sponsor artwork still
gets refreshed for every recording.

Run `build_engine.sh` as `builder` with the engine checkout at
`/workspace/flyhard-build/UnrealEngine_4.26`. It records stage, logs, result code,
and successful binary checksums on the persistent volume. Compilation is capped
at 16 parallel actions because some hosts expose more CPUs than were allocated.
Do not run `make -j` on the Unreal top-level makefile. Setup uses Ubuntu's Mono
runtime and certificate store for dependency HTTPS; the pinned bundled Mono is
still used by project generation and compilation.

For an interrupted build, `continue_build.sh project-files` resumes after a
completed setup, and `continue_build.sh compile` resumes after Makefile generation.
Both check the pinned source and setup markers; stop the previous pipeline first.
The default phase is `setup`. Build files are limited to Make without IDE indexes.
Use `continue_build.sh carla` when the engine is already compiled and only the
CARLA stages need to resume.

The minimal Ubuntu image also needs `libegl1`, `libgl1`, and `libopengl0`.
The mounted NVIDIA libraries and a working `nvidia-smi` did not suffice: before
these packages were installed, Vulkan exposed only Mesa's CPU renderer. A fresh
`vulkaninfo --summary` check under the unprivileged builder verified the RTX 6000
Ada and driver 580.159.04 afterward. `editor.sh` selects the NVIDIA ICD explicitly.

First editor initialization also builds shader and distance-field data. Warm it
independently of advertiser snapshots using `editor.sh -run=pythonscript
-script=/workspace/flyhard-build/downloads/warm_editor.py -unattended -NullRHI
-nosound -nop4`. Normal imports then reuse the results. Do not use
`-NoShaderCompile` for static-mesh import in this engine fork: it leaves the
distance-field task queue uninitialized and the mesh build dereferences it.
Disabling distance fields alone does not avoid that mesh-build code path.

`prepare_python_compat.py` retains Ubuntu's pinned `libffi6_3.2.1-8_amd64.deb`
and verifies the extracted library. Unreal's bundled Python 3.7 needs ABI 6 for
`ctypes`; Ubuntu 22.04's system ABI 8 is not a substitute. Editor and packaging
commands add this private compatibility directory to their library path. The
archive and extracted library both passed reuse with HTTPS directed to a closed
local port, verifying that this stage can run without a download.

On Linux this engine replaces hyphens in environment-variable names with
underscores, so the actual override is `UE_LocalDataCachePath`. `editor.sh` uses
that name, limits shader workers to the Pod CPU quota (up to 16), and puts shader
working files under `/tmp` using Unreal's `ShaderWorkingDir` option. Only those
temporary compiler files are ephemeral; derived data stays on the volume.
The first cache created under `Engine/DerivedDataCache` was moved into
`cache/DerivedDataCache`, with a symlink preserving the original path.

`build_carla.sh` applies `carla-native.patch` to the pinned CARLA checkout. The
patch adds a `movable` option to `static.prop.mesh`, allowing rigid visual
accessories with no simulated mass, includes `/Game/Flyhard` in cooked builds
because these meshes are loaded by path, and caps CARLA's build concurrency. It
requires compilation and a native simulator test before recording integration.

## Import gates

1. Run `scripts/refresh_live_livery.py`; select `work/latest-livery.json`.
2. Run Blender with `scripts/export_native_livery.py --asset DIR --output NEW_DIR`.
   The exporter checks production revision/layout and file hashes, then exports
   the billboard frame plus each paid logo independently. Only `logo_surface`
   objects count as artwork: structural objects also carry `slot_id=ad-59`.
3. In the built Unreal editor, run `import_livery.py` with
   `FLYHARD_NATIVE_EXPORT=NEW_DIR`. It verifies the imported centimetre bounds
   against the Blender metre bounds after the coordinate conversion, creates
   lit alpha materials, and removes mesh collisions. Native readiness still
   requires a fresh-process reload and simulator proof.
   Use the default FBX front-axis conversion: forcing X rotates these Blender
   exports by 90 degrees. The bounds check rejects that incorrect orientation.
4. Cook the assets and runtime with a manifest of source and output checksums.
   A Blender round trip or an Unreal import receipt is not cooking proof.
5. In CARLA, attach the native meshes rigidly to the Mini, disable their
   collisions, and check both sides of the billboard, roof contact, left door,
   and rear logos. Check RGB/depth occlusion and attachment while steering and
   braking. Compare vehicle physics/control results against the stock Mini.

Refresh live artwork again before every capture, including previews. Preserve
the selected snapshot for the run. Remove duplicate presentation sponsor layers
only after the corresponding native surfaces are verified. Keep the existing
request, steering, and stalk readouts, and the website address in the black area.

Native receipts retain both the original `.blend` checksum and the deterministic
embedded GLB checksum. A fresh Blender save can change metadata without changing
the model. Reuse of native assets requires matching GLB content, revision, layout,
paid surfaces and each artwork checksum; a changed model still requires import.

## First native simulator proof

After the editor build and content extraction finish, import with:

```sh
FLYHARD_NATIVE_EXPORT=/workspace/flyhard-build/livery-r12-layout5-v2 \
  bash /workspace/flyhard-build/downloads/editor.sh \
  -run=pythonscript -script=/workspace/flyhard-build/downloads/import_livery.py \
  -unattended -NullRHI -nosound -nop4
```

The example snapshot path must be replaced with that run's current live export.
Run `scripts/verify_native_livery.py --asset DIR --import-receipt RECEIPT --out NEW_DIR`
against an owned empty CARLA server. It captures native RGB/depth from both sides,
front and rear, checks vehicle physics configuration, and measures accessory
attachment error while steering and braking. Its result explicitly leaves visual
review and runtime packaging pending. Inspect those images before adding native
assets to the video pipeline; the verification capture contains no fly-policy
claim and is not the finished video.

If an import fails after creating assets, set `FLYHARD_NATIVE_IMPORT_ATTEMPT` to
a new letters/numbers/underscore label when retrying. This preserves the failed
attempt's asset namespace while producing a separate checked receipt.

Run `verify_saved_livery.py` in a fresh editor process to check that every saved
mesh reloads with its recorded bounds and non-null materials. Keep the commandlet
exit result separately from its asset receipt: a receipt written before an editor
shutdown failure is not a clean process result. `server.sh editor` and
`server.sh runtime` launch owned Town03 servers for the two simulator proof stages.

The first Linux import saved its assets but crashed during process teardown.
A diagnostic backtrace traced the failure through `FbxManager::Destroy()` during
shared-library static destruction. `engine-lifecycle.patch` releases Unreal's
FBX importer on `OnEnginePreExit`, while the FBX function registry is still alive.
`rebuild_editor.sh` refuses to replace editor libraries while an editor is running.
After rebuilding, require a clean import exit and a fresh-process material reload;
the source patch alone does not prove that the shutdown issue is resolved.

## Dependency build overlap

`build_carla_dependencies.sh` can run at low scheduling priority with four workers
while Unreal compiles. The editor build invokes the same script with 16 workers;
a shared file lock prevents simultaneous writes to CARLA dependencies. Both
phases retain their installed libraries on the volume. All Ninja commands use
the same explicit worker limit.

For a sparse CARLA checkout on Ubuntu 22.04's Git 2.34, use
`GIT_LFS_SKIP_SMUDGE=1 git sparse-checkout init --cone` followed by
`GIT_LFS_SKIP_SMUDGE=1 git sparse-checkout set Unreal LibCarla PythonAPI Util`. This includes top-level
Makefile/CMake files. That Git version treats `set --cone` as a path pattern.
The dependency build checks these files before starting. CARLA marks only log and
MP4 files for Git LFS; skip those demonstration downloads during source checkout.
The separate versioned CARLA content archive supplies the runtime assets.

The pinned CARLA setup script's libpng 1.6.37 URL has moved into the official
SourceForge `older-releases` directory. The patch preserves that version and
checks the published archive SHA-256.

StreetMap is fetched at CARLA's pinned commit with a shallow Git fetch. Once that
commit is present, subsequent builds use it without fetching repository history.
This also keeps the dependency independent of changes to its remote default branch.

`archive-manifest.json` pins the eight CARLA build dependency archives by URL,
size and SHA-256. `cache_carla_archive.py --prefetch` verifies/promotes those
archives on the durable volume; CARLA's setup copies from that cache. Upstream
cleanup removes only the temporary build copies. Cache locks allow a CPU helper
and the GPU builder to share downloads without writing the same archive twice.
This includes the pinned SUMO source ZIP used by OSM2ODR.

The first builder encountered a particularly slow GitHub ZIP download. Its
verified local SUMO ZIP was therefore used to produce a 4,912,816-byte source
bundle containing the original root files, `src/`, and `build/cmake_modules/`.
Those are the inputs used by this fork's OSM2ODR CMake build. The bundle retains
the full ZIP hash, commit, and all 2,507 source-file hashes. It transferred in
40.47 seconds over 16 independent SSH streams and passed extraction verification.
The original ZIP remains in the local ignored dependency archive directory;
seven other dependency archives are fully cached on the remote volume. The SUMO
bundle and extracted build source are retained there, so replacement Pods reuse
the source without fetching the full ZIP. Do not label the remote ZIP cache as
complete until that original ZIP is also present and verified.

Verified first-build timings: UE4Editor's 2,780 main build actions completed in
1,923.67 seconds (including planning/header work). A fresh Python client
environment restored from cached wheels with the index disabled in 5.016 seconds.
The native content archive completed integrity verification and extraction at
12:35:15 UTC on September 10, 2026; its archive and Town03 hashes are retained.
These are stage timings, not a claim that native CARLA import/cooking is finished.

## Reusable native runtime

After a successful native import, run `package_runtime.sh` as `builder` with
`FLYHARD_NATIVE_EXPORT` set to that export directory. It uses CARLA's official
Shipping packaging flow, including the tagged-material registry, with headless
commandlets. The default map selection includes Town03 and its annotation
landscape material; override `FLYHARD_MAPS_TO_COOK` with a plus-separated list
when another episode requires additional towns, retaining Town03 in that list.
The packaged game defaults to Town03: this Shipping target ignores a positional
map override, so the default map must be present in the cooked package. The editor
wrapper places user arguments before compiler flags, as Unreal reads the map from
the first token after the project path. The native proof rejects any other town.

The extracted Linux runtime stays under CARLA's `Dist/` directory on the same
private volume. The package receipt records the source pins, native files,
selected maps, and Shipping executable hash. It deliberately leaves a final
simulator test pending: run `verify_native_livery.py` against this packaged
runtime and inspect its native camera output before using it for recordings.
The source content archive and editor build are retained for future livery cooks.

`build_shipping.sh` can compile the standalone executable with eight workers
while the independent editor proof warms its graphics cache. Packaging reuses
that executable. The pinned build disables adaptive Git working-set discovery:
the scan timed out on the network volume and is unnecessary for this fixed source.
