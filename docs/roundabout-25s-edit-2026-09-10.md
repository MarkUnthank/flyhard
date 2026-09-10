# Roundabout: 25-second edit

The first directed cut switched shots too quickly to understand the foreleg and
indicator. This version keeps the same recorded episode and gives each action
more screen time. It uses labelled slow motion; it is not a new 25-second drive.
All panels are retimed together, retaining every source frame in order.

| Screen time | Shot | Hold |
| --- | --- | --- |
| 0.0–3.5s | Sponsored car arrival | 3.5s |
| 3.5–8.5s | Fly pulls the stalk | 5s |
| 8.5–12.5s | Native indicator flashes | 4s |
| 12.5–17.5s | Steering, traffic and contact | 5s |
| 17.5–21.0s | Fly cancels the signal | 3.5s |
| 21.0–23.0s | Exit view | 2s |
| 23.0–25.0s | Attribution | 2s |

The black header retains `thedrivingfly.com`. Request left/right, target angle,
measured wheel and stalk angles, applied CARLA steering and signal state remain
visible. Sponsors use revision 6, layout 3. The original videos are preserved.

## Reproduce

On the GPU, with the project environment activated:

```sh
python scripts/retime_directed_video.py \
  --input work/iteration-25s/source.mp4 \
  --plan configs/roundabout-edit-25s.json \
  --output work/iteration-25s/flyhard-roundabout-directed-25s-16x9.mp4
```

The plan requires the exact SHA of the branded 15.55-second master. The script
uses NVIDIA NVENC and writes a receipt with each output frame's source index.
An explicit `--encoder libx264` option supports machines without NVENC.

## Verified export

- A40/NVENC encode and full decode: 23.4 seconds total.
- 500 frames, exactly 25 seconds, 1920×1080, 20 fps, H.264/yuv420p.
- All 311 original frames retained; no motion-interpolated frames.
- All 460 action frames visibly labelled `SLOW MOTION`.
- Every exported panel compared against its mapped source frame. Maximum
  per-frame mean absolute RGB difference was 1.71/255 for road footage and
  below 0.57/255 for neural, fly, steering and website regions.
- Download matched the remote SHA:
  `c7fcc59ddce19288bff77760b55918aa5ae6d9bb463af9443a6072a062b32914`.
- Six shot previews inspected, including the stalk, lit indicator, steering,
  signal cancellation, and left/rear sponsor views.

Receipts are in `reports/2026-09-10-directed-25s/`. The native world recorder,
original four cameras, body and neural traces remain in
`runs/roundabout-directed-v1/`; see the original directed-recording notes for
the simulation evidence and limitations. Cabin fly and sponsor surfaces remain
camera/depth-matched composites. Navigation and speed are engineered inputs;
this edit adds no autonomous-driving claim.

The iteration Pod is deliberately kept running under its credit/deadline guard.
Current Pod state is recorded in ignored `work/runpod-session.json`; it must
not be inferred from the earlier recording's termination receipt.
