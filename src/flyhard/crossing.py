"""Geometry and scoring for stopping at a marked pedestrian crossing.

Coordinates are metres along the approach lane. The stop line is x = 0 and the
ego travels towards positive x, so a negative front-bumper position is short of
the line. Positive y is the near kerb's side of the centreline.

No scenario phase, pedestrian intent, teacher command or elapsed time enters
observations. Whether a stop was required is derived afterwards for scoring and
is never shown to the policy.
"""
from dataclasses import asdict, dataclass
import math
import numpy as np

from flyhard.parking import CAR_LENGTH, CAR_WIDTH, REAR_TO_CENTER

CROSSING_DEPTH = 4.0       # Length of the painted band beyond the stop line.
CONFLICT_HALF_WIDTH = 1.6  # Lateral half-band the car actually sweeps.
SENSING_RANGE = 40.        # Beyond this the pedestrian is not reported at all.
THROTTLE_ACCEL = 3.0
BRAKE_DECEL = 6.5
PEDESTRIAN_RADIUS = .35
FRONT_OVERHANG = CAR_LENGTH-REAR_TO_CENTER
ENCROACH_MARGIN = .5   # Past the stop line by more than this counts as entering.
ENCROACH_SPEED = 1.0   # ...and only while still carrying this much speed.


@dataclass(frozen=True)
class CrossingCase:
    seed: int
    split: str
    road_width: float
    approach_speed: float
    start_x: float
    kerb_side: float
    walk_speed: float
    trigger_distance: float   # Ego front-bumper distance to the line when the walk starts.
    walk_offset: float        # Where along the painted band the pedestrian walks.
    dwell_seconds: float      # Pause at the kerb before stepping out; large means never.

    def record(self):
        return asdict(self)

    @property
    def start(self):
        """Ego state: rear-axle x, speed."""
        return np.array([self.start_x, self.approach_speed])

    @property
    def kerb_y(self):
        return self.kerb_side*(self.road_width/2+.6)


def cases(split, count):
    """Held-out cases vary the walk trigger and speed, not only the seed.

    Training never sees a 10.0 m road, the slowest walk or the latest trigger; those
    are reserved so that a held-out pass is not a replay of a memorised approach.
    """
    if split not in {'train', 'validation', 'heldout'}:
        raise ValueError('Unknown crossing split')
    base = {'train': 81000, 'validation': 85000, 'heldout': 91000}[split]
    training = split == 'train'
    result = []
    for i in range(count):
        r = np.random.default_rng(base+i)
        # A quarter of every split is a quiet case: the pedestrian waits and the
        # car should not stop. These score unnecessary stops.
        quiet = i % 4 == 3
        result.append(CrossingCase(
            seed=base+i, split=split,
            road_width=float(r.choice([9.0, 11.0] if training else [10.0])),
            approach_speed=float(r.uniform(7.5, 9.5)),
            start_x=float(r.uniform(-58., -52.)),
            kerb_side=float(r.choice([-1., 1.])),
            walk_speed=float(r.uniform(1.1, 1.6) if training else r.uniform(.9, 1.7)),
            trigger_distance=float(r.uniform(26., 40.) if training else r.uniform(18., 42.)),
            walk_offset=float(r.uniform(.6, CROSSING_DEPTH-.6)),
            dwell_seconds=float(1e6 if quiet else r.uniform(0., .8))))
    return result


def pedestrian_state(case, triggered_at, now):
    """Lateral position and velocity of the pedestrian at time `now`.

    Returns (y, lateral_velocity, walking). Before the trigger and during the
    kerb dwell the pedestrian stands still at the kerb.
    """
    if triggered_at is None:
        return case.kerb_y, 0., False
    elapsed = now-triggered_at-case.dwell_seconds
    if elapsed <= 0:
        return case.kerb_y, 0., False
    direction = -case.kerb_side
    travelled = case.walk_speed*elapsed
    span = abs(case.kerb_y)*2
    if travelled >= span:
        return case.kerb_y+direction*span, 0., False
    return case.kerb_y+direction*travelled, direction*case.walk_speed, True


def in_conflict(y):
    return abs(y) <= CONFLICT_HALF_WIDTH+PEDESTRIAN_RADIUS


OBSERVATION_FIELDS = ['front_to_stop_line', 'ego_speed', 'pedestrian_visible',
                      'pedestrian_band_x', 'pedestrian_y', 'pedestrian_lateral_speed',
                      'pedestrian_range', 'measured_throttle', 'measured_brake', 'road_width']


