"""Geometry and scoring for giving way at an unsignalled junction.

Coordinates are metres along the ego's approach. The give-way line is x = 0 and the
ego travels towards positive x; the conflict box runs from the line to JUNCTION_DEPTH.
The other vehicle runs along the crossing arm and its position is a signed distance
to the middle of that box, negative while it is still approaching.

Three case kinds share one policy, and the discrimination between them is the point:

  right      an ordinary vehicle arrives from the right and holds priority, so stop
  left       an ordinary vehicle arrives from the left, the ego has priority, so go
  priority   a vehicle under blue lights arrives from either side, so stop regardless

The longitudinal physics, pedal free play and stop planning are the ones measured for
the crossing, so a stop here is the same motor skill applied to a different cause.
"""
from dataclasses import asdict, dataclass
import math

import numpy as np

from flyhard.crossing import ENCROACH_MARGIN, ENCROACH_SPEED, FRONT_OVERHANG
from flyhard.parking import REAR_TO_CENTER

JUNCTION_DEPTH = 7.5      # Depth of the conflict box beyond the give-way line.
OTHER_HALF_LENGTH = 2.4   # Half the crossing vehicle's length along its own path.
CONFLICT_HALF_SPAN = 2.2  # Half-width of the ego's swept path through the box.
SENSING_RANGE = 55.       # Beyond this the other vehicle is not reported at all.
CLEAR_MARGIN = 4.5        # It has gone once this far past the conflict centre.
MAX_OTHER_START = 56.     # Longest side-arm run a Town05 junction validates on both sides.
KINDS = ('right', 'left', 'priority')

OBSERVATION_FIELDS = ['front_to_line', 'ego_speed', 'other_visible', 'other_to_conflict',
                      'other_speed', 'other_time_to_conflict', 'other_range', 'other_from_right',
                      'other_is_emergency', 'measured_throttle', 'measured_brake']


@dataclass(frozen=True)
class JunctionCase:
    seed: int
    split: str
    kind: str
    approach_speed: float
    start_x: float
    other_speed: float
    other_start: float        # Signed distance to the conflict centre when the run begins.
    other_side: float         # +1 the other vehicle comes from the ego's right, -1 the left.
    arrival_offset: float     # Derived: its arrival at the box less the ego's unimpeded arrival.

    def record(self):
        return asdict(self)

    @property
    def start(self):
        return np.array([self.start_x, self.approach_speed])

    @property
    def emergency(self):
        return self.kind == 'priority'

    @property
    def must_yield(self):
        """Whether this case demands giving way at all. `left` is the negative case."""
        return self.kind in {'right', 'priority'}

    @property
    def other_waits(self):
        """The ordinary vehicle from the left is the one that has to give way."""
        return self.kind == 'left'


def cases(split, count):
    """Held-out cases vary approach and closing speeds beyond the demonstrated range.

    The kind cycles so every split carries all three in a fixed proportion: a policy
    that simply always stops fails the `left` cases, and one that never stops fails
    the rest. The other vehicle's start is derived from when it should reach the box
    relative to the ego, not drawn independently, so the cases actually bite.
    """
    if split not in {'train', 'validation', 'heldout'}:
        raise ValueError('Unknown junction split')
    base = {'train': 51000, 'validation': 55000, 'heldout': 61000}[split]
    training = split == 'train'
    result = []
    for i in range(count):
        r = np.random.default_rng(base+i)
        kind = KINDS[i % 3]
        side = 1. if kind == 'right' else -1. if kind == 'left' else float(r.choice([-1., 1.]))
        approach = float(r.uniform(7.5, 9.5) if training else r.uniform(6.8, 10.2))
        start_x = float(r.uniform(-58., -52.))
        other_speed = float(r.uniform(5.5, 8.5) if training else r.uniform(4.6, 9.4))
        # The crossing vehicle starts inside the arm length the native site actually
        # validates. Sampling its distance and speed independently still spreads the
        # arrival right across the ego's, from well before to many seconds after, so
        # some cases only need a lift-off and others a full stop and wait.
        other_start = float(r.uniform(-MAX_OTHER_START, -32.) if training
                            else r.uniform(-MAX_OTHER_START, -28.))
        ego_arrival = (-start_x-FRONT_OVERHANG)/approach
        result.append(JunctionCase(
            seed=base+i, split=split, kind=kind, approach_speed=approach, start_x=start_x,
            other_speed=other_speed, other_side=side, other_start=other_start,
            arrival_offset=round(-other_start/other_speed-ego_arrival, 3)))
    return result


HOLD_POINT = -(OTHER_HALF_LENGTH+CONFLICT_HALF_SPAN+1.2)


def step_other(case, other_s, ego_rear, dt):
    """Advance the crossing vehicle by one tick, returning its new position and speed.

    A vehicle that itself has to give way rolls up to its own line and waits there
    until the ego is completely through, which is what makes `left` a genuine
    negative case rather than a collision the ego could not have avoided. It is the
    ego's rear that has to be past the box, not its nose.
    """
    waiting = case.other_waits and other_s < HOLD_POINT and ego_rear < JUNCTION_DEPTH+1.5
    speed = min(case.other_speed, max(0., (HOLD_POINT-other_s)/1.2)) if waiting else case.other_speed
    return other_s+speed*dt, speed


def occupies(case, other_s):
    """Is the crossing vehicle inside the box the ego would drive through?"""
    return abs(other_s) <= OTHER_HALF_LENGTH+CONFLICT_HALF_SPAN


def gone(other_s):
    return other_s > CLEAR_MARGIN


