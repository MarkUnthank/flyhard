# Three-point turn — natural-speed edit

The user asked to remove the jump ahead to the successful finish and to leave the real pauses/corrections at their natural speed instead of forcing a 45-second runtime.

The existing early-checkpoint clip now plays for 16.6 seconds at 1× simulation speed; the existing intermediate excerpt plays for 10.05 seconds at 1×. Their source footage is unchanged, including recorded pauses, steering and gear changes. The intermediate source is still the previously captured excerpt (simulation time 2.5–12.55 seconds), not a claim to show that entire trial. There are no added internal cuts or road-view crops in either clip.

After 0.9 seconds of silent black, the complete successful take plays once, from its beginning through its stop, at normal speed for 20.3 seconds. It is not previewed before the blackout. A 1.8-second final hold gives a natural total of **49.65 seconds**, without a 45-second limit. Boccherini's Minuet and Trio remains the soundtrack. No new training, simulation or steering mistakes were introduced.

The current recipe is configs/three-point-boccherini-natural-speed.json. scripts/edit_three_point.py rejects reuse of the successful-take source in the preceding montage. The previous 45-second recipe was superseded; its exact source remains in commit 12d7554, with historical export receipts in ../2026-09-11-three-point-boccherini/.

Production artwork was refreshed before this export and still matched revision 35/layout 5. The green Mini, sponsor views, CNS/body, request/steering/pedal/gear data and thedrivingfly.com remain visible. All underlying controller results are unchanged.

Export: `Flyhard-three-point-turn-Boccherini-natural-speed.mp4` — 1920×1080 H.264, 60 fps, 2,979 frames, AAC stereo 48 kHz. SHA-256: `adf200d0455f1323bdf9aa679ae8e15413e393aa5897ebd2ded2b2aa203714b0`. Size: 17,302,499 bytes. Full decoding passed; the black interval is pixel-black and silent, music samples match the Boccherini source, and four sampled final-take frames match the original within encoding loss. Both learning segments verify exactly 1× simulation speed. The Desktop copy is checksum-verified; earlier exports remain intact. iCloud sync itself was not checked.

The Runpod instance remains running for user review with the existing credit guard. Code and edit receipts belong to draft PR #23; no merge, website deployment or native integration work occurred.
