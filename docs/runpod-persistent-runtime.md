# Durable Runpod runtime

CARLA, Blender, neural data, checkpoints and recordings belong on a Runpod **network volume**. The ordinary Pod `/workspace` volume survives a stop but is deleted when its Pod is terminated. Network volumes survive Pod deletion and attach to a replacement Pod in the same datacenter.

Runpod's available A40 locations did not offer network volumes when inspected on September 10, 2026. The seeded project volume is in US-IL-1, where the 48 GB RTX 6000 Ada is available. Availability changes; check the catalog before launching. The GPU is currently $0.84/hour and 50 GB standard storage is $3.50/month, billed hourly. Container disk adds a small charge. No automatic credit top-up is performed.

## Layout

- `/workspace/flyhard-runtime/carla-0.9.16`: immutable, verified simulator payload.
- `/workspace/flyhard-runtime/blender-5.2.1`: immutable renderer payload.
- `/workspace/flyhard-runtime/downloads`: retained verified source archives for
  restoring the simulator or renderer without downloading them again.
- `/workspace/flyhard/data`: acquired graph and anatomical geometry.
- `/workspace/flyhard/runs`: checkpoint, source traces, world recorder logs, and outputs.
- `/workspace/flyhard/work`: iteration inputs and receipts.

The new `docker/Dockerfile.volume` starts from a pinned Runpod base, installs Python dependencies once at image build, and omits the simulator and CUDA development toolkit from the image. PyTorch's CUDA runtime libraries remain packaged with PyTorch. The old full image remains selected until a new digest passes a real CUDA/CARLA GPU check. An image build alone is not proof of readiness or reduced cold-start time.

## Seed once

Create a standard network volume in a datacenter supporting both the desired GPU and durable storage. Attach it at Pod creation, with `mounts.network: [{volumeId: ID, path: "/workspace"}]`; omit `mounts.persistent`.

Run `python deploy/seed_runtime_volume.py` on the attached Pod. It downloads the official archives, verifies SHA-256, and atomically promotes complete extracted assets. A repeated run checks receipts and skips completed assets. Normal GPU startup deliberately never downloads these large assets.

New seeds retain their verified archives. Older already-seeded runtimes may have
only the extracted payload; they remain reusable and are not downloaded again
just to fill this archive cache. Native Unreal/CARLA build archives are retained
separately under `/workspace/flyhard-build`; see `deploy/native/README.md`.

A cloud-to-cloud `rsync` from an existing verified runtime is also suitable. Preserve the original pinned image/archive provenance in the asset receipt; copy into a staging directory, verify the transfer, and promote only a complete tree. CARLA's mutable `CarlaUE4/Saved` directory is not part of the immutable payload. A temporary SSH agent can forward only the project key for the transfer; do not copy the private SSH key or the Runpod account key onto a Pod.

## Launch

Use a release JSON containing the immutable image digest, source revision, `runtime_layout: "network-volume"`, the selected GPU, and validation status. With the previous default session closed:

```sh
python deploy/launch.py --release deploy/runtime-volume.json \
  --network-volume YOUR_VOLUME_ID --runtime-seconds 21600
```

A candidate uses `--validate-candidate` and is capped at one hour. For an explicitly authorized parallel validation, isolate **all** local lifecycle state from an existing session:

```sh
FLYHARD_SESSION_DIR="$PWD/work/volume-validation" python deploy/launch.py \
  --release work/volume-candidate.json --network-volume YOUR_VOLUME_ID \
  --validate-candidate --runtime-seconds 1800
```

The corresponding SSH file and receipts are in that session directory. The local credit guard enforces the same $4 reserve, account-wide spend cap and bounded runtime. The image's independent timer uses Runpod's injected Pod key; no account credential is uploaded. On network Pods, guards **delete only the Pod**, retaining the network volume. They reject automatic deletion if `/workspace` is not the network mount. Ordinary Pods still stop, preserving their ordinary workspace.

## Code and sponsor freshness

Each image records its source revision. A new image refreshes packaged source files and preserves displaced iteration edits under `work/source-backups`. A restart of the same image retains local code changes and reports the actual workspace hashes and changed paths in `work/runtime/workspace-source.json`. Datasets and recordings are not replaced by source refresh.

**Before every new recording, export/download the latest live advertisers and verify the current livery.** Never select a sponsor revision because it is already cached on the volume. The current video agent owns that export/preflight; the runtime cache does not declare any sponsor revision authoritative. Record the exact live export revision, layout, sponsor count and hashes with each recording. Existing videos and historic livery directories remain reproducible historical inputs.

## Costs and deletion

Storage continues billing after compute ends. At 50 GB this is about $0.00486/hour ($3.50 per 30 days). Keep an independent local copy of irreplaceable recordings. Deleting a Pod does not delete its network volume; deleting the **volume** destroys that copy of its data. The budget guard never deletes volumes and never adds credit.

References: [Runpod network volumes](https://docs.runpod.io/storage/network-volumes), [S3 API and prices](https://docs.runpod.io/storage/s3-api), [v2 Pod deletion semantics](https://docs.runpod.io/api-reference-v2/pods/terminate-a-pod).
