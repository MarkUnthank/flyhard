# Flyhard: verifiable experiment plan

Status updated 2026-09-09 after the [first bounded pilot](pilot-2026-09-09.md). E00, E01, independent E02 mechanics and the E04 pilot report have evidence. The wheel portion of E03 passed narrowly for one training seed; pedal learning and three-seed replication remain. E05–E09 have not passed. CARLA rendering is verified independently of body control.

## Final success

A trained model built from MaleCNS connectivity processes camera and engineered body-sensory inputs. Its outputs actuate a simulated fly. Leg contact physically operates the wheel and pedals, and measured control positions drive a CARLA vehicle. The vehicle is presented as the battered green Panda-inspired Flyat. Driving, body movement, and computed neural activity on the connectome geometry are recorded from the same episode.

The first release targets a short course with a start, bends, a conspicuous obstacle, and a stop. Road rules, general urban autonomy, biological learning, and recreation of the original fly's mind are not claims of this experiment.

## Proposed architecture

- A sparse recurrent model retains the measured neuron-to-neuron topology after explicit, documented dataset filtering. Aggregate multiple synapses between the same neuron pair; preserve counts and identifiers. Do not silently prune the graph to meet a runtime target.
- Start with simple rate-based neuron states, trainable connection gains and bounded neuronal dynamics. Fix the adjacency mask and audit that learning remains inside it. Record modelling assumptions and neurotransmitter uncertainty rather than treating predicted transmitter identity as a universally reliable synaptic sign.
- Missing early visual processing is an explicit sensory interface. Use a documented spatial input mapping and calibration; an existing FlyVis model is a candidate reference, not an already integrated MaleCNS component.
- Camera and proprioceptive inputs enter designated neural input populations. Only designated neural output populations reach the limb decoder. No direct sensory-to-action bypass.
- Prefer a small limb decoder and bounded joint servos. A more elaborate learned body controller requires explicit documentation and interventions to establish the connectome model's contribution.
- MuJoCo owns fly/cockpit contact physics; CARLA owns vehicle/world physics. One coordinator advances both clocks. Wheel angle and pedal displacement are the only normal vehicle-command source. Map car motion into the cockpit frame and explicitly document supported body-motion feedback and omitted effects.
- Prototype with two active pedals and automatic transmission; manual clutch/gear shifting is a separate future scope decision. The visual design must reflect the controls actually used.
- Record model outputs, applied joint commands, joint states, contacts, wheel/pedal states, vehicle state, timestamps, and selected neural traces. Initial neural visualization uses scalar rate states; any later vector state requires an explicit display reduction.

This architecture is a hypothesis. Library compatibility, sparse backward-pass performance, stable neural dynamics, and the body-to-vehicle interface must be tested before substantial training.

## Rules for every experiment

Before running, save the hypothesis, code revision, dependency versions, seed, data/model hashes, train/evaluation split, success metric, threshold, and runtime cap. Thresholds below are proposed engineering gates. Freeze each experiment's exact configuration before its run; any revision produces a new experiment record rather than changing the interpretation of an old result.

After running, save the command/configuration, metrics, representative success and failure replays, resource use, and the next decision. Report all evaluation attempts. Small development samples are preliminary; final milestone verification uses independent seeds and withheld cases. Use at least three training seeds for claims of repeatable learned performance, and report per-seed results rather than only a pooled score.

Pass means the named capability has been demonstrated at the stated scope. It does not establish later capabilities. A technically invalid run is inconclusive, not evidence of learning failure. After a valid failure, allow a small, predeclared set of targeted changes; do not repeatedly extend runtime without a hypothesis.

## E00 — Reproducible evidence and dependency baseline

Question: Can a clean environment run and replay the components we intend to use?

Work: Pin one body simulator release and a compatible training stack; run an upstream body example, render a short clip, and establish the episode schema. Inspect source licenses and asset provenance. Audit any candidate controller before treating it as a dependency.

Pass: A documented command generates a trace and clip; replay preserves stored simulation timestamps and joint positions. Licenses and versions are recorded. No unexplained dependency on a notebook state or local secret.

Failure decision: Fix or replace the failing dependency before building on it. FlyGM currently has a project-page notice of "Code (Coming soon)" and is research precedent only, not assumed runnable code.

## E01 — Real connectome, real gradients

Question: Can we load the actual graph and train parameters within it?

Work: Acquire versioned annotations, connectivity, and transmitter predictions. Produce a manifest of included/excluded IDs and counts. Check edge orientation, input/output reachability, and disconnected portions. Instantiate the full intended graph. On a synthetic temporal task, run forward and backward passes and inspect parameter updates inside the graph. Tiny test graphs may debug implementation but are not the evidence for full-graph feasibility.

