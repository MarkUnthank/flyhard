# Three-point turn — 45-second Boccherini edit

This edit adds anticipation to the original learning film using its saved, verified checkpoint footage. No additional training or CARLA simulation was run.

The opening 22 seconds contain six edit beats, with longer corrections and modest road-view crops. Those beats are not six separate attempts: they use the original checkpoint, the intermediate checkpoint, and a short teaser of the selected successful take before it stops. The intermediate checkpoint also passed its complete trial; its success is not relabelled as a failure. Playback rates are recalculated and displayed. The chronological source intervals, source hashes and full outcomes are in the edit receipt.

A 0.9-second black interval is silent. Boccherini's Minuet and Trio returns as the complete 20.3-second successful take fades in at real-time speed, followed by a 1.8-second final hold. The successful take and all learning-core benchmark results are unchanged; see ../2026-09-11-three-point-learning/ for the 6/8 native gate and 0/2 reset comparison.

The green Mini, CNS/body panels, request/steering/pedal/gear readouts and thedrivingfly.com remain visible. Fresh production artwork was rebuilt and verified before every finished render; revision 35, layout 5 still matches all three source renders, so sponsor re-rendering was unnecessary. Left-door and rear placements were visually checked in the final encoded video.

Music is the Rafael Krux recording of Boccherini's Minuet and Trio from the String Quintet in E major, Op. 11 No. 5, G. 275, distributed as CC0 on Wikimedia Commons. Recording/source/license details and checksums are in assets/music/boccherini-g275/. The edit uses an excerpt, a silent pause, a returning excerpt and fades.

Export: **45.000 seconds, 1920×1080, 60 fps, 2,700 frames**, H.264/yuv420p with AAC stereo at 48 kHz. File: `Flyhard-three-point-turn-Boccherini-45s.mp4`. SHA-256: `df8a49f9350643e1f2960ec90ced345c341f9b6476d40845728eac028c5d7515`. Size: 16,389,779 bytes.

Full audio/video decoding passed. The middle of the blackout is pixel-black with zero decoded audio amplitude. Audio-source correlations exceed 0.9997 for both the opening and returning Boccherini excerpts. Four sampled full-success frames match the original take within ordinary lossy-encoding error (mean RGB error below 1.3/255). Crops, HUD, sponsor views, finish and credits were visually checked. The Desktop copy matches the source checksum; iCloud synchronization itself was not checked. The previous Mozart MP4 remains unchanged.

The edit plan is configs/three-point-boccherini-45s.json; scripts/edit_three_point.py applies it after the live sponsor preflight. Run on the retained Runpod machine with the existing recording directories, `--plan configs/three-point-boccherini-45s.json --out runs/NEW_OUTPUT --asset CURRENT_LIVE_ASSET`. An initial NVENC attempt was unavailable on this host; the verified export uses libx264 on the same remote machine.

The pod remains running for the user's review, with the existing-credit guard active and no top-ups. Native Unreal packaging and unrelated work are untouched.
