# Indicator close-up cut

Requested: a clear, slower 25-second story showing the fly using the indicator,
with a smooth 60 fps export, current sponsor artwork and the existing black layout.

The cut opens on the left door/rear of the sponsored Mini, holds on a native CARLA
bumper-indicator close-up paired with a MuJoCo foreleg/stalk close-up, briefly
returns to a wide driving view, then holds on the stalk returning and the signal
switching off. The final two seconds retain the source credits. Request-left,
request-right, target/wheel/CARLA steering and stalk angle remain visible, with
`thedrivingfly.com` in the black header.

## What the close-up established

The CARLA 0.9.16 `vehicle.mini.cooper_s_2021` indicator is the small lamp in the
rear bumper. Its large upper Union Jack taillight is not the right place to frame
the indicator. Direct native tests of off/right/left states showed the bumper
lamp illuminating and cycling. No painted flash, added lamp mesh, light-command
replacement or synthetic neural activation is used in the delivered video.

The body camera is aimed at the actual recorded right foreleg gripping the orange
stalk. The foreleg is highlighted in light gray for visibility. Its joint motion,
stalk threshold and applied CARLA signal come from the same saved controller
run. The on/off captions read the native CARLA light-state bits. The camera does
not infer an indicator from steering direction.

## Replay and provenance

This is another presentation of `runs/roundabout-directed-v1`, not another
training run. CARLA world trajectories and MuJoCo joint poses are interpolated at
60 output timestamps per second. Neural activity holds each original measured
sample until its next sample. The wide-view paid sponsor surfaces are rendered
from their exact exported meshes/UVs and composited using CARLA depth.

Repeated CARLA replay starts exposed a one-frame initial phase difference.
The renderer now starts from a fresh episode and aligns its paused starting pose
to the saved moving trajectory before generating any output. Every rendered
frame must remain within 12 cm of the reference, including previews. The receipt
records both the initial correction and every subsequent native position error.

Source world recorder SHA256:
`d88df50f8e8eec87140023b58c7a60228b8c3661ed0871862957968c89f89544`

Source body trace SHA256:
`fa4ba6676597a36fa4907fadff37a18b89ff8e2a7a3d9037b803864a9d1ea842`

The final run selected live sponsor revision 12, layout 4, seven paid placements,
fetched from https://thedrivingfly.com at 2026-09-10 08:48:43 UTC. Revision 12
arrived during iteration and was incorporated. Left-door and rear placements
were visually checked before the full export. Later purchases require another
fresh export; this run keeps its immutable selected snapshot.

## Verification and retained files

`scripts/verify_indicator_video.py` checks the full decoded 1920×1080, 25-second,
1,500-frame file, changing road/body frames, the original neural-sample indices,
trajectory alignment, physical stalk angles at native signal transitions,
multiple bright/dark cycles in the native bumper-lamp pixels, and darkness before
activation and after cancellation. `verification.json` contains the measured
results; `render-receipt.json` contains the complete frame map.

The native RGB camera video, 1,380 native depth frames, interpolated body poses,
source recorder, original body trace, frozen livery and receipts are retained.
The verified backup inventory includes `runs/roundabout-directed-v1/world-recorder.log`
and `runs/roundabout-directed-v1/body-trace.npz` with their byte counts and hashes.
Future 3D angles can be rendered from the same saved world/body record. Reusing a
finished 2D video alone cannot reveal an unrecorded camera angle.

Edit config: `configs/indicator-closeup-25s.json`.
Renderer: `scripts/render_smooth_roundabout.py`.
Output run: `runs/indicator-closeup-v2`.
Reproducibility snapshot: `reports/2026-09-10-indicator-closeup`.

Vehicle: CARLA 0.9.16, CVC, Universitat Autònoma de Barcelona.
Connectome: MaleCNS / Janelia. Fly: NeuroMechFly / FlyGym, EPFL.
Sponsor names and artwork belong to their respective owners.

Final verified result: 1,500 decoded frames, 25.000 seconds, 1920×1080 at 60 fps; zero repeated adjacent road/body frames. Signal on at 6.317s and off at 19.650s. Native lamp pixels include 272 bright frames and 348 dark frames during signalling. All 1,380 native depth images and the native RGB/body/receipt files were downloaded and their checksums verified.

MP4 SHA256: `93999d02d636417fc0d5a7ba86b274808565971d9a27b296cad2b0a2de10017c`