def visible(case, front, other_s):
    """Whether the crossing vehicle is reported at all, from the ego's own position."""
    lateral = case.other_side*(-other_s)
    gap = math.hypot(JUNCTION_DEPTH/2-front, lateral)
    return gap <= SENSING_RANGE and front < JUNCTION_DEPTH and not gone(other_s)


def observation(state, case, other_s, other_speed, throttle, brake):
    """Eleven measured quantities. Nothing about the case kind is revealed directly:
    which side it comes from and whether its lights are on are both things you can see.
    """
    front = state[0]+FRONT_OVERHANG
    gap = math.hypot(JUNCTION_DEPTH/2-front, case.other_side*(-other_s))
    seen = visible(case, front, other_s)
    time_to = (-other_s)/max(other_speed, .1) if other_s < 0 else 0.
    return np.array([-front, state[1], float(seen),
                     other_s if seen else -SENSING_RANGE,
                     other_speed if seen else 0.,
                     float(np.clip(time_to, 0., 20.)) if seen else 20.,
                     gap if seen else SENSING_RANGE,
                     case.other_side if seen else 0.,
                     float(case.emergency) if seen else 0.,
                     throttle, brake], np.float32)


def encode(observations):
    """Raw normalised features plus a place code over approach distance and closing time."""
    a = np.atleast_2d(np.asarray(observations, dtype=np.float32))
    if a.shape[1] != len(OBSERVATION_FIELDS) or not np.isfinite(a).all():
        raise ValueError('Expected finite junction observations')
    distance = a[:, 0]/30
    speed = a[:, 1]/9
    other = a[:, 3]/30
    closing = a[:, 5]/6
    raw = np.column_stack([np.ones(len(a)), distance, np.square(distance), speed, a[:, 2],
                           other, a[:, 4]/9, closing, a[:, 6]/40, a[:, 7], a[:, 8],
                           a[:, 9], a[:, 10]])
    grid = np.stack(np.meshgrid(np.linspace(-.4, 2.2, 13), np.linspace(-2.2, 1.0, 11),
                                indexing='ij'), axis=-1).reshape(-1, 2)
    dd = (distance[:, None]-grid[:, 0])/.24
    do = (other[:, None]-grid[:, 1])/.32
    place = np.exp(-.5*(dd*dd+do*do))
    # A pure place code cannot express "from the right" or "under blue lights", so the
    # two flags gate copies of it; that is what lets one policy hold three behaviours.
    return np.concatenate([raw, place, place*speed[:, None], place*a[:, 7, None],
                           place*a[:, 8, None]], axis=1).astype(np.float32)


def separation(front, other_s):
    """Clearance between the ego's front bumper and the crossing vehicle's body."""
    along = JUNCTION_DEPTH/2-front
    across = abs(other_s)-OTHER_HALF_LENGTH
    return math.hypot(max(along, 0.), max(across, 0.)) if along > 0 or across > 0 else 0.


def metrics(trajectory, case):
    """Score one rollout. `trajectory` carries state, other_s and its speed.

    Giving way does not mean coming to a full stop: slowing enough to let the other
    vehicle through is correct driving and is scored as a pass. What fails is
    entering the box while it is occupied, closing to within touching distance, or
    stopping for a vehicle that had no priority.
    """
    required = False
    contact = False
    entered_occupied = False
    ever_relevant = False
    min_separation = math.inf
    overshoot = -math.inf
    rest_fronts = []
    for row in trajectory:
        front = row['state'][0]+FRONT_OVERHANG
        rear = row['state'][0]-REAR_TO_CENTER
        inside = occupies(case, row['other_s'])
        # Once the ego's rear is past the box it has left the junction; what the other
        # vehicle does behind it is no longer the ego's conflict.
        engaged = rear < JUNCTION_DEPTH
        if case.must_yield and not gone(row['other_s']) and front < JUNCTION_DEPTH:
            ever_relevant = True
        if inside and front < JUNCTION_DEPTH and case.must_yield:
            required = True
        if inside and rear <= JUNCTION_DEPTH/2 <= front:
            contact = True
        if engaged and not gone(row['other_s']):
            min_separation = min(min_separation, separation(front, row['other_s']))
        if engaged and inside and front > ENCROACH_MARGIN and row['state'][1] >= ENCROACH_SPEED:
            entered_occupied = True
        overshoot = max(overshoot, front)
        if row['state'][1] < .25:
            rest_fronts.append(front)
    final = trajectory[-1]
    cleared = final['state'][0]+FRONT_OVERHANG > JUNCTION_DEPTH
    stopped = [f for f in rest_fronts if f < JUNCTION_DEPTH]
    yielded = bool(stopped and min(stopped) <= ENCROACH_MARGIN)
    stopped_in_box = any(f > ENCROACH_MARGIN for f in stopped)
    unnecessary_stop = bool(stopped) and not ever_relevant
    too_close = bool(min_separation < 1.5)
    passed = (not contact and not entered_occupied and not stopped_in_box
              and not unnecessary_stop and not too_close and cleared)
    return {'kind': case.kind, 'stop_required': bool(required), 'contact': bool(contact),
            'entered_occupied': bool(entered_occupied), 'yielded_before_line': yielded,
            'stopped_in_box': bool(stopped_in_box), 'unnecessary_stop': bool(unnecessary_stop),
            'cleared_junction': bool(cleared), 'too_close': too_close,
            'min_separation_m': None if math.isinf(min_separation) else round(float(min_separation), 3),
            'max_overshoot_m': None if math.isinf(overshoot) else round(float(overshoot), 3),
            'passed': bool(passed)}
