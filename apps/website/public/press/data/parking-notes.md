# Parallel parking — 10 September 2026

The current film is the 30-second faster Mozart edit: it builds to 32 simultaneous attempts by 6.4 seconds and cuts between grids and individual attempts. All 50 held-out trials appear as excerpts. Grid footage plays at 6× speed, presented at 60 fps. The side-panel fly is an independently looped replay, labelled in the film; it is not synchronized to each car. No simulation was regenerated for this edit. Sponsor revision 20, layout 5 is preserved.

## Results

| Metric | Learned core | Reset core |
| --- | --- | --- |
| Successful parks | 0/50 | 0/50 |
| Collision-flagged trials | 10/50 | 12/50 |
| Mean final position error | 3.71 m | 18.31 m |
| Mean final heading error | 13.26° | 26.32° |

Neither controller passed the parking benchmark. The gate required at least 40/50 collision-free parks, the entire vehicle within the bay, position error ≤0.3 m, heading error ≤10°, and a stationary hold of 0.5 s. Each trial was limited to 45 seconds. Collision flags include virtual-curb and vehicle-bound overlap as well as native CARLA contacts; they are not a count of separate crashes.

Both conditions used the same 50 held-out geometries (seeds 34000–34049). The model was not tuned using these outcomes. Lower mean final error than the reset comparison does not establish successful parking.

## Control and presentation

The policy consumes structured relative geometry, chooses wheel target, speed magnitude and gear, and uses fixed velocity regulation and inverse kinematics to move 28 fly joints. Passive measured wheel, accelerator, brake and selector positions determine CARLA controls. The model uses 165,122 traced MaleCNS neurons with engineered dynamics. This is not visual perception or a complete biological fly simulation.

The source audit checked 40,959 synchronized recording frames and recomputed 250 sampled model outputs. The editing exception is the explicitly independent side-panel fly in the faster montage. The data file preserves 100 result rows: 50 learned and 50 matched reset trials.

Music: Mozart, Eine kleine Nachtmusik, K. 525: I. Allegro, Musopen European Archive recording, identified as public domain by Wikimedia Commons. See the press kit credits.

## Sources

- [Original benchmark and faster-edit report](https://github.com/MarkUnthank/flyhard/blob/b7ecd17a51f98acdf1775430248ff98bc6d6dd03/reports/2026-09-10-parking/RESULTS.md)
- `parking-trials.csv`: unchanged per-trial table for both conditions.
- `parking-results.json` and `parking-reset-results.json`: unchanged condition metrics.
- `web-exports.json`: source and website-file checksums and stream metadata.

Project: The Driving Fly / Mark Unthank — https://thedrivingfly.com
