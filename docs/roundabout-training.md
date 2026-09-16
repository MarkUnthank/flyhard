# Roundabout signalling and combined steering

This pilot uses the MaleCNS traced-neuron graph to command a physical
NeuroMechFly. The left foreleg grips a passive steering wheel and the right
foreleg grips a passive indicator stalk. Neither control has an actuator.
Fourteen leg-servo targets come from one connectome model.

The input is structured navigation and traffic information: GPS position,
heading, velocity, destination, and the nearest simulated car's relative
position and velocity. A separate requested wheel angle supplies the steering
instruction. This is navigation-assisted motor control, not camera perception
or learned route planning. No indicator request, desired stalk angle, episode
clock, route-progress index or scoring label is supplied to inference.

Only the measured graph's bounded edge gains and neuron leaks are trained.
The spatial population encoder, signed sensory mapping and motor readout are
fixed. Neural state is reset for each four-step decision. The model does not
claim biological dynamics, synaptic signs or a validated sensory/motor mapping.

## Data and learning

`collect_roundabout.py` runs CARLA Town03 with a waypoint-following BasicAgent
for the ego car and independently simulated Traffic Manager cars. The traffic
seed, speed and requested exit vary. A bounded lane-topology search excludes
city detours. The initial pilot has ten direct entry/exit combinations and
four episodes each: two training, one validation, one test.

Teacher labels request the right signal from 30m before to 10m after the
selected exit boundary. That boundary is the last planned waypoint within 34m
of the junction centre. These are explicit simulator task labels for right-hand
traffic, not a complete legal driving standard. Offline inverse kinematics
turns the labels and independent random wheel instructions into leg targets.
The teacher and IK solver are absent during learned inference.

Checkpoints are selected using validation loss. The final test set must remain
unused until that choice is fixed. Tests replay held-out CARLA observations
through a fresh physical fly, then separate live captures couple the fly back
to CARLA. Report those two types of evidence separately.

Episode success requires an initial right signal 40–16m before the exit
boundary, continuous right signalling from 14m before through 5m after it,
cancellation by 20m after it, no left/early signal, and arrival within 3.01m of
the route goal. Data quality also requires route error below 5m. The centimetre
tolerance avoids rejecting a car stopped at the route follower's 3m endpoint
because of waypoint rounding. Always-on and always-off policies fail.

Matched controls reset only the learned graph gains/leaks, or remove the
right-foreleg grip. The latter should stop signalling while leaving steering
functional. A single training seed is a pilot, not the larger replication gate
described in the episode plan.

## Reproduce on the packaged GPU runtime

Source `docker/activate.sh` from `/workspace/flyhard`. The runtime must include
the project's `simulator` extra; Shapely 2.1.2 was added for BasicAgent.
Provide the separately hashed graph and source geometry described in their
data manifests. Do not copy `.env` or credentials to the GPU.

```sh
python scripts/check_combined_rig.py
python scripts/collect_roundabout.py --out runs/roundabout-data --traffic 14
python scripts/train_roundabout.py --data runs/roundabout-data --out runs/roundabout-policy --steps 1200
python scripts/evaluate_roundabout.py --checkpoint runs/roundabout-policy/checkpoint.pt.gz --data runs/roundabout-data --split test --out runs/roundabout-test
python scripts/evaluate_roundabout.py --checkpoint runs/roundabout-policy/checkpoint.pt.gz --data runs/roundabout-data --split test --condition core-reset --limit 3 --out runs/roundabout-core-reset
python scripts/evaluate_roundabout.py --checkpoint runs/roundabout-policy/checkpoint.pt.gz --data runs/roundabout-data --split test --condition no-stalk-grip --limit 3 --out runs/roundabout-no-grip
```

Save the dataset, selected checkpoint, configuration, source hashes, evaluation
records and recordings before terminating the Pod. Use the project budget
guard and verify both the Pod inventory and hourly spend afterward.

## Recordings and sponsorship

In indicator-only mode, BasicAgent supplies vehicle motion and the fly controls
the indicator stalk. In combined mode, BasicAgent supplies a requested wheel
angle, the trained fly physically turns the wheel, and only the measured wheel
position supplies CARLA steering. Speed remains scripted. Erratic steering
requests and higher speed are an explicit stress test; retain collisions and
failures in its results.

Every 50ms interval records the neural decision, resulting physical body state,
CARLA RGB/depth frames, measured controls, light-state readback and collisions.
Playback is real time. The CNS panel uses recorded model states on the actual
MaleCNS geometry. The visible request labels refer to steering instructions;
the signal label reports the stalk-driven CARLA state.

Revision 6, layout 3 sponsor assets contain six separate UV-mapped surfaces.
They are not an Unreal skeletal-vehicle replacement. The presentation renderer
uses the supplied Blender geometry and PNGs without repeating artwork
transforms, projects them into the recorded rigid camera frame, and uses the
original car as a holdout. Native CARLA depth occludes them behind intervening
traffic. Review the camera alignment, left door and rear before the full render.
The sponsor step changes only presentation pixels, not vehicle physics,
observations, neural decisions, control values or scoring.

The sponsored renderer uses Blender 5.2.1 LTS on the A40. The following commands
reproduce the two modes; use a fresh output directory for each capture. Only one
capture/collection process may own the CARLA world at a time. Rendering and
offline physical evaluation can run independently.

```sh
python deploy/install_blender.py
python scripts/capture_roundabout.py --checkpoint runs/roundabout-policy/checkpoint.pt.gz --out runs/normal --mode indicators --route entry2-exit3 --speed 25 --traffic 14 --seed 62031
python scripts/capture_roundabout.py --checkpoint runs/roundabout-policy/checkpoint.pt.gz --out runs/unhinged --mode combined --route entry2-exit1 --speed 55 --traffic 14 --seed 63031 --erratic .10 --camera front-right
/workspace/blender/blender-5.2.1-linux-x64/blender --background --python-exit-code 1 --python scripts/render_sponsor_layer.py -- --run runs/normal --out runs/sponsor-rear-left
/workspace/blender/blender-5.2.1-linux-x64/blender --background --python-exit-code 1 --python scripts/render_sponsor_layer.py -- --run runs/unhinged --out runs/sponsor-front-right
python scripts/render_roundabout.py --run runs/normal --sponsors runs/sponsor-rear-left
python scripts/render_roundabout.py --run runs/unhinged --sponsors runs/sponsor-front-right
```

The previously published runtime image does not yet include these new scripts,
Shapely or Blender. Sync the source and install the simulator extra/renderer,
or build a new image from the updated packaging source. The installer pins and
verifies the same official Blender archive used for these recordings.

Vehicle geometry/textures: CARLA 0.9.16, Computer Vision Center (CVC),
Universitat Autònoma de Barcelona. Sponsor names/artwork remain the property
of their owners. MaleCNS data: Janelia/FlyEM, CC BY 4.0. Fly body:
NeuroMechFly/FlyGym, NeLy, EPFL. Retain these credits with published videos.
