Current final benchmark and video state: see [RESULTS.md](RESULTS.md). The notes below preserve the earlier work history.

# Parking video and trial montage

User priority: deliver one nice 25-second, 60 fps parking edit first. Then compile the 50 held-out trials into a montage building from 1 to 4, 8, 16 and 32 simultaneous attempts. No old roundabout footage. Preserve native work; packaging remains deferred.

Fresh video Pod: RTX 4090, EUR-IS-1, $0.74/h compute. Session: `work/video-priority-20260910/session`. Only existing credit; no top-ups. Local reserve guard is $4. Ordinary workspace must be retained until outputs are verified locally.

New mechanics: passive wheel, throttle pedal, brake pedal and forward/reverse selector. Only 28 fly leg joints have motor targets. Isolated coupled/uncoupled diagnostic: `runs/parking-mechanics-v2`, 8/8 passed. This is a mechanics check, not learned parking.

Policy: measured MaleCNS graph, 165,122 neurons and 25,563,197 edges. Learn edge gains and neuron leaks; fixed population encoding and fixed decoder. Input is relative geometry, current velocity and measured selector position. Output is desired wheel angle and signed speed. Fixed velocity regulation and IK move the fly; CARLA receives only measured physical controls. No visual-perception or general-autonomy claim.

Training: `runs/parking-data-v3` is the corrected demonstration dataset, with 128 training cases, 16 validation cases and 50 separately frozen held-out cases. The held-out cases do not contribute labels. Initial training uses 600 steps on the 4090. `runs/parking-policy-v1` stores the checkpoint and audits. Full evaluation is pending.

First take: `scripts/capture_parking.py` writes native recorder, measured world poses, body states and neural trace to `runs/parking-take-v1`. The edit uses recorded transforms and joint interpolation only for display, with CARLA physics disabled during replay. Neural states are held between original samples. It must label a failed attempt as failed.

Sponsor artwork is refreshed from production before capture/preview/render and verified at each command start. The scene preview checked revision 19, layout 5, seven placements. Left door and rear image paths: `work/video-priority-20260910/scene-preview/`. Final output must use its own fresh immutable snapshot and receipts.

Native build is preserved on a private network volume; native Pod was deleted. Shipping compilation completed, but cooking and in-CARLA proof remain outstanding. See `work/native-carla/status.json` and `native-pause.json`.

Benchmark gate remains scoped: at least 40 collision-free parks out of 50 held-out cases, entire vehicle inside marked bay, <=0.3m and <=10 degrees target error. Report collision rate, pose errors, time, direction changes, and a learned-core-reset comparison. No performance claim before actual evaluation.

Training diagnostics: continuous signed-speed policies v1 and v2 stopped outside the bay. Their source is preserved under `continuous-policy-diagnostic/`. V3 uses learned categorical reverse/neutral/forward logits plus learned wheel angle and speed magnitude. This avoids averaging contradictory directions into a stationary action. It is trained from scratch on the standstill-augmented v4 dataset, with frozen interfaces. No held-out trials have been run yet.

Selected video take: `runs/parking-take-v5`, validation seed 24000, checkpoint `parking-policy-v3`. Categorical gear policy; decisions at 4 Hz, measured controls/velocity regulation at 20 Hz. Selector feedback is explicitly masked from neural observations while remaining active in the physical interlock. Actual recording: 35 seconds, 24 direction changes, no collision, final 2.2031 m / 21.4835 degrees error, outside the bay. It is a failed practice attempt and the edit says so. The prior unmasked tests stalled at a gear change. No steering errors or vehicle motion were added. Full held-out evaluation still pending.

Export notes: this RTX 4090 Pod rejects NVENC sessions, so video encoding uses remote CPU libx264 (60-frame encoder smoke test passed). CARLA, CNS and fly rendering remain on the GPU. Replay now reloads Town03 before spawning to clear native collision state between renders. Failed exports v5/v6 are retained separately; v7 is the current render destination.

