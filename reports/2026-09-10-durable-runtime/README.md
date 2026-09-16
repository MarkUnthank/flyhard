# Durable runtime validation — September 10, 2026

The persistent cache is complete. CARLA 0.9.16 and Blender 5.2.1 were downloaded from their official distributions, verified against pinned archive SHA-256 values, and atomically installed. The cache also contains the verified connectome graph, anatomical geometry, selected roundabout policy, world recorder, body trace, frame clock and CNS video. The full raw neural trace remains on the local workstation; it is not required by the current replay.

The published candidate image is **5.37 GB compressed**, compared with **19.56 GB** for the current full image: **72.5% smaller**. Large simulator and Blender assets reside on the network volume. Python/CUDA dependencies and current live-advertiser export tools are built into the image. Startup performs no package installation.

**No startup speed improvement has been demonstrated yet.** The US-IL-1 validator was still downloading image layers after approximately 7 minutes 41 seconds. It was deleted at the conservative account spending bound. CUDA, CARLA and the new renderer components therefore remain unvalidated on this candidate. `deploy/runtime-volume.json` deliberately has `validated: false`; the existing A40 release is unchanged.

Eight storage regression checks passed, covering network-volume preservation, ordinary-volume shutdown, source edits, source deletion and unprivileged traversal. After validator deletion, the API confirmed that the 50 GB network volume survived and the existing A40 was the only running Pod. Storage costs $3.50 per 30 days, billed hourly. No credit was added.

Next: attach the seeded network volume to a bounded candidate validation in US-IL-1, measure CUDA/CARLA readiness, and exercise MuJoCo/PyRender plus a fresh live-livery export before promoting this image. The candidate is available by immutable digest in the adjacent JSON receipt; a successful build is not runtime validation.
