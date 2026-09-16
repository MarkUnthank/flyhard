# Indicator episode: the fly takes a driving test

The next audience-facing capability is indicating, then a roundabout exit challenge. Autonomous driving adds perception, planning, steering, speed and collision avoidance together; this episode isolates a useful, visible skill that we can score. A shareable hook is: **“I taught a fly to use its indicators. Your move, BMW drivers.”** This is an editorial suggestion, not a prediction of reach.

## Small, verifiable releases

1. **Lamp and body mechanics.** Check visible left/right/off lamps on the actual Mini, then diagnostic foreleg commands operating a passive stalk. Repeat with the foot coupling removed. This establishes mechanics only; no learned-indicator claim.
2. **Learn to operate it.** Train the connectome model to choose left, right and neutral from a disclosed request. Score held-out transitions and compare the trained model to its initial state. Preserve the existing I01 gates in `indicators-fallback.md`.
3. **A junction test.** Give a visible route arrow on approaches to left, right and straight routes. Score correct side, timing and cancellation, including trials where it should do nothing. Hold out approach speeds, cue times and junction geometry. The car follows a controlled route while the fly operates only the indicators.
4. **The roundabout episode.** Show “take exit 1 / 2 / 3”; the fly must wait through earlier exits, signal for the selected exit and cancel after leaving. A full successful sequence earns one point. Include failures in the evaluation; choose the video take from recorded runs with its score and seed retained.
5. **Autonomous driving later.** Start with one quiet route and closed-loop lane keeping. Add learned speed control, intersections and hazards as separate gates.

Roundabout timing is a more demanding problem than selecting a left/right command. The current wheel policy resets its state at each decision; it does not remember a chosen exit or count passed exits. Add explicit route intent and a stateful policy, then test its memory with longer waits and varied speeds. A camera alone cannot tell the fly which destination we intended.

## Traffic convention

Working default: right-hand traffic, consistent with the existing CARLA roads and the previous New Yorker video. Use New York's documented exit signalling convention for this benchmark: signal right for the upcoming chosen exit, after passing the preceding exit when applicable. This avoids mixing UK entry-signal rules with right-hand traffic. [NYSDOT guidance](https://www.dot.ny.gov/main/roundabouts/guide-users).

Town03 has a central roundabout and ordinary junctions in the [CARLA 0.9.16 map documentation](https://carla.readthedocs.io/en/0.9.16/map_town03/). Availability and camera suitability must also be checked in the actual runtime.

The first roundabout course uses predetermined routes with appropriate lanes and controlled surrounding traffic; we are testing signal choice and timing. The route controller handles lane selection and vehicle motion. Learned lane selection, yielding and collision avoidance remain separate skills. Keep the route instruction visible before and during the manoeuvre. In training and evaluation, target labels and evaluation-only junction boundaries never enter the policy.

## What viewers see

A 16:9, simple black layout: road and sponsor car on the left; real neural activity above and synchronized fly body below on the right. Keep REQUEST LEFT, REQUEST RIGHT and measured steering angle visible; add a large signal state and the route instruction. Use a short lamp/stalk close-up so the new capability is legible. Keep the distinction between controlled route and fly-operated indicators clear in the caption and methods.

The existing steering footage can support a sponsor announcement while the new skill is trained, provided the sponsor surfaces are actually integrated and verified. Do not label a scripted lamp camera test as learned behavior.

## Sponsor asset handoff

Frozen export: `apps/website/exports/sponsors-r6-2026-09-10`, revision 6, six paid surfaces. `work/indicators/sponsor-handoff.json` records the verified input checksums, paid slot IDs and final model hashes. Do not change the other task's export.

The model is the matching CARLA Mini Cooper S 2021, with separate UV-mapped sponsor surfaces. It is ready for Blender/glTF rendering. Loading its GLB or replacing a single diffuse texture does not integrate those surfaces into the native CARLA vehicle. That still requires a matching Unreal asset integration, or a deliberate synchronized rendering pipeline using the exported model and CARLA's recorded transforms. The [0.9.16 texture-streaming implementation](https://github.com/carla-simulator/carla/blob/0.9.16/Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp#L305) updates static-mesh components, while the main Mini body is the skeletal `SK_Mini2021` asset; seeing its actor name in the API is not proof that the full livery is replaceable at runtime. Verify the left door and rear views, preserve all six paid surfaces and transparency, and record the livery revision in each video manifest.

## First GPU run

The 2026-09-10 A40 preflight uses the existing validated runtime, with a one-hour limit and no additional credit. Scripts are `preflight_indicators.py` (native lamps/maps) and `indicator_experiment.py` (isolated mechanical stalk and removed-grip comparison). Runtime source files are copied explicitly; no new trained model is bundled in the image. Results are recorded separately from the prior wheel videos.

## Preflight result

Both native lamp checks and the complete isolated stalk diagnostic passed. There is no trained indicator policy yet. See `reports/2026-09-10-indicators/README.md` for the evidence, gravity fix, camera-change crash, and remaining integration gates.
