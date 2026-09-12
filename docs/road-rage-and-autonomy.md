# Next episodes: road rage, parking, autonomous traffic decisions

Approved direction, 2026-09-10: prioritise immediately understandable, funny clips.
Order: green-light horn scene, parallel parking, then recognition and autonomous
responses to traffic situations. This is an execution brief, not evidence that
these capabilities have been implemented or trained.

## 1. “I taught a fly road rage.”

Make a 16:9 clip, approximately 18–25 seconds. Establish a red light, the sponsor
car with its tiny fly, and a car waiting ahead. The light turns green; the front
car hesitates. Cut to the foreleg pressing the horn button and hear the honk.
The front car creeps forward, stops again, and the fly gives a longer honk.
Hold shots long enough to read the cause and response. Cut around recorded
actions; never manufacture a press or neural response to match the storyboard.

Sound is the main comic device. Keep engine idle and street ambience quiet enough
that the first honk lands cleanly. Use a brief, disproportionately assertive car
horn for the tiny fly; preserve an awkward silence while the lead car creeps,
then let a genuinely longer button hold produce the second, sustained blast.
Avoid music or added comedy effects that mask the press, silence and escalation.
Use a self-created or appropriately licensed horn recording, avoid clipping, and
retain exact simulation-event timing. Change timbre and mix for comedy, never
invent extra honks or extend a press beyond the measured hold.

Stage the lead car and light. The fly's own horn actuation must be real. For this
first episode, disclose structured traffic observations in the methods; do not
claim that it recognised the light from pixels. Neither elapsed episode time nor
a “honk now” cue may enter the learned decision policy. A policy may retain
internal memory to learn how long the lead car has been stationary on green.

### Build and verify in order

1. Add an isolated passive, spring-return horn button to the body simulation.
   Fly joint actuators move a foreleg; measured button travel triggers the horn.
   There must be no actuator on the button and no direct policy-to-audio bypass.
   Verify press, release and repeated operation. Remove the foot coupling/contact
   and confirm that the same commands cannot press it.
2. Integrate it with the wheel, resolving which leg leaves the wheel to press.
   Check steering stability and release. This is a mechanics diagnostic, not
   proof of learning.
3. Train press/release motor control through the connectome model. Compare with
   the untrained model and the disabled physical coupling. Save neural state,
   limb positions, button travel and output transitions on one simulation clock.
4. Train a context-based decision using observed light state, lead-car range and
   relative motion. Randomise the red duration, green delay, lead-car motion and
   gap. Include red-light waits, prompt departures, and pedestrian-blocked green
   lights as quiet examples. Keep reward labels and scenario phase private to
   training/evaluation; they must not appear in observations.
5. Evaluate held-out combinations and seeds before selecting a take. Proposed
   first gate: at least 90% successful responses over 100 held-out opportunities,
   no more than 5% false honks over 100 quiet examples, and successful physical
   release in every trial. These are project targets, not established results.
6. Record the funny scene from a passing policy. Save RGB camera streams, world
   state, body and neural traces, checkpoint hashes, seed, and sponsor receipt.

Verify horn/audio support in the actual CARLA build before implementing the
sound path. If sound must be added during export, derive its onset and duration
solely from measured button events and describe it as event-synchronised sound.

Follow AGENTS.md before every capture or preview: refresh live advertisers,
verify the immutable livery, preserve sponsor surfaces, and check left door and
rear views. Keep the black layout, thedrivingfly.com, existing steering/indicator
readouts, and add a simple HORN state. Rendering does not establish a new learned
capability; retain the evaluation evidence separately.

## 2. “I taught a fly to parallel park.”

Use an obviously generous space between two cars. The comic payoff is hesitant
corrections and a recognisable final result. If a failed attempt is funny, show it
as a failed attempt; do not inject extra steering mistakes for the learning claim.

Begin with structured relative geometry. The goal is a parking space, not a
sequence of steering requests. The learned controller must choose steering,
forward/reverse and speed; measured body-operated controls drive CARLA. Pedal and
gear-selection mechanics are new prerequisites, not capabilities established by
the existing wheel/stalk rig. A steering-only diagnostic may use controlled
speed but must be labelled accordingly.

Hold out space widths, approach offsets and obstacle positions. Report collision
rate, final pose error, time and direction changes, plus results with the learned
core reset. First proposed complete gate: 80% collision-free parks over 50 held-out
trials, inside the marked bay, within 0.3 m and 10 degrees of the target pose.
Treat that as a scoped parking benchmark, not general autonomous driving.

## 3. Recognise traffic and choose what to do

Replace supplied situation descriptions with sensor observations in small steps.
Keep destination intent available: knowing where to go is different from being
told which control to operate.

1. **Red/green stop and go:** camera observations, learned brake/throttle choice,
   then physical pedal actuation. Hold out light locations, timing, weather and
   vehicle distance. Score stop-line violations and unnecessary waiting.
2. **A green light does not always mean go:** add a stopped vehicle or pedestrian
   crossing. Test whether it waits until the path clears, including unfamiliar
   combinations. This also tests whether horn use is situation-aware.
3. **Follow traffic:** combine obstacle response with learned lane keeping and
   speed. Score collisions, lane departures and progress against simple baselines.
4. **Junctions and parking from sensors:** combine the earlier skills only after
   each passes independently. Re-evaluate on unseen layouts and traffic seeds.

Use a conventional visual encoder if useful, with a documented boundary: it
extracts visual features; the connectome-based controller selects motor actions.
Do not let an external driving agent select the manoeuvre behind that interface.
CARLA ground truth can provide training labels and evaluation measurements, but
must not leak into the deployed policy's observations. Audit that input path and
test counterfactual scenes, such as the same green light with and without an
obstruction. State model size, trained parameters, engineered sensory/motor
mappings and the tested domain alongside each public capability claim.

## Current implementation boundary

Local inspection on 2026-09-10 found wheel/stalk mechanics and an indicator policy
whose features include a requested wheel angle. The capture script documents
conventional route requests and scripted speed. No horn implementation was found
in src/ or scripts/. This brief introduces no changes to those active paths and
does not start a Pod, train a checkpoint, or produce a recording.
