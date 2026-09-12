# Flyhard — roundabout indicators and unhinged steering

You asked for a learned roundabout indicator policy with simulated traffic, the
revision 6/layout 3 sponsor livery, and a faster version where the fly physically
steers and indicates together. Both 1920×1080 videos are complete.

| Video | Length | What the fly controls | Recorded behaviour |
| --- | ---: | --- | --- |
| `flyhard-roundabout-indicators-16x9.mp4` | 28.85s | Indicator stalk; CARLA BasicAgent drives the route | Correct third-exit signalling and cancellation; one continuous contact with a Tesla |
| `flyhard-roundabout-unhinged-16x9.mp4` | 16.05s | Both passive wheel and stalk, through separate forelegs | 48.3 km/h peak; contact with Lincoln traffic; correct first-exit signalling and cancellation |

Both play at real speed and include two seconds of attribution. The faster
version deliberately adds erratic steering requests and a higher speed target.
Its collisions remain visible. Contact callbacks are recorded per simulation
frame: 6 in the first run and 174 in the second, not 6 and 174 distinct crashes.

## What was learned and verified

One model uses the measured MaleCNS graph to output fourteen foreleg joint
targets. The left foreleg grips a passive wheel, and the right grips a passive
indicator stalk. Only graph edge gains and neuron leaks are trained; sensory
encoding and motor readout remain fixed. There is no wheel or stalk actuator.

Forty CARLA traffic episodes covered ten direct entry/exit combinations and
14–16 surrounding vehicles. Twenty episodes trained the model, ten selected
the checkpoint, and ten were held out. Episode duration varied from 13.25 to
62.2 seconds. A car was within 25m for 90.5% of recorded frames.

Training took 7.99 minutes on an NVIDIA A40.
The selected checkpoint is step 800, chosen before testing.

| Check | Result |
| --- | --- |
| Held-out physical signalling episodes | 10/10 passed |
| Mean per-episode signal frame accuracy | 98.1% |
| Mean wheel tracking RMSE while signalling | 0.69° |
| Reset learned graph parameters, same first three test episodes | 0/3 passed |
| Disconnect stalk grip, same first three test episodes | 0/3 passed; steering still tracked |
| Mechanical wheel/stalk independence and grip-removal checks | 15/15 passed |
| Repository tests | 12 passed |

Both live recordings also passed the signalling checks. Success requires a
right signal in the permitted approach window, continuous signalling through
the selected exit, cancellation afterward, no left/early signal, and arrival
at the route endpoint. These are simulator task criteria for right-hand traffic.

The video, body and neural records share one 50ms clock. Native CARLA RGB/depth
frame IDs match; light-state readback matches the stalk-derived commands.
Every combined-video steering command equals its recorded physical wheel
measurement times the declared gain. The CNS display uses actual MaleCNS
geometry coloured by recorded model states. The video files decode fully and
match the GPU render hashes.

## Scope and decisions

The policy receives position, heading, velocity, destination and nearby traffic
measurements, plus a requested steering angle. Indicator timing is learned.
There is no episode timer, requested signal, teacher label or route-progress
index in the policy input. Navigation supplies steering requests and speed is
scripted. This is a single-seed, navigation-assisted pilot on one map; visual
perception, learned route planning and the larger replication gate remain open.

The general route planner initially sent two combinations on city detours. The
data collector now follows bounded, reachable lane topology and uses BasicAgent
for the ego car. Four completion flags needed a scoring-only correction: those
cars had stopped exactly 3m from their goals, while the earlier check used a
slightly different exit-distance endpoint. The full final training pass includes
all forty episodes. Original data and the correction audit are preserved.

The supplied sponsor meshes align with CARLA's Mini without manual repositioning.
All six paid surfaces retain their existing UVs, artwork transforms and alpha.
Blender renders them in the recorded camera frame; native CARLA depth hides them
behind intervening vehicles. Left-door and rear views were inspected. This is a
presentation composite; the Unreal skeletal vehicle has not been rebuilt.
The snapshot is explicitly revision 6, layout 3.

## Handoff and next step

Use the short unhinged cut for the hook and the longer indicator cut for context.
A suitable caption is: **“It learned the indicators. The driving still needs work.”**
Describe it as a fly-connectome model; the videos demonstrate motor control and
learned signalling with navigation assistance.

`flyhard-roundabout-evidence.zip` includes the selected checkpoint, traffic
observations, evaluation records, source, artwork and reproduction instructions.
The complete synchronized recordings remain in the repository's
`runs/roundabout-normal-v1` and `runs/roundabout-unhinged-v1` directories.
All 966 exported files (1.50 GB) were hash-verified before termination.

The GPU Pod is terminated. Runpod reports no remaining Pods and $0/hour.
This session cost **$0.51**. No credit was added.

Reproduction commands and the precise control/scoring contract are in
`docs/roundabout-training.md`. The new Blender installer pins the same official
5.2.1 archive used here. The published runtime image remains the prior release;
sync the new source and install the simulator extra/renderer before the next run.

Vehicle: CARLA 0.9.16, Computer Vision Center (CVC), Universitat Autònoma de
Barcelona. Connectome: MaleCNS, Janelia/FlyEM, CC BY 4.0. Body: NeuroMechFly/FlyGym,
NeLy, EPFL. Sponsor names and artwork remain the property of their owners.
