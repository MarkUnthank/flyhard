# Horn experiment evidence

See the [experiment report](../../docs/horn-etiquette-2026-09-10.md) for the causal
contract, training inputs, failures, video, reproduction commands and limitations.

The final benchmark contains **180 held-out structured-state cases × three
conditions**, ten seconds per case, with physical controls measured at 60 Hz.
These are MuJoCo body/control trials, not 540 CARLA driving scenes. There are three
separate final CARLA demonstrations, one for each requested behaviour.

| Condition | Timely single-beep positives | Quiet negatives |
| --- | ---: | ---: |
| Learned core | 28/30 | 150/150 |
| Core reset to initialization | 0/30 | 150/150 |
| Learned commands, control grips disconnected | 0/30 | 150/150 |

The learned condition passes the declared 90% positive / at-most-5%-false-beep gate.
Two positive trials had a second threshold crossing; both remain failures. The
initial 20 Hz evaluation missed these crossings, so its 30/30 result is superseded.
This is one training seed and a scoped benchmark, not a guarantee in other traffic.

- `training-config.json`, `training-history.json`, `training-metrics.json`: frozen
  interfaces, graph and code hashes, cases, optimization progress and gradient audit.
  The trainer's original `trained_pending_physical_evaluation` status is preserved;
  later evaluation results are in the separate benchmark receipt.
- `mechanics.json`: attached and disconnected button checks, timestep and IK error.
- `test-plan.json`: all held-out cases, thresholds, measurement rates and checkpoint.
- `benchmark-60hz.json`: final aggregate results for all three conditions.
- `trials.csv`: all 540 trial summaries, including failures and button onset times.
- `capture-results.json`: three actual CARLA episodes, light-sequence checks and
  body/camera clock error. No-car and arrival-green are quiet; waiting-green beeps
  once, 0.15 seconds after the light changes.
- `video-export.json`: native 60 fps source mapping, sponsor visibility measurements,
  NVIDIA renderer, audio interval, exported-video hash and decoded-file checks.
- `livery-preflight.json`: revision 21, layout 5 and exact hashes verified against
  production before the finished render. It is a dated receipt, not a claim that
  these assets remain the newest after another purchase.
- `provenance.json`: graph/checkpoint and archive hashes. The full raw archives,
  including the first invalid scene-harness captures, are retained locally and on
  the stopped Pod's ordinary workspace. Large files and private provider state are
  excluded from Git.
- `sha256.json`: hashes of the public evidence files in this directory.

The final MP4 has 1,500 decoded frames at 1920×1080, 60 fps and exactly 25 seconds.
The original synthesized beep is gated by the passive button measurement. Its
source PCM is exactly silent outside 16.75–17.40 seconds; the decoded AAC interval
was also checked. The green Mini, left-door/rear sponsor placement, actual lamp
camera, fly button press, request/steering readouts, website and credits were
visually inspected. No outcome was changed for comedy.

The local source checks passed: 79 pytest tests, 112 Python files parsed, and
`git diff --check`. Credentials, private sponsorship data, native build archives,
checkpoints and raw recordings are not part of this public evidence directory.
