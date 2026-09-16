# Three-point-turn learning video — 11 September 2026

A continuation of the original 400-step pilot. The first follow-up training pass produced convincing native CARLA three-point turns. This is a scoped control experiment from structured relative road and goal geometry.

The training-only bicycle approximation was turning more sharply than CARLA: steady recorded samples showed a median native/model curvature ratio of 0.793. The teaching data now accounts for that measured response, includes wider state perturbations, and uses a 0.46-radian maximum wheel request within the existing mechanical rig's travel. Steering range is stored explicitly in each checkpoint; the original checkpoint retains its original 0.35-radian range.

The frozen sensory mapping and motor decoder remain unchanged during training. Only measured-edge gains and neuron leaks learn. Steering, signed speed and gear come from the connectome policy. Fixed inverse kinematics and a velocity regulator move 28 fly joints; only measured passive wheel, pedal and gear-selector positions drive CARLA.

## Verified native results

- Two validation trials passed in 20.3 seconds each.
- Eight newly frozen held-out cases: **6/8 passed** the full stopping gate; **0/8 contact or virtual road-boundary crossings**.
- All eight executed forward/reverse/forward with exactly two actual direction changes and finished within 1.21 degrees of the opposite heading.
- The two failures stopped 0.735 m and 0.721 m from the target. They remain failures under the unchanged 0.6 m position tolerance.
- Resetting the learned core on two predeclared matched cases: **0/2 passed**. Both runs were classified as `no_motion/setup_failure`: the reset core never initiated a turn, so they are not ordinary failed manoeuvres and their terminal errors are excluded from aggregate means.
- Mean final position error: 0.491 m; mean heading error: 0.870 degrees. Passing trials took 21.05–22.3 seconds. Failed trials ran to the predeclared 40-second limit.

Gate: stationary for 0.5 seconds, within 0.6 m and 12 degrees of the target, exactly forward/reverse/forward, with no native contact or virtual-boundary crossing. The road width is 10 m, absent from training widths of 9.5/10.5 m. Test seeds 91000–91007 were frozen before the additional training. The old 71000-series cases used to calibrate the dynamics are now development evidence, not fresh held-out results.

The eight-case result is a small three-point-turn benchmark. It does not establish the earlier proposed 50-trial parking benchmark or general autonomous driving.

## Learning and film provenance

The follow-up ran 600 supervised updates in 153 seconds on a Runpod RTX 4090. The best validation checkpoint was update 500. Its SHA-256 is `7f45e7ddf2bfc2b72f3b0c01e097f61e0b56df43c5cd72027336df0007143c5b`.

The film uses real native CARLA trials of saved training checkpoints. It is a retrospective comparison of those checkpoints, not a claim that learning happened live between camera cuts. No additional steering mistakes or scripted route corrections were inserted. The full successful reveal is the first successful validation take: 20.3 seconds, 0.254 m final position error and 0.755 degrees heading error. The intermediate update-200 checkpoint also passed its trial; it is not labelled as a failure.

Recorded native vehicle poses and MuJoCo joint states are interpolated only for presentation at 60 fps. Neural samples are held until the next actual recorded decision. Sponsor surfaces are depth-composited onto the native Mini, with the latest live artwork checked before every capture/render. The video keeps the green car, control readouts and thedrivingfly.com.

The training-only bicycle diagnostic remains imperfect: this follow-up failed its simplified-model stopping tests even though the native controller succeeds. Native physical measurements, the fixed-case outcomes and causal audits are the evidence for this demo.

Music: Mozart, Eine kleine Nachtmusik K. 525: I. Allegro, the existing Musopen European Archive recording distributed through Wikimedia Commons. Recording attribution and source hashes are in `assets/music/mozart-k525/README.md`. CARLA vehicle credit: CVC / Universitat Autònoma de Barcelona. MaleCNS: Janelia. NeuroMechFly/FlyGym: EPFL. Sponsor artwork remains the property of its owners.

## Export and verification

`Flyhard-three-point-turn-Mozart.mp4` is 39.4 seconds, 1920×1080, H.264 at 60 fps with AAC stereo audio. Its SHA-256 is `3a4cfe93381d733d934521502703d080230e264de52e5fcd360473d92ce4f45e` (15,244,068 bytes). The edit shows 15 seconds of the original and intermediate saved checkpoints, fades to 1.1 seconds of black, then fades into the complete 20.3-second successful attempt at real-time speed, followed by a three-second final hold.

Full audio/video decoding passed; the black interval, green paint, left-door and rear sponsor placements, control readouts, site address and credits were checked in the encoded output. Audio peaks at -4.5 dB. Live livery revision 35, layout 5 includes seven paid placements; immutable manifests and preflight hashes are included. The Desktop copy was verified byte-for-byte. This verifies the local handoff, not iCloud synchronization.

Across native baseline, intermediate, validation, held-out and reset runs, the causal verifier checked 7,346 frames and recomputed 140 neural decisions. Maximum clock disagreement was 7.7e-10 seconds, applied-control error 3.0e-8, and recorded float16 neural-state error 4.8e-7. The local backup verified 152 raw trace/checkpoint files and all 36 rendered-video/cache files against the remote checksums. Twelve focused unit tests passed.

The GPU remains running at the user's explicit request while they review the video. Existing-credit guards remain active; no top-up was made. Native Unreal packaging and unrelated website work remain unchanged.
