# Indicator preflight — 2026-09-10

We tested the mechanics for the next Flyhard episode: a fly using an indicator stalk, then learning when to signal at junctions and a roundabout. This run trained no indicator policy and applied no sponsor graphics to CARLA.

## Verified

- The packaged A40 runtime passed CUDA and CARLA readiness in 345.45 seconds after the provider request; the container itself took 20.05 seconds. No package installation at startup.
- Town03 is installed. Its central roundabout was identified from OpenDRIVE arcs and captured from overhead.
- The native Mini's left and right lamps blink visibly at both front and rear. All 240 pairs of camera frames match world frame IDs. Pixel checks found six on/off transitions on each requested side, no opposite-side illumination, and no illumination after cancellation.
- The isolated, passive stalk completed 20 left–off–right–off cycles (80 requests). Each final 0.2-second hold stayed within the 0.08-radian gate; the worst error was 1.35 degrees.
- Repeating all 80 requests with the engineered foot grip disabled produced zero stalk motion. No actuator drives the stalk. A physical counterweight balances gravity, and a spring centres the lever; there is no latch.
- The stalk clip was rendered on NVIDIA A40, 1280×720, 25 fps, 8 seconds, H.264/yuv420p. The lamp clip is 1280×720, 20 fps, 12 seconds. Both were visually inspected.
- All 25 remote run artifacts (15,783,406 bytes) were downloaded and verified by SHA-256 and size.

## Limits and failures

These are diagnostic mechanical tests. The leg commands are kinematic diagnostic targets, not connectome outputs. Lamp and stalk recordings are separate tests. The next stage must learn the requests, combine body and lamps on one clock, and then learn scenario timing. There is no measured learned-indicator accuracy yet. The stalk is isolated from the steering wheel; simultaneous operation remains a separate integration gate.

The first unbalanced lever sagged under gravity and failed its angle bound. Adding a mirrored physical counterweight corrected this, without applying motor torque to the stalk.

CARLA segfaulted while changing scouting cameras, causing the runtime container to restart and interrupt the first counterbalanced test. The complete rerun with no concurrent CARLA camera changes passed in 102.70 seconds. The aerial image was saved before the crash; the second scouting view and final frame metadata were not. The camera-change crash still needs diagnosis before long scenario recordings.

Sponsor revision 6 has six paid surfaces and all 18 input checksums passed. The exported Mini preserves the correct base vehicle geometry, but the separate sponsor surfaces have not been integrated into CARLA's native vehicle. See the episode plan for this handoff and the texture API limitation.

## Reproduce on the packaged GPU runtime

```sh
source docker/activate.sh
python scripts/preflight_indicators.py --out runs/indicators-preflight-new
python scripts/indicator_experiment.py --out runs/i00-stalk-new
```

Run the mechanics diagnostic independently of camera scouting. The two scripts deliberately contain no learned-policy claim. Keep requested direction and measured control state visible. Do not promote these diagnostics as the finished indicator episode.

The next step is I01: train left/right/off operation and evaluate held-out transitions against the initial model. Then add route cues, appropriate timing and cancellation, followed by the chosen-exit roundabout challenge. The proposed full sequence is in `docs/indicator-episode.md`.
