# Three-point turn — 11 September 2026

The current film is one complete successful validation take: 20.3 seconds at normal simulation speed, followed by a 2.5-second still and credits. Total: 22.8 seconds, 1920 × 1080, 60 fps. All 1,218 rendered attempt frames are retained, in order. There are no cuts within the attempt, added corrections or speed changes.

The featured validation take finished with 0.254 m position error and 0.755° heading error, without collision. It is separate from the eight held-out cases in `three-point-turn-results.json`.

## Held-out evaluation

- Six of eight passed the full stopping gate.
- All eight made forward → reverse → forward with exactly two actual direction changes, no native contact and no virtual road-boundary crossing.
- Two trials failed: final position errors were 0.735 m and 0.721 m, outside the unchanged 0.6 m tolerance. Both ran to the 40-second time limit.
- Resetting the learned core on two matched cases produced no turn and 0/2 passes.

The full gate requires a stationary 0.5-second hold, position error ≤0.6 m, heading error ≤12°, exactly forward/reverse/forward, and no contact or boundary crossing. Eight seeds (91000–91007) were frozen before follow-up training. This small benchmark does not establish general driving reliability or successful parallel parking.

## Control and presentation

The connectome-based policy consumes structured relative road and goal geometry and chooses steering, signed speed and gear. Only measured-edge gains and neuron leaks learn. Fixed sensory mapping, motor decoding, inverse kinematics and a velocity regulator provide engineered assistance. Twenty-eight fly joints move; measured passive wheel, pedals and gear-selector positions operate CARLA. The model does not use camera-based road perception.

Body states and vehicle poses come from the same recording. Pose interpolation presents the recording at 60 fps; neural samples are held until the next recorded decision. Sponsor surfaces are depth-composited on the Mini. The film retains sponsor revision 35, layout 5. The colours are computed model states, not observed biological spikes.

Music: Boccherini, Minuet and Trio from String Quintet in E major, Op. 11 No. 5, G. 275; recording by Rafael Krux, CC0. See the press kit credits.

## Sources

- [Original evaluation report](https://github.com/MarkUnthank/flyhard/blob/132ba204153ff870989f84b52e364ee5968d6861/reports/2026-09-11-three-point-learning/README.md)
- [Final single-attempt edit report](https://github.com/MarkUnthank/flyhard/blob/132ba204153ff870989f84b52e364ee5968d6861/reports/2026-09-11-three-point-single-attempt/README.md)
- `three-point-turn-results.json`: unchanged eight-case result file.
- `three-point-turn-audit.json`: unchanged held-out control audit.
- `web-exports.json`: source and website-file checksums and stream metadata.

Project: The Driving Fly / Mark Unthank — https://thedrivingfly.com
