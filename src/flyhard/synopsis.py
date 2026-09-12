"""What actually happens in a take, read off its own control trace.

A take's label says how the trial was scored. It does not say what you see: when the
fly gets on the throttle, when it runs out of room, when it swings out, and the second
something goes wrong. Those are all in the trace the trial already wrote down, as
speed, pedal travel, lane offset and the gaps to the other traffic, so the description
is measured rather than written by hand and cannot drift away from the footage.

Timings are seconds from the first frame of the clip, so they are read straight off a
scrubber. Every threshold here is a presentation choice about what is worth mentioning
and none of them change a recorded metric.
"""
BRAKE_ON = .25          # Pedal travel that reads on screen as braking, not trimming.
OUT_OF_LANE = 1.2       # Metres of lane offset that reads as leaving the lane.
CLOSING_GAP = 15.       # Metres to the car in front that reads as catching it up.
IMPACT_DROP = 2.5       # Metres per second lost in one control step: nothing else does that.
CONTROL_DT = .05


def _first(rows, predicate):
    for row in rows:
        if predicate(row):
            return row
    return None


def _impact(rows):
    """The step that loses the most speed. A crash sheds far more than a brake can."""
    worst, at = 0., None
    for before, after in zip(rows, rows[1:]):
        drop = before['speed_m_s']-after['speed_m_s']
        if drop > worst:
            worst, at = drop, after
    return (at, worst) if worst >= IMPACT_DROP else (None, worst)


def beats(rows, metrics=None):
    """Timed beats for one take, in the order they happen."""
    if not rows:
        return []
    metrics = metrics or {}
    found = []
    start = rows[0]['time']

    def at(row):
        return round(row['time']-start+CONTROL_DT, 1)

    top = max(rows, key=lambda row: row['speed_m_s'])
    found.append((at(rows[0]), f"rolling at {rows[0]['speed_m_s']*2.237:.0f} mph"))
    if top['speed_m_s'] > rows[0]['speed_m_s']+1:
        found.append((at(top), f"up to {top['speed_m_s']*2.237:.0f} mph"))

    closing = _first(rows, lambda row: 0 < row.get('lead_gap', 1e9) < CLOSING_GAP)
    if closing:
        found.append((at(closing), f"catches the vehicle in front, {closing['lead_gap']:.0f} m back"))

    braking = _first(rows, lambda row: row['measured_brake'] > BRAKE_ON)
    if braking:
        found.append((at(braking), f"brakes hard at {braking['speed_m_s']*2.237:.0f} mph"))

    # The furthest the car gets from its lane, not the first wobble past the threshold:
    # a take that drifts a metre early and leaves the road later should be described by
    # the second one.
    out = max(rows, key=lambda row: abs(row.get('lane_offset', 0.)))
    if abs(out.get('lane_offset', 0.)) > OUT_OF_LANE:
        side = 'right' if out['lane_offset'] > 0 else 'left'
        found.append((at(out), f"{abs(out['lane_offset']):.1f} m out of its lane "
                               f"to the {side}"))
        back = _first([row for row in rows if row['time'] > out['time']],
                      lambda row: abs(row.get('lane_offset', 0.)) < OUT_OF_LANE/2)
        found.append((at(back), 'back in the lane') if back is not None
                     else (at(rows[-1]), 'never comes back into the lane'))

    hit, drop = _impact(rows)
    if hit is not None:
        found.append((at(hit), f"hits something: {drop*2.237:.0f} mph gone in one step"))

    last = rows[-1]
    if last['speed_m_s'] < 1:
        found.append((at(last), 'stopped'))
    else:
        found.append((at(last), f"still doing {last['speed_m_s']*2.237:.0f} mph at the end"))
    return sorted(found)


def synopsis(rows, metrics=None):
    """One line per beat, which is the description that goes beside the films."""
    return [f'{when:0.1f}s — {what}' for when, what in beats(rows, metrics)]
