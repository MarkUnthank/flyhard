# Flyhard parallel parking — 10 September 2026

The requested deliverables are a 25-second main edit, followed by all 50 held-out attempts in 1 → 4 → 8 → 16 → 32 grids, set to Mozart’s *Eine kleine Nachtmusik*, K. 525, I. Allegro. The existing main exports are retained. The user explicitly requested keeping existing footage when another sponsor arrived; the montage therefore keeps **livery revision 20, layout 5, seven placements**, even though production advanced to revision 21 during final checks.

## Actual benchmark result

**The proposed parking gate was not passed. Neither controller completed a successful park.**

| Metric | Learned core | Reset learned core |
|---|---:|---:|
| Successful parks | 0/50 | 0/50 |
| Collision trials | 10/50 (20%) | 12/50 (24%) |
| Mean final position error | 3.71 m | 18.31 m |
| Mean final heading error | 13.26° | 26.32° |
| Mean duration | 40.96 s | 43.40 s |
| Mean direction changes | 34.52 | 0.00 |

Gate: at least 40/50 collision-free parks, entire vehicle inside the marked bay, position error ≤0.3 m, heading error ≤10°, and a stationary final hold of 0.5 s. Each trial was limited to 45 s. Collision flags include vehicle-bound overlap and the benchmark’s virtual curb, as well as native CARLA collision events; they are not exclusively native collision impulses.

Both conditions used the same 50 held-out geometries, seeds 34000–34049, including withheld space widths, approach offsets and obstacle positions. The fixed controller and interfaces were not tuned using these outcomes. Resetting zeroed the learned edge-gain and neuron-leak parameters while retaining the same frozen encoding, decoder and body/control interface. Lower observed final error does not establish successful parking or general autonomous driving.

The three recording partitions were declared before their remaining outcomes: indices 0–20,25–42, and21–24 plus43–49. Every assigned case is retained. See `benchmark/parking-final-partitions.json`, `benchmark/all-trials.csv`, and the original JSON metrics for per-trial results.

## Causal controls and verification

The controller consumes structured relative geometry, not visual perception or a sequence of steering requests. It chooses wheel target, speed magnitude and reverse/neutral/forward. Engineered neuron dynamics use the MaleCNS graph (165,122 neurons,25,563,197 connections). Fixed velocity regulation and inverse kinematics move the fly’s 28 actuated leg joints; passive measured wheel, accelerator, brake and selector positions determine CARLA controls. Selector sensory input is masked for this frozen evaluation, while remaining part of the physical interlock. This is an engineered connectome-based prototype, not a complete biological fly simulation.

Policy decisions: 4 Hz. Measured CARLA controls: 20 Hz. Fly motor targets: 200 Hz; MuJoCo timestep 0.00005 s. The saved body pose is the end of each tick; the next CARLA tick uses those measured physical controls.

Verified: **40,959 synchronized frames** across all 50 recordings, matching body clocks and consecutive CARLA camera frames; measured-control values match applied steering, pedals and gear; direction changes, collision flags and final metrics match recorded rows. **250 fixed sampled model outputs** were recomputed from the checkpoint. All50 composed camera files decoded to their expected frame counts. See the two audit JSON files under `benchmark/`.

Checkpoint SHA256: `4f4d46b875836af2b03930fe1cf47cbabb66a552eb12912d8fa4d74725d1ce65`. Cases SHA256: `3e451a858420f80a337512b5ca0e5d15c8adb06372ad86ab6d8033fbdc7966c5`. Policy `parking-policy-v3`, training data `parking-data-v4`; supervised training used separate training cases and no held-out labels.

## Video treatment

The main 25 s video uses validation seed 24000, not one of these 50 held-out trials. It is an actual unsuccessful practice attempt: no collision, final 2.2031 m / 21.4835° error, 24 direction changes. No steering mistakes or vehicle motion were injected. The requested title is `flyhard | parallel parking`; the car is green; the outcome-caption box was removed at the user’s request. Request/steering readouts, CNS, fly and `thedrivingfly.com` remain visible.

The montage includes all 50 unique attempts. Eleven reappear across the expanding grids, because 1+4+8+16+32=61 visible slots; this is disclosed on screen. Trials play at 6× from actual 20 fps recordings, presented at 60 fps. Short attempts hold their last frame. Grid cuts are frame-aligned to attacks in the Mozart opening; the edit is 45.75 s including a 6 s results card. No synthetic neural or driving activity is added. Trial labels and measured request/steering readouts remain in the footage, with the website in the black header.

Music: Mozart, *Eine kleine Nachtmusik*, K. 525, I. Allegro. Public-domain recording identified by Wikimedia Commons, sourced from Musopen’s European Archive collection; actual ensemble unspecified by that source. Opening excerpt with loudness normalization and a one-second ending fade. Source/license/SHA are in `assets/music/mozart-k525/README.md` and `sha256.txt`. [Recording source](https://commons.wikimedia.org/wiki/File:Mozart_K525_Serenade_in_G_Major_1_-_Allegro.ogg).

Sponsor surfaces are composited from their real UV-mapped meshes using native CARLA depth. This is not a completed native Unreal vehicle import. Left-door and rear placements were checked for the main export; preserved r20 artwork is also in the montage. Vehicle credit: CARLA 0.9.16, CVC / Universitat Autònoma de Barcelona. MaleCNS: Janelia. NeuroMechFly / FlyGym: EPFL. Sponsor artwork retains its owners’ rights.

## Preservation and remaining work

All50 raw trial archives and the reset comparison are backed up locally and checksum-verified. The main r20 clean camera/depth/matrix cache is also verified locally (`parking-main-r20-cache.tar`, SHA256 0f8720bc8a5fa5f303723b22efcf322dcbd46c8d4785dc252ce4851ccf374f6a). Original main videos remain on the Desktop. Native build progress is retained on a private persistent volume; native import/cooking and packaging remain deferred. No unrelated repository work was reset, committed or pushed.

The next controller iteration needs a fresh held-out evaluation after training changes; these 50 outcomes are now known. This report does not claim the scoped parking benchmark, visual autonomy, or native sponsor integration is complete.

Final MP4 verified:45.75s,1920×1080,H.264/yuv420p,60fps,2745 decoded frames and AAC audio matching the selected Mozart source. SHA256`ed5a0fa119d2da7f24028965aa53388906bbe5a959498e8a9abd9aca29971413`. Output: `~/Desktop/Flyhard-parking-2026-09-10/Flyhard-50-parking-attempts-Mozart-r20.mp4`.

Pod cleanup verified through Runpod API: both project Pods are EXITED; no running Pods. Workspace/storage retained. No credit was added.

## Faster editorial version

User requested quicker build-up, fly on the side, and cutbacks between the full grid and single attempts, with no regeneration. `~/Desktop/Flyhard-parking-Mozart-fast-edit.mp4` is the new30s,1080p60 edit. It reaches32 attempts at6.4s and uses sharp existing r20 recordings of trials25,49 and50 for close-ups. All50 trials remain represented as edited excerpts. The fly is an independent replay cropped from the existing original video and labelled accordingly; it is not synchronized to every trial. Mozart retained, all older MP4s preserved. No Pod, simulation or3D generation used. Verified1800 frames,30.000s,H.264 Constrained Baseline,AAC; music correlation0.9923. Source hashes and timeline are in `fast-edit-receipt.json`.