First video delivered and then revised at user request: `~/Desktop/Flyhard-parking-2026-09-10/Flyhard-parallel-parking-green-25s.mp4`. Original brand green explicitly set, neutral title `flyhard | parallel parking`, outcome caption removed. Same recorded failed attempt; metrics remain in receipts. 25s, 1080p, 60fps, 1500 decoded frames; SHA256 250bceb81586241e3f869e029161bca1cf67d5a277d41dffaeef28e706d9d900. Live livery r19/layout5, seven sponsors, verified left door/rear. Source/checkpoint/data backup verified locally at `work/video-priority-20260910/backups/parking-first-attempt-source.tar.gz`.

50-case learned recording is starting on CARLA port2000. Reset-core comparison runs independently on port2100 on the same Pod to reduce elapsed time, with identical benchmark settings and no cameras. No controller tuning against these held-out cases. The reset evaluation supports resumable completed trials; first seed34000 was completed before the renderer iteration and is retained. Deadline extended to19:00UTC within the unchanged existing-credit reserve/spend caps; replacement on-Pod guard PID21342, old supervised timer495 paused.

Montage throughput: lossless FFV1 stores packed depth instead of one PNG per frame; a 20-frame native-depth round trip returned byte-exact data. Primary learning camera trial time improved from145s to118s. To reduce elapsed time further using existing spare GPU/CPU capacity, fixed partitions were declared before later outcomes: primary seeds34000–34024 on port2000 and parallel seeds34025–34049 on port2200; reset50 remains on port2100. No new Pod or policy change. A boundary monitor interrupts the primary evaluator after its25 designated complete trials; any partial next trial remains excluded by this predetermined partition, not by outcome. Separate local collectors back up and SHA-verify complete raw recordings while capture continues.

Latest main video delivered: `~/Desktop/Flyhard-parking-2026-09-10/Flyhard-parallel-parking-r20-25s.mp4`. Gas Monkey Garage replaces ad-59 on both roof billboard faces. Livery r20/layout5/seven placements; brand green and requested neutral title preserved, outcome-caption panel removed at user request. Same failed validation motion. Verified 1500 decoded frames, 25.000s, 1080p60, SHA2568364c7b40bc1d4555e3c8a668cef0ef01cd46c1a51a9cb55ca1e590c068beb84. `runs/parking-main-r20` now retains clean camera RGB, lossless packed depth and all camera/vehicle matrices for future sponsor-only recomposition without CARLA.

Final fixed benchmark partitions supersede the prior25/25 plan: primary indices0–20 (21 cases), parallel25–42 (18), third21–24 and43–49 (11). Third uses already-warm port2300 after main render. Authoritative plan `work/parking-final-partitions.json` on Pod. Boundary monitor38782 stops primary/parallel only at completed designated trials; third38781 runs its explicit11 indices. No outcome-based selection. Reset comparator remains all50.

Montage music requested: Mozart, Eine kleine Nachtmusik K.525, I.Allegro. Public-domain Musopen / European Archive recording downloaded from Wikimedia Commons; provenance and hash in `assets/music/mozart-k525/`. Planned video cuts on recording attacks, 1/4/8/16/32 grids, 45.75s including6s metrics card. All50 unique attempts represented,11 repeats disclosed. Main25s video remains unchanged.

Incremental fresh-sponsor recomposition PID40702 follows the fixed partitions while capture continues; output `runs/parking-cameras-r20`, log `work/parking-cameras-r20.log`, immutable live snapshot20260910T163052541750Z. It reuses cameras only when artwork and mesh hashes match; r19 cameras are redrawn from clean RGB/depth. Final render must recheck/refresh live revision again.

Final: Mozart montage exported and verified (45.75s,1080p60,2745 frames), r20 retained under explicit user instruction despite live revision21. All50 recorded trials and250 sampled model outputs passed the causal audit;0/50 parks,10/50 collision flags. Reset0/50,12/50. All50 raw archives,main camera cache and source provenance verified locally. Both Pods EXITED; no running Pods. Native integration/packaging remains deferred. See RESULTS.md and benchmark receipts.