def observation(state, case, pedestrian_y, lateral_speed, throttle, brake):
    """Ten measured quantities. A pedestrian beyond the sensing range is reported absent."""
    front = state[0]+FRONT_OVERHANG
    band_x = case.walk_offset
    gap = math.hypot(band_x-front, pedestrian_y)
    visible = gap <= SENSING_RANGE and front < band_x+CROSSING_DEPTH
    return np.array([-front, state[1], float(visible),
                     band_x-front if visible else SENSING_RANGE,
                     pedestrian_y if visible else 0.,
                     lateral_speed if visible else 0.,
                     gap if visible else SENSING_RANGE,
                     throttle, brake, case.road_width], np.float32)


def encode(observations):
    """Raw normalised features plus a place code over approach distance and pedestrian offset."""
    a = np.atleast_2d(np.asarray(observations, dtype=np.float32))
    if a.shape[1] != 10 or not np.isfinite(a).all():
        raise ValueError('Expected finite crossing observations')
    distance = a[:, 0]/30
    speed = a[:, 1]/9
    band = a[:, 3]/30
    lateral = a[:, 4]/6
    raw = np.column_stack([np.ones(len(a)), distance, np.square(distance), speed, a[:, 2],
                           band, lateral, a[:, 5]/1.6, a[:, 6]/30, a[:, 7], a[:, 8], a[:, 9]/10])
    grid = np.stack(np.meshgrid(np.linspace(-.4, 2.2, 13), np.linspace(-1.2, 1.2, 9),
                                indexing='ij'), axis=-1).reshape(-1, 2)
    dd = (distance[:, None]-grid[:, 0])/.24
    dl = (lateral[:, None]-grid[:, 1])/.30
    place = np.exp(-.5*(dd*dd+dl*dl))
    return np.concatenate([raw, place, place*speed[:, None], place*a[:, 2, None]], axis=1).astype(np.float32)


def kinematic_step(state, throttle, brake, dt=.05):
    """Longitudinal training diagnostic only. Native trials use the measured body rig."""
    state = np.array(state, float, copy=True)
    acceleration = THROTTLE_ACCEL*float(np.clip(throttle, 0, 1))-BRAKE_DECEL*float(np.clip(brake, 0, 1))
    state[1] = max(0., state[1]+acceleration*dt)
    state[0] += state[1]*dt
    return state


def stopping_distance(speed):
    return speed*speed/(2*BRAKE_DECEL)


def metrics(trajectory, case):
    """Score one rollout.

    `trajectory` is a list of dicts carrying state, pedestrian_y and walking. A stop
    was required if the pedestrian was ever inside the conflict band while the car
    had not yet cleared the painted crossing.
    """
    required = False
    contact = False
    entered_on_pedestrian = False
    ever_occupied = False
    min_front_gap = math.inf
    overshoot = -math.inf
    rest_fronts = []
    for row in trajectory:
        front = row['state'][0]+FRONT_OVERHANG
        rear = row['state'][0]-REAR_TO_CENTER
        occupied = in_conflict(row['pedestrian_y'])
        ever_occupied = ever_occupied or occupied
        if occupied and front < case.walk_offset+CROSSING_DEPTH:
            required = True
        if occupied and rear <= case.walk_offset <= front:
            contact = True
        if occupied:
            min_front_gap = min(min_front_gap, math.hypot(case.walk_offset-front, row['pedestrian_y']))
            overshoot = max(overshoot, front)
            # Encroachment means driving into the crossing, not creeping a
            # centimetre over the line while coming to rest. A car still doing
            # ENCROACH_SPEED past ENCROACH_MARGIN has not yielded.
            if front > ENCROACH_MARGIN and row['state'][1] >= ENCROACH_SPEED:
                entered_on_pedestrian = True
        if row['state'][1] < .25:
            rest_fronts.append(front)
    final = trajectory[-1]
    cleared = final['state'][0]+FRONT_OVERHANG > case.walk_offset+CROSSING_DEPTH
    # A rest at the very end of a run that simply ran out of steps is not a yield.
    stopped = [f for f in rest_fronts if f < case.walk_offset+CROSSING_DEPTH]
    yielded = bool(stopped) and min(stopped) <= ENCROACH_MARGIN
    stopped_in_crossing = any(f > ENCROACH_MARGIN for f in stopped)
    unnecessary_stop = bool(stopped) and not ever_occupied
    passed = (not contact and not entered_on_pedestrian and not stopped_in_crossing
              and not unnecessary_stop and cleared)
    return {'stop_required': required, 'contact': contact,
            'entered_on_pedestrian': entered_on_pedestrian,
            'yielded_before_line': yielded, 'stopped_in_crossing': bool(stopped_in_crossing),
            'unnecessary_stop': bool(unnecessary_stop), 'cleared_crossing': bool(cleared),
            'min_pedestrian_gap_m': None if math.isinf(min_front_gap) else round(min_front_gap, 3),
            'max_overshoot_m': None if math.isinf(overshoot) else round(overshoot, 3),
            'passed': bool(passed)}
