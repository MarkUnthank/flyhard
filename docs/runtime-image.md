# Packaged GPU runtime

The runtime image packages CARLA 0.9.16, the verified Runpod PyTorch 2.8.0 / CUDA 12.8.1 base, FlyGym/NeuroMechFly, MuJoCo, VTK/PyVista and video tools. All installations and the checksum-verified CARLA extraction run at image build time. Startup performs no downloads or package installation.

The Docker base is pinned by its Linux AMD64 manifest digest. The CARLA archive and FlyGym source commit are pinned independently. Project dependency constraints and explicit visualization versions are applied during the build; the image stores a complete installed-package inventory and source hashes. `docker/build_receipt.py` records these under `/opt/flyhard/build-receipt.json`.

## Build and publication

The `Build Flyhard runtime` GitHub Actions workflow builds on a disposable Ubuntu 24.04 Linux runner and publishes an immutable `runtime-<commit>` tag in `ghcr.io/markunthank/flyhard`. The workflow can also be dispatched manually. Its artifact contains the exact image digest. The registry cache retains the large CARLA and dependency layers across source-only changes.

Build context is an explicit allowlist: project source, scripts, tests, fonts, dependency declarations and licenses. Environment files, credentials, account configuration, local apps, simulation recordings, graph data and checkpoints are excluded. Trained-model data is restored separately into the mounted workspace when required. The image contains the official CARLA binary distribution with its existing notices; that distribution is not relicensed under Flyhard's MIT license. No Unreal editor/source is included.

GitHub-hosted standard Linux builds for public repositories are free under the [current GitHub policy](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). GitHub currently charges no storage or bandwidth fee for its [container registry](https://docs.github.com/en/billing/concepts/product-billing/github-packages). These policies can change. No paid GitHub runner or additional Runpod credit is configured by this workflow.

## Runtime layout

- `/opt/carla`: pre-extracted simulator.
- `/opt/flyhard-env`: preinstalled Python environment.
- `/opt/flyhard`: bundled project source and build receipt.
- `/workspace/flyhard`: editable working project and experiment outputs. Missing source folders are seeded on first boot; existing work is preserved.
- `/workspace/flyhard/.venv`: link to the image's Python environment.
- `/workspace/flyhard/work/runtime`: startup timings, readiness, process logs and build provenance.

The default entrypoint starts SSH, the independent Pod deadline guard, and offscreen CARLA. A real CUDA calculation and CARLA API readback must pass before `work/runtime/ready.json` is written. A service failure exits the runtime instead of leaving a misleading ready process. Only SSH is exposed; CARLA's API remains internal.

`FLYHARD_MAX_RUNTIME_SECONDS` defaults to 3,600 seconds and must be between 120 and 21,600. On Runpod, the guard uses the provider-injected Pod credential to stop the instance at its deadline. The local launcher independently checks account credit. Stopping preserves the volume for recovery and may retain storage charges; after verified exports, terminate the Pod to release its storage too.

## Validation before promotion

The build runs the existing graph/budget tests and constructs the full supported fly rig without a GPU. A built image is still only a candidate. On a newly created Runpod GPU:

```bash
cat work/runtime/ready.json
python scripts/runtime_graphics_smoke.py mujoco
python scripts/runtime_graphics_smoke.py vtk
python scripts/carla_smoke.py --out runs/runtime-carla-smoke
```

MuJoCo and VTK render in separate processes to preserve their separate EGL lifetimes. Both checks require the actual NVIDIA renderer. CARLA records 120 matching synchronous camera frames using explicitly scripted infrastructure-test controls. These checks validate installation and graphics, not learned driving.

Record both provider-request-to-ready and container-start-to-ready times. A fresh host still needs to pull uncached image layers; an already cached image can start faster. Do not infer warm-start timing from the build duration. Update the Runpod template to the tested immutable digest only after the GPU checks and local exports pass.

The native-fly Unreal editor build remains a separate task. This image accelerates the existing packaged CARLA and MuJoCo workflow.
