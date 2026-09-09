# Packaged GPU runtime validation

Flyhard previously installed CARLA and its Python/graphics environment on each experiment host. The published container performs that work during a reusable image build. A fresh A40 and a restart of the same Pod verified the resulting runtime on 2026-09-09.

## Result

| Measurement | Fresh Pod | Same-Pod restart |
| --- | ---: | ---: |
| Request to CUDA and CARLA ready | 580.52 seconds | 24.13 seconds |
| Request to container start | 561.25 seconds | 5.77 seconds |
| Container start to ready | 19.27 seconds | 18.37 seconds |
| Installation at startup | None | None |

These are single measurements in EU-SE-1. The 19.6 GB compressed image accounts for most of the fresh-host delay. A new host may need the full download; a same-Pod restart reuses its cached image. The launcher observed readiness 3.45 and 7.22 seconds after the respective on-Pod checks because it polls periodically.

The deployment reference is pinned in [runtime.json](../../deploy/runtime.json). It identifies the Linux AMD64 manifest of source revision `9a9a2e7ea2125ec7375d0280782102668f03f8bb`. The image is publicly pullable from GHCR without registry credentials. The user's private Runpod template points to the same digest; no account template ID or credentials are committed.

## Evidence

- [Build](build.json): eight tests passed, with CARLA, system-library and Python-environment layers cached. The final build/publish step took 5 minutes 26 seconds.
- [Provenance](build-receipt.json): all 42 recorded source hashes matched the published commit; the exported [installed package inventory](environment.lock.txt) matched its recorded hash.
- [CUDA and CARLA readiness](fresh-launch.json): a real GPU calculation and live CARLA 0.9.16 API connection passed.
- [Fly body](mujoco.json): the 54-body rig simulated 0.5 seconds and rendered through the NVIDIA A40.
- [VTK](vtk.json): NVIDIA EGL rendering passed. The [actual MaleCNS preview](cns-preview.json) also rendered successfully using [existing recorded neural activity](cns-source.json).
- [CARLA camera](carla.json): all 120 synchronous world/camera frames matched, producing a six-second recording. Its controls were scripted for this infrastructure check.
- [Restart](warm-launch.json): readiness passed with a new container-start timestamp. The installed image/source receipt was unchanged, and all saved experiment files survived.
- [Exports](artifact-manifest.json): all 17 input/output files, totaling 435,650,483 bytes, matched their SHA-256 hashes locally before the Pod was terminated.
- [Closed lifecycle](closed-lifecycle.json): both validation Pods were terminated, no Pods remained, current account spending was zero, and the local guard had exited. Runpod validation consumed approximately $0.45 of existing credit.

The first image exposed a CARLA readiness bug: a client constructed before the server was available retained its failed connection. A fresh client could connect immediately. The final image recreates the client on each attempt, includes a regression test, and passed both measured boots. The failed candidate and diagnostic log are retained for the audit trail.

## Use and limits

Follow the [launch instructions](../../docs/runtime-image.md). `python3 deploy/launch.py` creates one A40 from the validated image, checks readiness and applies a one-hour limit. The launcher uses the local Runpod key, requires existing credit, and never adds credit. Terminate after exporting results to release Pod storage as well as GPU billing.

The image includes the fly-body assets, simulator and rendering environment. Connectome graph data, checkpoints and recordings are restored into the workspace separately. This check adds no learned driving capability. The Unreal editor/native-fly asset build remains a separate task.
