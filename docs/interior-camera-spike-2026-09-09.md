# Flyhard: inside the car

The requested spike was a native CARLA camera looking over the fly's shoulder. The native cabin camera works. The delivered five-second preview places the existing simulated fly into that camera using matching perspective, recorded body poses and CARLA depth. The fly is a labelled composite in this preview; it is not yet an actor rendered by Unreal.

The car remains the stock green Mini proxy. The battered Panda is separate work. The preview enlarges the fly for display so it can reach a human-sized wheel; its physical simulation retains the original millimetre units. This is a camera and asset-preparation experiment, with no new training.

## What the spike established

Six native RGB/depth camera positions were surveyed. The final camera is rigidly attached at vehicle-relative `(x=-0.45, y=0.08, z=1.35)` metres, pitch `-12` degrees, yaw `-23` degrees, with a 90-degree horizontal field of view. Moving forward from the rear seat keeps the headrest out of the central shot. Both outputs are silent H.264, 1280 by 720, 25 fps and five seconds long, at normal simulation speed.

The body was simulated again from reset, using the saved neural action sequence from the verified calm recording. Every one of 1,400 body samples reproduced the original joint positions and commands exactly. The left foreleg supplies steering force through its grip on the passive wheel; the right foreleg follows through its passive grip. CARLA steering is calculated from the physical wheel at the start of each 40 ms interval. Both camera sensors and the body are recorded at its endpoint. The camera does not feed the neural model. Requested turns and vehicle speed remain scripted, and vehicle acceleration does not feed back into the supported body.

The complete capture is seven seconds / 175 frames. The delivered clip takes the final 125 consecutive frames, corresponding to body times 2.04 through 7.00 seconds. Native RGB and depth frame IDs match throughout. Maximum camera/body clock error is `1.565e-7` seconds; maximum steering readback error is `1.851e-9`. There are zero collision events. Both final videos decoded fully after download; all 124 adjacent frame pairs show motion.

The fly renderer uses the camera's actual vehicle-relative transform, a fixed display wheel centre `(0.27, -0.41, 1.03)` metres and a scale of 0.16 metres per physical rig unit. That corresponds to a 31.1 cm display wheel and approximately 160 times physical fly size. Native depth provides occlusion by the car interior. Fly lighting comes from MuJoCo, so shadows, translucent wings and the fit against the stock steering wheel still need refinement in the native renderer. The preview is useful for choosing the shot, not evidence of completed Unreal integration.

## Native asset preparation

The bundle contains 53 FBX parts: the wheel and 52 fly body parts, plus per-frame body transforms for all 175 captured frames. These are exported from the actual compiled MuJoCo geometry. No CARLA vehicle assets or Unreal Engine source are included.

All 53 FBX files were imported back into Blender 5.2.0 LTS. Triangle counts and bounds pass; maximum bounds error is below `5e-8` metres. The compiled source meshes contain repeated and zero-area triangles. The exporter explicitly removes 3,894 exact duplicate faces and 85 faces with repeated vertex indices, leaving 118,539 triangles. Original interchange geometry is also retained for inspection. FlyGym's Apache 2.0 license and the Flyhard wheel's MIT license are included.

The interchange geometry uses right-handed X forward, Y left, Z up, in metres. Pose records provide both rig transforms and left-handed CARLA vehicle-relative transforms. The FBX exporter declares X forward and Z up with unit metadata. The CARLA-compatible Unreal 4.26 editor must still verify the imported axes, units, transparency and collision settings. The Blender roundtrip does not substitute for that check.

Unreal source access is currently unavailable to the user's GitHub account. Follow [Epic's account-linking instructions](https://www.unrealengine.com/ue-on-github?lang=en-US): create/sign into an Epic account, link GitHub `MarkUnthank`, and accept the emailed GitHub organization invitation. This unlocks the next build step, rather than completing it automatically. Then prepare the CARLA 0.9.16 Unreal environment, import and cook the FBX parts, disable display-mesh collisions, and drive their transforms from the same recorded body clock. Verify the native fly in RGB/depth before calling the integration complete. CARLA documents the [prop import and cooking pipeline](https://carla.readthedocs.io/en/0.9.16/tuto_A_add_props/).

## Reproduction

Restore the verified `runs/carla-calm-v2` traces and configuration from the earlier demo. The source trace hashes and checkpoint/graph provenance are recorded in the capture's `action-source.json`; the new run does not load the checkpoint or graph. Follow `docs/reproduce.md` for CARLA 0.9.16 and the pinned FlyGym environment. Additional mesh preparation dependencies are installed with `pip install -e '.[body,assets]'`. Blender is needed only for interchange conversion; capture and fly rendering ran on the remote GPU.

Extract the saved actions without loading the full neural activity matrix:

```python
import hashlib, json, numpy as np
from pathlib import Path
source = Path('runs/carla-calm-v2')
out = Path('work/interior-actions')
out.mkdir(parents=True, exist_ok=True)
with np.load(source/'neural-trace.npz') as archive:
    np.savez_compressed(out/'actions.npz', time=archive['time'],
        action=archive['action'], requested_angle=archive['requested_angle'])
with (source/'neural-trace.npz').open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
(out/'source.json').write_text(json.dumps({
    'source_run': str(source), 'source_neural_trace_sha256': digest,
    'extract_sha256': hashlib.sha256((out/'actions.npz').read_bytes()).hexdigest(),
    'source_config': json.loads((source/'config.json').read_text())}, indent=2))
```

With CARLA running, use fresh output directories for each attempt:

```bash
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl PYTHONPATH=src
.venv/bin/python scripts/interior_camera_spike.py --out runs/interior-camera-survey-v1
.venv/bin/python scripts/render_interior_stills.py
.venv/bin/python scripts/capture_interior_replay.py
.venv/bin/python scripts/render_interior_replay.py
.venv/bin/python scripts/qc_interior_video.py
.venv/bin/python scripts/export_interior_assets.py
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/export_interior_fbx.py -- --assets runs/interior-native-assets-v1
```

The static survey uses an independently captured stationary cabin for framing; it is not a synchronized driving episode. Only `interior-replay-v1` produces the synchronized moving preview. Its saved RGB/depth frames and body states allow rerendering without another GPU instance running CARLA.

## Compute and export receipt

Capture and fly rendering used an NVIDIA A40 on Runpod in EU-SE-1. Rendering reported `NVIDIA A40/PCIe/SSE2`. The seven-second capture took 103.57 wall seconds and the five-second composite took 21.43 seconds. Local Blender was used for FBX conversion, and local decoding checked the downloaded videos.

Before terminating the Pod, 395 remote files totalling 286,694,100 bytes were verified against their SHA-256 manifest. The Pod was then terminated; account readback confirmed no Pod and $0/hour spending, with approximately $18.19 credit remaining after billing settled. This spike consumed approximately $0.35. No credit was added. The local budget watcher has exited.

Compact evidence is in `reports/2026-09-09-interior/`. Full RGB/depth frames, poses, videos and asset files remain in the ignored run directories. The scientific limitations of the learned steering controller are unchanged; this spike resolves camera feasibility and prepares interchange assets.
