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