Pass: Graph identity and topology checks pass; states and gradients are finite; gradients reach trainable core parameters; optimization improves the fixed synthetic objective; no edges appear outside the adjacency mask. Record actual peak memory and timing rather than extrapolating from neuron count alone.

Location: Local preprocessing and small correctness tests; full-size training benchmark on the A6000 when prepared.

Failure decision: Fix computation or conditioning first. If runtime requires changing neuron dynamics or connectivity scope, record the tradeoff before retesting.

## E02 — One leg, one physical control

Question: Can the body physically operate a control at all?

Work: Build a simple wheel and a single pedal in the cockpit. Use a diagnostic joint controller to reach and move each independently. Choose a consistent scale, mass, joint-limit, grip/contact, and actuator-force specification. A supported seated posture is allowed and documented. No direct wheel/pedal actuators or joint teleportation may supply successful actions.

Pass: Across 20 reset trials, the leg moves the wheel in both directions and depresses/releases the pedal without numerical instability. Recorded contacts explain the resulting motion. Disabling the relevant contacts/grip constraints removes the response to the same leg command, allowing for passive spring return and existing momentum.

Failure decision: Change reach, cockpit geometry, contact design, or actuator limits before involving the neural model.

## E03 — Learn one control skill

Question: Can the connectome-based model learn useful physical actuation?

Work: First teach wheel-angle tracking, then pedal tracking in separate experiments. Generate demonstrations using the diagnostic limb controller from E02; fit the connectome-based model, then evaluate it closed-loop on the physical cockpit. A small conventional policy is a diagnostic baseline with the same observations and actuator limits. Input here is a requested control position plus body feedback; this is not yet visual driving.

Proposed pass: In at least 90 of 100 held-out target trials, reach within 10% of the control's full travel within two simulated seconds, then hold that tolerance for one second. Evaluate wheel and pedal independently. Report initial versus trained model performance and reproduce across three training seeds before claiming reliable learning.

Failure decision: If the conventional policy fails, revisit task mechanics/rewards. If only the connectome model fails, investigate architecture, conditioning, and optimization. Lower imitation loss without closed-loop success does not pass.

## E04 — First A6000 pilot report

Question: What does an actual training-and-evaluation cycle cost, and is more training justified?

Work: Run E01's full-graph benchmark and one bounded E03 training block followed by held-out evaluation, saving a resumable checkpoint. This is the agreed single-A6000 pilot, using a Runpod on-demand Pod. Prepare scripts locally and record an instance lifetime limit before provisioning. Do not interpret "one cycle" as one optimizer step or a complete successful driving curriculum.

Provider preflight: Verify the exact GPU, allocated CPU/RAM, live price, SSH/file-transfer access, storage persistence, and NVIDIA graphics support in the selected container. Runpod Pods are container-based; do not assume a full VM or that nested Docker is available. Validate CARLA offscreen camera rendering and body rendering on that host. Use storage that survives Pod termination for checkpoints and recordings, or export and verify them before termination. Operate through the official API/CLI and SSH. Previous Lambda instance specifications and cost estimates do not apply.

Measure: Startup/compilation separately from steady-state time; neural forward/backward time; physics time; aggregate control transitions per second; peak GPU/host memory; utilization; evaluation success; improvement over initial weights; actual billed runtime. Add a CARLA camera smoke test before making integrated-driving throughput claims.

Pass: Produce a reproducible report and a checkpoint, including a valid negative learning result if that is what occurred. Performance extrapolations state their workload assumptions. A learning plateau is not an estimate of eventual convergence time.

Decision: Continue on the A6000, fix the model/task, or benchmark another GPU according to the measured bottleneck. Do not automatically begin a long run.

## E05 — Physical cockpit drives CARLA

Question: Does body operation actually control the car?

Work: Connect measured wheel/pedal state to CARLA, initially using the diagnostic limb controller. Validate acceleration, left/right steering, brake, release, and reset. Use fixed CARLA steps and smaller cockpit substeps with an explicit observation/action timing convention. Keep the same body and cockpit physics used in E02/E03. Use a simple proxy vehicle shell while validating the interface.

Pass: Repeated scripted limb-driven manoeuvres produce the expected vehicle response. Locking the wheel removes commanded turns; blocking pedal contact removes commanded acceleration or braking. Vehicle commands match recorded physical control readings. Logs reconcile every sensor frame, body state, and applied command by simulation tick.

Failure decision: Fix the coupling and timing before training visual behaviour. This milestone proves the mechanical/software chain, not autonomous driving.

## E06 — One learned visual turn

