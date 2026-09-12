# Flyhard: directed roundabout cut

[Play the 15.55-second video](flyhard-roundabout-directed-16x9.mp4)

The requested rerun adds a moving orbit camera, an exterior indicator close-up,
and a native cabin camera. The existing trained checkpoint still operates the
physical fly's wheel and stalk. No retraining was needed. All four cameras were
captured simultaneously with RGB and lossless native depth.

| Time in delivered video | Shot |
| --- | --- |
| 0.00s | Orbit around the sponsored Mini |
| 2.35s | Inside the cabin as the foreleg pulls the stalk |
| 4.60s | Close-up of the native indicator flashing |
| 6.60s | Steering, traffic and the collision |
| 10.15s | Cabin shot as the signal is cancelled |
| 11.95s | Orbit on the exit |
| 13.55s | Attribution |

The first half-second was trimmed to remove initial texture streaming. The rest
is one uninterrupted timeline at normal speed. Steering request left/right,
requested angle, measured wheel/stalk angles, applied steering and signal state
remain visible. Foreleg framing tightens during the stalk shots. The CNS panel
shows the new run's actual model states on the original MaleCNS geometry.

The fly in the cabin is a camera-matched MuJoCo composite using native CARLA depth.
It is not an Unreal actor. The sponsor surfaces are also presentation composites
from the supplied revision 6/layout 3 export. Their original UVs, image transforms
and alpha were retained. Camera cuts, the closer crop and sponsor overlays do not
change the physical simulation or neural actions.

## Verified

- One 14.05-second drive: 281 synchronized simulation frames at 20 fps.
- Peak speed 48.3 km/h, with actual traffic contact retained.
- All signalling criteria passed, including the exit and cancellation.
- Measured-wheel-to-CARLA steering error: 0.0.
- Maximum body/camera clock error: 2.09e-07 seconds.
- All four camera RGB/depth IDs match; maximum attached-camera transform error was 6.5e-06.
- The lamp close-up contains multiple bright/off cycles in native RGB.
- All 311 delivered video frames decoded: H.264, 1920×1080, yuv420p, 20 fps.
- All 1,377 exported files (1.88 GB) were hash-verified.

Navigation supplies steering requests and speed remains scripted, as in the
previous pilot. This recording adds camera direction; it does not establish
visual autonomous driving. The 174 collision callbacks are repeated contact
notifications, not 174 separate crashes.

## Saved for new angles

The full recording is retained at:

`runs/roundabout-directed-v1`

It includes four native camera videos and depth sequences, the fly's complete
body and neural traces, car/camera transforms, per-frame vehicle states, the
edit plan, all sponsor projections, the original render and the delivered cut.

The new [world replay log](flyhard-roundabout-world-recorder.log) was enabled with additional data. It was loaded
back into CARLA and 271 interior trajectory samples matched the captured car positions
exactly. Future road-camera angles can therefore be rendered from this saved
world replay; the policy does not need to drive another episode. CARLA and a GPU
are still needed for new native camera footage. Fly/CNS views can be rerendered
from their saved traces.

See [CARLA's recorder documentation](https://carla.readthedocs.io/en/0.9.16/foundations/#recorder).

The main implementation is `scripts/capture_roundabout.py --directed`,
`src/flyhard/shot_cameras.py`, `scripts/direct_roundabout.py`,
`scripts/render_directed_roundabout.py` and `scripts/verify_roundabout_replay.py`.

The A40 became ready in 6.6 minutes. A slow local upload was replaced with direct
GPU downloads from the public data sources; the rebuilt graph and anatomy both
matched the original byte hashes. Capture took 3.4 minutes. The new recorder and
camera source are saved locally; the published runtime image has not been rebuilt.

Vehicle: CARLA 0.9.16, Computer Vision Center (CVC), Universitat Autònoma de Barcelona.
Connectome: MaleCNS/Janelia, CC BY 4.0. Body: NeuroMechFly/FlyGym, NeLy, EPFL.
Sponsor names/artwork remain the property of their owners; livery revision 6, layout 3.

The Pod is terminated; verified inventory is empty and spending is $0/hour.
This run cost $0.20, leaving $16.88 of the existing credit. No credit was added.
