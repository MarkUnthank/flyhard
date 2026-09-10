# Dynamic horn evidence

One frozen controller operates both forelegs. The saved model hash is
`b529a3623a42bf1b34fe9ccc42e6d1839bcbe5d1878ec53d49fd50888e4e8f88`.
It is the step-500 selection from a hard-negative continuation of the 1500-step
v2 run; the continuation subsequently finished at step 600, but the recording
checkpoint was not changed.

The structured held-out diagnostic contains one disjoint seed for each of ten
scenario kinds. It is a small diagnostic, not a statistical driving benchmark.
The learned core passed three of four positive horn cases and all six quiet
cases. The remaining positive case pressed but exceeded the allowed timing/hold
window. Resetting the learned core or disconnecting the forefeet produced no
horn presses in any of the four positive cases. Mean wheel error was 0.0543 rad
for learned, 0.2254 rad for reset, and 0.0982 rad for disconnected.

Native CARLA tests are separate from this structured diagnostic. In particular,
the recorded empty-road transition includes an 83 ms false horn press. It remains
a failed quiet case and is retained in the authentic edit; the held-out result
must not be presented as a guarantee of quiet native driving.

The source code and reproduction details are in
[the dynamic horn notes](../../docs/dynamic-horn-2026-09-10.md). Raw recordings,
checkpoints, exact body/neural traces and development failures are retained in the
session archive. The public receipts contain no private checkout or billing data.

## Exported main clip

The main edit is 37.5 seconds, 1920×1080 at native 60 fps. It opens with the
red-to-green honk (0.117 seconds after green), shows the imperfect empty-road
case and the quiet already-green drive-through, then the two different pull-outs.
The T-junction has two presses with a 2.467-second longest hold. The crossroads
has three presses with a 2.000-second longest hold. Both use their own native
approach light after the binding correction. The ego collision sensor reported no contacts in these five
source takes. The edit contains 250 synchronized interior frames.

The full MP4 decode, frame count, single checkpoint, camera/body clock and horn
PCM gating passed. The Desktop copy has SHA-256
`8ef75db167044b8071f3c304158c5651cbfab2bda0d29d02d9f56fdb72ce176b`.
The sponsor snapshot used for the finished render is revision 21, layout 5.
The left door, rear, right side and cabin views were visually checked.

## Exported road-rage clip

The separate edit is 20 seconds, 1920×1080 at native 60 fps, including 288
synchronized interior frames. It uses source seconds 0–10 and 14–22, followed by
two seconds of credits. Four seconds of waiting are trimmed; the actual impacts
and continuing horn hold are retained. The car passes the first white car, hits
the blue car, and keeps honking as the third orange car joins the pile-up.

The source encountered three cars and honked near all three, but failed the
strict road-rage gate: it travelled 60.04 m and produced two separate horn onsets,
below the required 90 m and three onsets. Its longest physical press was 16
seconds. The collision sensor recorded 845 contact events, mostly continued
contact, not 845 separate crashes. This is an authentic failed take, not a
collision-free or autonomous-driving result. Erratic steering requests are
choreographed; the model's actual wheel and button actuation is recorded.

The real recorded horn stays continuous across touching edit segments. The final
audio-only remux refreshed production sponsors again and required every texture
and panel checksum to match the existing picture. Both used revision 21,
layout 5. The compressed video stream is byte-identical before and after the
remux. Full decode, 1,200 frames, the shared clock, measured audio gating and
Desktop SHA-256 verification passed. The delivered MP4 hash is
`f9b56edb8dd71d09fafb07b3a53a188967bdc73841248dc8f132b14980d74fcf`.
Exported cabin and exterior frames were visually checked.

## Preservation

All six final sources, including native exterior/cabin video, lossless depth,
body/neural traces and CARLA recorder data, were downloaded. Sixty raw files and
the frozen checkpoint were checksum-verified against the GPU copy; the receipt
is [raw-backup-verification.json](raw-backup-verification.json). Exact earlier
source variants are retained in `source-history` so recorded configuration
hashes remain auditable. Older videos and unrelated workspace changes are
preserved. The compute shutdown receipt is stored alongside the export results.
