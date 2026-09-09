# Packaged GPU runtime

The runtime image packages CARLA 0.9.16, the verified Runpod PyTorch 2.8.0 / CUDA 12.8.1 base, FlyGym/NeuroMechFly, MuJoCo, VTK/PyVista and video tools. All installations and the checksum-verified CARLA extraction run at image build time. Startup performs no downloads or package installation.

The Docker base is pinned by its Linux AMD64 manifest digest. The CARLA archive and FlyGym source commit are pinned independently. Project dependency constraints and explicit visualization versions are applied during the build; the image stores a complete installed-package inventory and source hashes. `docker/build_receipt.py` records these under `/opt/flyhard/build-receipt.json`.

## Build and publication

The `Build Flyhard runtime` GitHub Actions workflow builds on a disposable Ubuntu 24.04 Linux runner and publishes a commit-tagged candidate, `runtime-<commit>`, in `ghcr.io/markunthank/flyhard`. The workflow can also be dispatched manually. Its artifact contains the image index digest. Deployment pins the immutable Linux AMD64 manifest digest selected from that index. The registry cache retains the large CARLA and dependency layers across source-only changes.

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
source docker/activate.sh
cat work/runtime/ready.json
python scripts/runtime_graphics_smoke.py mujoco
python scripts/runtime_graphics_smoke.py vtk
python scripts/carla_smoke.py --out runs/runtime-carla-smoke
```

MuJoCo and VTK render in separate processes to preserve their separate EGL lifetimes. Both checks require the actual NVIDIA renderer. CARLA records 120 matching synchronous camera frames using explicitly scripted infrastructure-test controls. These checks validate installation and graphics, not learned driving.

Record both provider-request-to-ready and container-start-to-ready times. A fresh host still needs to pull uncached image layers; an already cached image can start faster. Do not infer warm-start timing from the build duration. Update the Runpod template to the tested immutable digest only after the GPU checks and local exports pass.

The native-fly Unreal editor build remains a separate task. This image accelerates the existing packaged CARLA and MuJoCo workflow.

## Measured startup

The [2026-09-09 validation](../reports/2026-09-09-runtime/) used one A40 in EU-SE-1 and the immutable image recorded in `deploy/runtime.json`.

| Measurement | Fresh Pod | Restart of the same Pod |
| --- | ---: | ---: |
| Request to CUDA + CARLA ready | 9 min 41 sec | 24 sec |
| Container start to ready | 19 sec | 18 sec |
| Package installation at startup | None | None |

The image is 19.6 GB compressed. The fresh launch spent 9 min 21 sec before the container started. The restart reused the image on the same host; it does not predict the pull time on another host. These are single observations, not guaranteed startup times. The local launcher noticed readiness about 3 seconds after the fresh check and 7 seconds after the restart check because it polls at intervals.

The NVIDIA CUDA calculation, full 54-body fly rig, VTK EGL render, actual MaleCNS anatomy preview and 120-frame CARLA camera capture passed. All 17 exported input/output files matched their hashes and survived the restart. The CNS preview reused an existing model recording. This validation does not add training or driving capability.

## Launch a validated release

After GPU validation, `deploy/runtime.json` records the tested image. Your account's template ID is saved separately in the ignored `work/runpod-template.json`. The local `.env` must contain your own `RUNPOD_API_KEY`; the launcher creates a project SSH key if one is missing.

```bash
python3 deploy/launch.py
ssh -F work/ssh-config flyhard
# Inside the Pod:
cd /workspace/flyhard
source docker/activate.sh
```

The launcher creates one A40, waits for the packaged CUDA calculation and CARLA API check, verifies the running source revision, and saves measured startup times to `work/runtime-launch.json`. It archives a completed previous session before starting a new one. It requires at least $10 of existing credit, caps the estimated hourly price at $0.90, and never adds credit. The image and local guard both enforce the one-hour runtime limit. A readiness failure requests a stop and retains the workspace for inspection.

Use `python3 deploy/launch.py --wait` to reconnect to an existing launch without creating another Pod. Stop early with `python3 scripts/runpod_control.py stop`. After copying results locally and verifying their hashes, set `exports_verified` in the local session record and run `python3 scripts/runpod_control.py terminate`; stopping alone can retain storage charges.

To promote a newly tested build, run `python3 deploy/register_template.py --validation reports/<run>/validation.json`. This requires successful CUDA, MuJoCo, VTK and CARLA checks. It updates the existing private `Flyhard / CARLA 0.9.16` Runpod template, reads it back, and records the release locally. A successful container build alone cannot promote a release.