Question: Can visual information cause appropriate driving through the complete chain?

Work: Present a small textured corridor with randomly selected left or right bends. First isolate steering at a disclosed fixed speed, then repeat with physical throttle operation. Feed only camera images and documented body/vehicle-sensory feedback to the policy. Road geometry and target route may inform rewards or training demonstrations but must not become hidden policy inputs.

Proposed pass: At least 80 of 100 held-out bend trials complete without wall contact, reported separately for each of three training seeds. Compare against untrained core parameters. Perturb visual inputs and clamp relevant model outputs in matched trials to test causal dependence. The version with automatic speed is intermediate evidence only.

Failure decision: Diagnose visual encoding, neural learning, actuation latency, and camera/cockpit synchronization separately. This is the first major evidence gate for confidence in the final demo.

## E07 — Combine learned skills

Question: Can the controller coordinate wheel and pedals over a useful sequence?

Work: Separate additions: start and stop on a straight; left and right bends; brake for one large obstacle; combine them into a fixed-length course. Use the already demonstrated physical control skills and continue training within the connectome model. Keep any learned limb controller identifiable and bounded in scope.

Proposed pass: For each addition, at least 80 of 100 held-out trials succeed without collisions, hidden autopilot, or direct vehicle-command bypass. For the combined course, success requires crossing the finish and stopping within a predefined region below a predefined speed. Freeze course, speed, and stopping tolerances before evaluation. Report results across three training seeds.

Failure decision: Return to the failed skill or curriculum transition. Do not add traffic or route planning while this task remains unreliable.

## E08 — Attribution and modest generalization

Question: Does the trained connectome model matter, and is success more than a memorized run?

Work: Hold out start offsets, bend geometries, obstacle positions, and lighting. Compare frozen initial core, trained core, and core-disabled conditions while accounting for adapter training. Confirm changes in core weights/dynamics materially contribute. As a separate architecture experiment, retrain degree-preserving shuffled graphs and conventional policies using matched data and compute budgets.

Pass for the demo: Repeatable completion under declared variations and evidence of a causal, learned contribution from the connectome model. Beating shuffled graphs is not required to demonstrate a working controller; it is required for any claim that the fly topology is superior. Post-training lesions alone do not establish that superiority.

Failure decision: Narrow the demonstration claim or continue training; do not claim general driving, biological fidelity, or an architectural advantage without evidence.

## E09 — Flyat and synchronized release

Question: Can we show the genuine result clearly and reproducibly?

Work: Finish the licensed/original Panda-style shell, worn interior, and fly presentation using the accepted cockpit reach/physics. Re-evaluate after visual changes because camera observations may change. Render cockpit, driving, body/contact, and neuron-activity views from the same trace. Record whether playback is real-time or accelerated. Publish setup instructions, dependency/data manifests, model assumptions, evaluation results, and permitted artifacts.

Pass: A new user can reproduce the declared demo within documented requirements; all video panels refer to the same episode and time; the physical control path still passes interventions; the claim matches the measured result. Publish successes alongside evaluation totals and representative failures.

## Reporting confidence

Use an evidence table with each capability marked untested, demonstrated narrowly, reproduced, or failed. Update the overall qualitative confidence after valid experiments, with reasons. Earlier 60–70% success and 200–700 GPU-hour estimates were subjective planning judgments, not measured forecasts. The first visual turn and coordinated driving are stronger evidence than installation success or attractive footage. Predictability of virality remains separate from technical feasibility.

## Next action after the first pilot

Retain the A6000 for the next bounded block. Replicate stationary steering over two additional training seeds; resolve the pedal's recorded fine timestep sensitivity and teach pedal operation. Combine the controls in one cockpit and verify measured control positions against CARLA commands before visual training. The first pilot used one Runpod Secure Cloud A6000 with budget/deadline guards and exported its artifacts; consult its lifecycle receipt before provisioning again.

## Sources

- [MaleCNS downloads](https://male-cns.janelia.org/download/)
- [FlyVis implementation](https://github.com/TuragaLab/flyvis)
- [FlyGym tutorials](https://neuromechfly.org/tutorials/index.html)
- [FlyBody](https://github.com/TuragaLab/flybody)
- [FlyGM project page, checked 2026-09-09; code marked coming soon](https://lnsgroup.cc/research/FlyGM/)
- [FlyGM preprint](https://arxiv.org/html/2602.17997v1)
- [CARLA UE5 quickstart](https://github.com/carla-simulator/carla/blob/ue5-dev/Docs/start_quickstart.md)
- [Runpod Pods](https://docs.runpod.io/pods/overview)
- [Runpod API](https://docs.runpod.io/api-reference/overview)
