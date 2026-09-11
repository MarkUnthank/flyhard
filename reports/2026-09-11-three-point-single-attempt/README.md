# One full successful attempt, edited locally

The final requested scope is one complete successful-ish attempt, at normal speed, rather than a montage. The user specifically asked to download the constituent footage and edit locally, and to use the existing good take instead of generating a contrived many-correction run.

The verified source was downloaded from the retained Runpod machine to work/three-point-local-edit/parts/success/three-point.mp4. Its SHA-256 is `939184ea1b6a94ac97d540dfd9911abb88d8c523285087b0e0354c13853dfb93`. The local FFmpeg edit uses its entire 20.3-second video stream once, without time cuts, cropping, speed changes or a preview of the finish. All 406 recorded states and all 1,218 rendered attempt frames are retained. Boccherini's Minuet and Trio accompanies the attempt; a 2.5-second still follows the completed turn with credits. Total: **22.8 seconds**, 1920×1080, 60 fps, H.264/AAC.

The source is the same verified validation take as before: collision-free forward/reverse/forward, two direction changes, 0.254 m final-position error and 0.755 degrees heading error. No new driving run, added steering mistakes or 100-point-turn claim is involved.

The previous montage's middle source was only an excerpt. Its missing endpoint was identified and the full middle run recovered from saved poses before the user clarified the single-take scope. That recovered clip is not included in this deliverable. Earlier montage exports are historical iterations, not the current video.

Current script: scripts/edit_three_point.py. Current recipe: configs/three-point-boccherini-natural-speed.json. Local command uses `PYTHONPATH=src python3 scripts/edit_three_point.py --plan configs/three-point-boccherini-natural-speed.json --out NEW_OUTPUT --asset CURRENT_LIVE_ASSET`. The editor rejects failed, truncated or retimed sources. The receipt records Darwin/arm64 and /opt/homebrew/bin/ffmpeg, confirming the finishing step ran locally.

Fresh production sponsors were rebuilt and verified immediately before the local export; revision 35/layout 5 matched the source. Green paint, sponsor surfaces, CNS/body, request/steering/pedal/gear data and thedrivingfly.com are unchanged during the full attempt. Full decoding passed. Every one of the 1,218 source attempt frames was compared in order against the output road view; maximum downscaled grayscale error was 0.784/255 (ordinary re-encoding loss). The final pose and credits were visually checked.

Output: `Flyhard-good-attempt-Boccherini.mp4`, SHA-256 `6c831de1e73741ab089b1e057407c3b73cdba0e4a9c2de0c781ad46cb337a6d5`. The finished MP4 and the unchanged `Flyhard-good-attempt-SOURCE.mp4` were copied to Desktop and checksum-verified. iCloud synchronization itself was not checked. The Runpod instance remains running for review with the existing-credit guard; no top-ups, merge or deployment occurred.
