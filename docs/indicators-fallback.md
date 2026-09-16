# Optional demo: a fly that uses its indicators

Status: added to the plan on 2026-09-09. Native lamp and mechanical stalk preflight began on 2026-09-10; learned selection and scenario timing remain untested. See `indicator-episode.md` for the staged follow-up. Full body-driven CARLA driving remains the main goal; this is a smaller fallback and a useful skill to add to the eventual driving demo.

The intended punchline is: **“We taught a fly to use its indicators.”**

## What the fly must actually do

Given the intended route and the approaching junction, the trained connectome model chooses left, right, or off; moves the simulated fly's leg; physically operates an indicator stalk; and causes the corresponding vehicle lamps to signal. It must indicate before the manoeuvre, maintain the correct side through it, and cancel afterward. Straight-ahead cases test whether it can leave the indicators off.

Road appearance alone cannot specify which exit we intend to take. Give the fly a visible navigation arrow, then use camera input and documented motion/body feedback for timing. Evaluation-only junction boundaries and target labels must not leak into the policy. A numeric left/right/off command is acceptable in the earlier actuation test, with that narrower claim stated explicitly.

For the standalone fallback, CARLA follows a scripted route. The fly controls only the indicators, and the video discloses that division. The original full-driving milestone still requires the body to operate steering and pedals. Shared timing and genuine body actuation apply to both versions.

## Three small experiments

| Stage | Work | Proposed evidence gate |
|---|---|---|
| I00: physical stalk | Add a reachable passive stalk with left, neutral and right positions. Use diagnostic leg commands; document any detent/latch assistance. | 20 left–neutral–right–neutral cycles succeed. Disabling contact removes commanded transitions. No direct stalk actuator or pose assignment supplies the result. |
| I01: learned selection | Train connectome parameters to move the stalk from its current state to a disclosed requested state. Keep input/output interfaces fixed and audited, as in the wheel pilot. | 120 held-out transitions, 40 for each target state. Reach the correct state within 2 seconds and hold for 1 second; at least 90% success in each class. Compare initial and trained models; replicate over three training seeds. |
| I02: appropriate timing | Add a visible route cue and camera view while CARLA follows a controlled route. Teach when to activate, maintain and cancel the signal. | 120 held-out approaches per seed, balanced across left, right and straight. At least 90% success in each class across three training seeds, counting the whole signal sequence. |

For I02, freeze the course and timing rules before training. A candidate toy benchmark requires activation 2–4 simulated seconds before junction entry, the correct signal throughout the manoeuvre, and cancellation within 2 seconds after exit; straight approaches remain off. These are engineering test windows, not a universal road-law claim. Vary approach speed, cue timing, junction spacing and geometry so a fixed timer cannot solve every episode. Report wrong-side, early, late, missed, unwanted and uncancelled signals separately.

The model must actuate cancellation in the learned-cancellation test. If a later vehicle has an engineered self-cancelling mechanism, document it and do not credit that action to the model. Mechanical blinking itself is a vehicle function, not something the fly has to learn.

## CARLA and causal checks

CARLA 0.9.16 documents `LeftBlinker`, `RightBlinker`, `Vehicle.set_light_state()` and automatic blinking. Its documentation also warns that vehicle support varies, so verify visible left/right lamp behavior on the selected asset before training. See the [versioned vehicle-light API](https://carla.readthedocs.io/en/0.9.16/python_api/#carla.VehicleLightState).

Measured stalk position is the only source of the indicator flags. Preserve other vehicle-light flags, prevent simultaneous left/right selection, and disable any route controller's automatic indicator management. Do not let a route script or the neural output set indicator flags directly.

Record the navigation cue, camera/world frame IDs, neural states, joint commands, body/contact state, stalk position, indicator flags and visible lamp frames on one simulation clock. Repeat matched episodes with the stalk blocked, leg contact disabled, initial core parameters restored, and the route cue perturbed. The tests should establish that the trained model and its physical leg action both contribute.

## Why this is a useful fallback

This reduces the learned behavior to selecting and timing one three-position control. It reuses the connectome, body simulation, physical-control approach and recording pipeline. We can test it without first solving simultaneous steering, throttle, braking and collision avoidance. Contact mechanics, visual encoding and timing still need experiments; the existing wheel result does not supply an indicator success rate or training-time estimate.

For the video, show the worn green Flyat approaching a junction, the visible navigation cue, a close view of the fly moving the stalk, and the matching exterior lamp. Finish with cancellation and an evaluation tally. Keep the scripted-route disclosure visible in the standalone version. The humour should survive an accurate description of what the model controls.

The 2026-09-10 preflight scripts are `scripts/preflight_indicators.py` and `scripts/indicator_experiment.py`. The stalk uses an explicit point-grip constraint and a physically counterbalanced spring-centred hinge, with no latch or stalk actuator. It is isolated from the wheel for I00. Learning and combined steering/stalk operation require further experiments; the preflight is not evidence of a trained indicator policy.
