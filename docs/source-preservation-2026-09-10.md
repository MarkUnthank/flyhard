# September 10 source preservation

This snapshot stores the simulation, video and infrastructure work that was still
local after the parking videos were exported. It is based on `f9765cd` from the
current GitHub `main`, preserving the newer website checkout, payment and social
image work. It does not deploy the website, launch a Pod or promote a runtime.

## Entry points

| Work | Source and evidence |
| --- | --- |
| Indicators and roundabouts | `src/flyhard/indicator_*.py`, `roundabout*.py`, `scripts/train_roundabout.py`, `capture_roundabout.py`, `evaluate_roundabout.py`; `reports/2026-09-10-indicators/` |
| Parallel parking | `src/flyhard/parking*.py`, `scripts/prepare_parking_data.py`, `train_parking.py`, `evaluate_parking.py`, `merge_parking_benchmark.py`, `verify_parking_benchmark.py`; `reports/2026-09-10-parking/RESULTS.md` |
| Camera, CNS, body and sponsor presentation | `scripts/render_*.py`, `recompose_parking_*.py`, `retime_directed_video.py`, `src/flyhard/sponsor_view.py`, `steering_hud.py`, `video_branding.py` |
| Latest edit of existing videos | `scripts/edit_parking_montage.py`; the source hashes and timeline are in `reports/2026-09-10-parking/fast-edit-receipt.json` |
| Current advertiser export | `scripts/refresh_live_livery.py`, `src/flyhard/live_livery.py`; `docs/live-livery-recording.md` |
| Persistent runtime and spending guards | `deploy/`, `docker/`, `scripts/runpod_control.py`, `runtime_manifest.py`; `docs/runtime-manifest.md`, `docs/runpod-persistent-runtime.md` |
| Native livery build and import | `deploy/native/`, `scripts/export_native_livery.py`, `verify_native_livery.py`; `deploy/native/README.md` |
| Historical design assets | `apps/mini-livery/sponsors/r8-layout4/`, `taxi-billboard/`, `taxi-billboard-smaller/`, `carla-billboard-import/` |

The montage editor uses the two original r20 exports under
`~/Desktop/Flyhard-parking-2026-09-10/` and the recorded cameras for seeds 34024,
34048 and 34049 under `work/parking-punchy-edit/<seed>/camera.mp4`. Those video
inputs are not in Git. It crops the existing fly take and labels its independent
replay; it does not simulate new body or vehicle motion. FFmpeg must be on PATH.
`--assemble-only` reuses the already composed shot files in that work directory.
The public-domain Mozart source, license provenance and checksum are included
under `assets/music/mozart-k525/`.

## Evidence and unfinished work

- The parking gate failed: 0/50 learned parks and 0/50 reset-core parks. Original
  per-trial outcomes, collision definitions and model/control audit results are
  retained; no unsuccessful trials were removed.
- The final edit is 30 seconds at 1080p60, with 32 attempts visible at 6.4 seconds.
  Its receipt describes preserved r20 artwork and excerpts from all 50 trials.
  It is not a new sponsor export or a new simulation run.
- Native source compilation progressed, but clean import, cooking, native visual
  proof and final packaging remain unfinished. Helper scripts are preserved as
  development work, not a ready native vehicle release.
- The smaller runtime candidate remains `validated: false`. Its image was built,
  but the new-host CUDA/CARLA startup gate was not completed. No default changed.
- Dated reports are historical observations, including infrastructure status.
  They do not establish that any Pod is running or stopped today.

## Public repository boundary

Original code, tests, dependency pins, run configurations, public scientific
results, attributed art/model snapshots and small provenance receipts are stored
here. Existing current website sources and base models were retained from GitHub;
older local website variants were already committed, formatting-only, or
superseded by later payment and social-image changes.

Credentials, private sponsor-credit receipts, press outreach/contact records,
provider account readbacks, raw recordings, checkpoints, large datasets, Unreal
checkouts/binaries and build caches remain local or in private persistent storage.
The original working directory and its source hashes were preserved during this
reconciliation. Published receipts omit account balances and use portable paths;
the unsanitized originals were not altered. Historical sponsor snapshots are not
fallback assets for a fresh recording.

## Verification of this snapshot

- 69 Python tests passed using the existing local Python environment.
- 124 Python files parsed; 18 shell scripts passed `bash -n`.
- All 11 files named in the r8 sponsor checksum manifest matched.
- Gitleaks 8.30.1 reported no findings. An additional literal-value check found
  none of the available local credential values in the curated checkout.
- The original 338 changed/untracked files still matched their initial SHA-256s.
- No GPU run, native build or container rebuild was performed for this PR. The
  montage editor's Desktop path and malformed crop command were corrected; its
  complete video export was not repeated as part of source preservation.

Review before merging. The intended next development work is to improve the
controller against fresh held-out parking cases, or resume the separately gated
native integration. This snapshot does not claim either task is complete.
