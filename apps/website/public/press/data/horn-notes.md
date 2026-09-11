# Dynamic horn recordings — 10 September 2026

## Main film: 37.5 seconds

Five moving traffic situations: a wait behind a car at red followed by green; an empty-road approach; a quiet already-green drive-through; a T-junction pull-out; and a crossroads pull-out. The red-to-green horn starts 0.117 seconds after green. The empty-road transition includes an 83 ms false press, retained as a failed quiet case. The five source takes recorded no ego-vehicle collision contacts.

The two pull-outs are different native road setups. The T-junction take has two presses, longest hold 2.467 seconds; the crossroads has three, longest hold 2.000 seconds. Interior views show the same recorded body motion composited into CARLA's cabin. The edit contains 250 synchronized interior frames.

## Road-rage film: 20 seconds

A separate failed take passes the first car, collides with the next, and continues honking as a third car joins the pile-up. It travels 60.04 m and produces two horn onsets, failing the 90 m / three-onset gate. The longest physical press is 16 seconds. The sensor's 845 contact events mostly represent continued contact, not 845 separate crashes.

Source seconds 0–10 and 14–22 appear at normal simulation speed, followed by two seconds of credits. Four seconds of waiting are omitted; impacts and the continuing hold remain. There are 288 synchronized interior frames.

## What is learned, directed and measured

One frozen learned model operates both forelegs, including wheel and physical button actuation. Traffic, routes, speed and erratic steering requests are directed. Structured inputs are used; this is not camera-based autonomous driving. Sound comes from a real horn recording, cropped and looped to follow measured button intervals, not inserted on a scenario timer. Both films retain sponsor revision 21, layout 5.

The separate ten-case structured held-out diagnostic has one seed for each scenario kind: 3/4 positive horn cases passed and 6/6 quiet cases stayed quiet. The remaining positive case exceeded the permitted timing/hold window. Resetting the learned core or disconnecting the forefeet produced no horn presses in any positive case. This is a small structured diagnostic, not a randomized CARLA benchmark, and does not erase the filmed native false chirp.

## Sources

- [Original report and receipts](https://github.com/MarkUnthank/flyhard/blob/f68907a7ad8f38862000b3604076cc8311231260/reports/2026-09-10-dynamic-horn/README.md)
- `horn-diagnostic.json`: unchanged structured held-out summary, including reset and disconnected comparisons.
- `web-exports.json`: source and website-file checksums and stream metadata.

Horn recording: “05 Horn.wav” by 15HPanska_Ruttner_Jan, CC0 1.0. See the press kit credits.

Project: The Driving Fly / Mark Unthank — https://thedrivingfly.com
