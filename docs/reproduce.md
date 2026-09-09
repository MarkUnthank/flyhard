# Reproducing the first pilot

The pilot ran on one Runpod Secure Cloud RTX A6000 (48 GB), with 9 vCPUs and 50 GB host RAM, in EU-SE-1. The observed GPU price was $0.53/hour; total account spending while running was $0.558/hour including the configured 200 GB storage. These are historical observations, not a current offer or availability guarantee.

Use the verified CUDA image:

```
runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35
```

Python 3.12, PyTorch 2.8.0+cu128, FlyGym 2.1.0 pinned to `38c8ec61034cd59bc5ba0de20688d4a3c0000d60`, MuJoCo 3.9.0 and CARLA 0.9.16 were exercised together. The full observed package inventory is in `reports/2026-09-09/environment.lock.txt`; the constraint file pins the relevant computational dependencies. The bootstrap, tests, CARLA installation, and saved checkpoint inference also passed on a second fresh A6000 host in US-TX-1 for the video experiment. Training has not been repeated across seeds.

The second launch rejected a digest-form image reference with HTTP 500; no Pod was created. The tag-form reference above succeeded. The example configuration therefore uses that tag; the digest records the originally verified image provenance.

## Provisioning and budget

`scripts/runpod_control.py` reads `RUNPOD_API_KEY` from the environment or local `.env`. Never upload that file. The v2 API manages lifecycle; the balance read uses Runpod's GraphQL endpoint. The example Pod configuration exposes SSH only. Check allocated CPU/RAM, actual price, direct SSH access and auto-pay settings before a paid run. The original account's auto-pay was visibly disabled.

The launcher restricts this pilot to one GPU, an estimated $0.90/hour ceiling, a six-hour lifetime, at most $6 spent, and a $4 balance reserve. `watch` is an independent local guard. `pod_deadline.py` additionally stops the Pod at its deadline using Runpod's injected Pod-scoped token; no account API key is uploaded. These scripts never purchase credit. A stopped Pod retains paid storage, so verified exports must precede termination.

The local controller expects an SSH key at `secrets/runpod_ed25519.pub` and writes ignored lifecycle records under `work/`. Example preparation:

```bash
mkdir -p secrets work
chmod 700 secrets
ssh-keygen -t ed25519 -N '' -f secrets/runpod_ed25519
python3 scripts/runpod_control.py balance
python3 scripts/runpod_control.py launch configs/runpod-a6000.example.json
python3 scripts/runpod_control.py status
```

Record the returned direct SSH host/port in a private SSH configuration. Transfer tracked code and the experiment scripts, never `.env`, credentials, local caches, or the whole home directory. Runpod's persistent volume is NFS: use `rsync -rltz`, because `-a` attempts unsupported ownership changes.

## Environment inside the Pod

From the copied repository:

```bash
bash scripts/bootstrap_runpod.sh
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl PYTHONPATH=src
.venv/bin/pytest -q
.venv/bin/python scripts/body_baseline.py --out runs/e00-a6000
```

The container protects its global Python environment; the virtualenv uses its existing CUDA PyTorch through `--system-site-packages`. Native EGL and Vulkan libraries are necessary even for offscreen rendering. The tested physics runs on CPU; the connectome runs on CUDA.

## Data and training

The raw annotation/transmitter/connectivity downloads total about 1.1 GB. Preprocessing retains all edges whose endpoints pass the documented neuron filter; there is no extra small-edge pruning. The resulting graph file is about 0.31 GB, and the directory also preserves excluded IDs. Allocate several GB for data and each resumable checkpoint.

```bash
python3 scripts/acquire_connectome.py
.venv/bin/python scripts/prepare_graph.py
.venv/bin/python scripts/benchmark_core.py --out runs/e01-core-v2
.venv/bin/python scripts/wheel_experiment.py --out runs/e02-wheel
.venv/bin/python scripts/pedal_experiment.py --out runs/e02-pedal
.venv/bin/python scripts/train_wheel.py --out runs/e03-wheel-pilot --steps 600 --seconds 900 --batch 16 --seed 123
.venv/bin/python scripts/record_learned_wheel.py capture
.venv/bin/python scripts/record_learned_wheel.py render
```

Use a new output directory for every changed configuration. The E03 wall time was 11.4 minutes, including demonstrations and two 100-trial physical evaluations; optimizer updates alone took 3.1 minutes. These figures do not forecast full driving training.

`checkpoint.pt` contains model parameters, immutable topology/interface buffers, optimizer state, experiment configuration and completed optimizer-step count. It is sufficient for inspection and manual optimizer resumption. There is no command-line resume implementation or exact RNG-state continuation yet.

## CARLA rendering smoke test

The official archive is 8.35 GB; extracted files use about 19 GB. Keep the archive on persistent storage and unpack to the container's local disk. The installer verifies the recorded archive hash and uses `--no-same-owner`.

```bash
bash scripts/install_carla.sh
bash scripts/start_carla.sh > work/carla-server.log 2>&1 &
# Wait for the server to finish starting, then run the client.
.venv/bin/python scripts/carla_smoke.py
```

The startup helper runs Unreal as the image's `ubuntu` user because Unreal refuses root. CARLA RPC stays inside the Pod's unexposed ports. The smoke test waits for exactly matching world/camera frame IDs in synchronous mode. It uses scripted vehicle commands and does not satisfy body-driven or autonomous driving. Stop CARLA while measuring isolated neural training so that rendering does not confound the timing.

## Export and shut down

Run `python3 scripts/verify_artifacts.py create` on the Pod, copy its manifest and result directories, then run `python3 scripts/verify_artifacts.py verify` locally. It compares SHA-256 hashes and file sizes for the graph, checkpoints, and recorded states. The replay's locally extended rendering metadata is explicitly excluded; its underlying trace remains verified.

After successful verification, record `exports_verified: true` in the private `work/runpod-session.json`, terminate through `runpod_control.py`, and verify that the Pod is absent from the API and spending is zero. Preserve a lifecycle receipt with the final balance. Large artifacts stay outside Git; compact configurations, all evaluation scores, provenance, and the report belong in Git.
