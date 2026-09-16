"""Geometry and scoring for overtaking a slower vehicle on a dual carriageway.

Coordinates are metres in the carriageway frame: x runs along the road, y is lateral
with positive to the left, and the ego starts in the right-hand lane at y = 0. The
overtaking lane is therefore at y = +LANE_WIDTH.

This is the one scenario where the fly steers. The policy produces three measured
controls, throttle, brake and steering wheel angle, and all three reach CARLA only as
travel measured off the fly's own limbs.

Three case kinds share one policy and the discrimination between them is the point:

  clear     the lane beside is empty, so pull out, pass and return
  blocked   something quicker is already coming up the outside, so wait for it
  no_need   the vehicle ahead is not slower, so stay where you are
"""
from dataclasses import asdict, dataclass
import math

import numpy as np

from flyhard.crossing import (BRAKE_FREE_PLAY, COAST_DECEL, THROTTLE_FREE_PLAY, brake_decel,
                              brake_for_decel, past_free_play, terminal_speed, throttle_for_speed)
from flyhard.parking import CAR_LENGTH, CAR_WIDTH, REAR_TO_CENTER

LANE_WIDTH = 3.5
WHEELBASE = 2.5            # Mini Cooper S, front to rear axle.
MAX_STEER_DEG = 69.        # CARLA's max road-wheel angle for this vehicle; measured on the pod.
STEER_RATIO = .715         # Measured in Town04 at 8-11 m/s; see work/steering-calibration.json.
WHEEL_PER_STEER = 2.0      # Steering wheel radians per unit of CARLA steer, as the rig is built.
APPROACH_LAG = .20
FRONT_OVERHANG = CAR_LENGTH-REAR_TO_CENTER
SENSING_RANGE = 90.
LANE_TOLERANCE = .8        # Counted as settled in a lane inside this much of its centre;
                           # a lane is 3.5 m wide, so this is still unambiguously in it.
SAFE_GAP = 6.0             # Longitudinal clearance demanded before pulling back in.
SIDE_CLEARANCE = 2.2       # Lateral clearance that counts as sharing a lane.
CURVATURE_SCALE = .006     # A 170 m radius; the sharpest bend on the chosen carriageway.
KINDS = ('clear', 'blocked', 'no_need')

OBSERVATION_FIELDS = ['ego_speed', 'lane_offset', 'heading_error', 'lead_visible', 'lead_gap',
                      'lead_closing_speed', 'lead_lane_offset', 'outside_visible', 'outside_gap',
                      'outside_closing_speed', 'measured_throttle', 'measured_brake',
                      'measured_steer', 'lane_curvature']


@dataclass(frozen=True)
class OvertakeCase:
    seed: int
    split: str
    kind: str
    cruise_speed: float       # What the ego would hold on an empty road.
    lead_speed: float
    lead_gap: float           # Longitudinal gap to the lead when the run starts.
    outside_speed: float      # Speed of the vehicle already in the overtaking lane.
    outside_gap: float        # Its longitudinal offset at the start; negative is behind.
    curvature: float          # Peak signed lane curvature, 1/m. Positive bends left.
    curve_period: float       # Metres over which the curvature completes one cycle.

    def record(self):
        return asdict(self)

    @property
    def start(self):
        """[x, y, heading, speed]."""
        return np.array([0., 0., 0., self.cruise_speed])

    @property
    def has_outside(self):
        return self.kind == 'blocked'

    @property
    def should_overtake(self):
        return self.kind in {'clear', 'blocked'}


def cases(split, count):
    """Held-out cases widen every speed and gap beyond what was demonstrated."""
    if split not in {'train', 'validation', 'heldout'}:
        raise ValueError('Unknown overtake split')
    base = {'train': 71000, 'validation': 75000, 'heldout': 78000}[split]
    training = split == 'train'
    result = []
    for i in range(count):
        r = np.random.default_rng(base+i)
        kind = KINDS[i % 3]
        # Speeds are set by the road rather than by taste: the longest straight with a
        # same-direction lane beside it anywhere in the stock towns is 228 m, and a pass
        # at motorway speed needs closer to three hundred. Around fifty km/h fits.
        cruise = float(r.uniform(13.5, 16.) if training else r.uniform(12.5, 17.))
        # `no_need` puts a vehicle ahead that is not actually slower, so the only
        # correct action is to hold the lane and the speed.
        lead = (cruise*float(r.uniform(1.0, 1.12)) if kind == 'no_need'
                else cruise*float(r.uniform(.55, .78) if training else r.uniform(.48, .84)))
        result.append(OvertakeCase(
            seed=base+i, split=split, kind=kind, cruise_speed=cruise, lead_speed=float(lead),
            lead_gap=float(r.uniform(26., 36.) if training else r.uniform(23., 39.)),
            outside_speed=float(cruise*r.uniform(1.14, 1.34)),
            outside_gap=float(r.uniform(-48., -28.) if training else r.uniform(-54., -24.)),
            # The carriageway bends. Measured on the chosen Town04 site, the sharpest
            # twelve-metre step turns 3.8 degrees, which is 0.0056 per metre, and the
            # bend reverses over a few hundred metres. A straight-lane demonstrator has
            # no feed-forward for that and settles most of a metre off the centre line.
            curvature=float(r.uniform(-.0055, .0055) if training else r.uniform(-.008, .008)),
            curve_period=float(r.uniform(420., 900.) if training else r.uniform(300., 1100.))))
    return result


def lane_curvature(case, distance):
    """Signed curvature of the lane at a distance along it, positive bending left."""
    return float(case.curvature*math.cos(2*math.pi*float(distance)/case.curve_period))


def traffic_state(case, now, ego_x):
    """Positions and speeds of the other two vehicles, relative to the ego."""
    lead_x = case.lead_gap+case.lead_speed*now
    outside_x = case.outside_gap+case.outside_speed*now if case.has_outside else None
    return ((lead_x-ego_x, case.lead_speed),
            ((outside_x-ego_x, case.outside_speed) if outside_x is not None else (None, 0.)))


def observation(state, case, lead_gap, lead_speed, outside_gap, outside_speed, curvature,
                throttle, brake, steer):
    """Fourteen measured quantities. Nothing names the case kind.

    The other vehicles' speeds are the ones observed, not the ones the case asked for.
    In the diagnostic model those are the same number; in CARLA a van asked to hold
    seven metres a second may be doing six, and a policy told otherwise drives into it.
    """
    speed = state[3]
    lead_seen = lead_gap is not None and -14. < lead_gap <= SENSING_RANGE
    outside_seen = outside_gap is not None and -SENSING_RANGE <= outside_gap <= SENSING_RANGE
    return np.array([
        speed, state[1], state[2], float(lead_seen),
        lead_gap if lead_seen else SENSING_RANGE,
        (lead_speed-speed) if lead_seen else 0.,
        0.,
        float(outside_seen),
        outside_gap if outside_seen else -SENSING_RANGE,
        (outside_speed-speed) if outside_seen else 0.,
        throttle, brake, steer, curvature], np.float32)


def encode(observations):
    """Raw normalised features plus a place code over the two gaps and lane offset."""
    a = np.atleast_2d(np.asarray(observations, dtype=np.float32))
    if a.shape[1] != len(OBSERVATION_FIELDS) or not np.isfinite(a).all():
        raise ValueError('Expected finite overtake observations')
    speed = a[:, 0]/15
    offset = a[:, 1]/LANE_WIDTH
    heading = a[:, 2]/.2
    lead = a[:, 4]/30
    outside = a[:, 8]/30
    raw = np.column_stack([np.ones(len(a)), speed, offset, np.square(offset), heading, a[:, 3],
                           lead, a[:, 5]/6, a[:, 7], outside, a[:, 9]/6,
                           a[:, 10], a[:, 11], a[:, 12], a[:, 13]/CURVATURE_SCALE,
                           a[:, 13]*speed/CURVATURE_SCALE])
    grid = np.stack(np.meshgrid(np.linspace(-.4, 2.2, 11), np.linspace(-.4, 1.4, 9),
                                indexing='ij'), axis=-1).reshape(-1, 2)
    dl = (lead[:, None]-grid[:, 0])/.26
    do = (offset[:, None]-grid[:, 1])/.22
    place = np.exp(-.5*(dl*dl+do*do))
    return np.concatenate([raw, place, place*speed[:, None], place*a[:, 7, None],
                           place*np.clip(outside, -2, 2)[:, None]], axis=1).astype(np.float32)


def road_wheel_angle(steer):
    """Road-wheel angle for a steering demand, through the measured linkage.

    `steer` is in the same units CARLA takes, which is what the fly's wheel travel is
    converted into. STEER_RATIO carries the gap between the bicycle model's curvature
    and the curvature the car actually turns, the same correction the three-point turn
    needed; it is re-measured rather than assumed, see scripts/calibrate_steering.py.
    """
    return math.radians(MAX_STEER_DEG*STEER_RATIO*float(np.clip(steer, -1., 1.)))


def kinematic_step(state, throttle, brake, steer, curvature=0., dt=.05):
    """Bicycle model on the measured longitudinal response. A training diagnostic only.

    The state is in the lane's own frame, so a bending lane turns underneath the car:
    holding a heading error of zero on a left-hand bend needs a steering angle, not a
    straight wheel. Without this the model would teach a control law that leaves the
    lane as soon as the road stops being straight.
    """
    state = np.array(state, float, copy=True)
    if past_free_play(brake, BRAKE_FREE_PLAY) > 0.:
        acceleration = -brake_decel(brake)
    elif past_free_play(throttle, THROTTLE_FREE_PLAY) > 0.:
        acceleration = APPROACH_LAG*(terminal_speed(throttle)-state[3])
    else:
        acceleration = -COAST_DECEL if state[3] > 0. else 0.
    state[3] = max(0., state[3]+acceleration*dt)
    turn = state[3]*math.tan(road_wheel_angle(steer))/WHEELBASE
    state[2] += (turn-curvature*state[3]*math.cos(state[2])/max(1.-curvature*state[1], .2))*dt
    state[2] = float(np.clip(state[2], -.6, .6))
    # Distance is arc length along the lane centre, so a car running wide on a bend
    # covers more ground than the centre line does.
    state[0] += state[3]*math.cos(state[2])/max(1.-curvature*state[1], .2)*dt
    state[1] += state[3]*math.sin(state[2])*dt
    return state


def overlapping(gap):
    """Two cars share road at this longitudinal offset."""
    return abs(gap) < CAR_LENGTH+.4


def metrics(trajectory, case):
    """Score one rollout. Rows carry state, lead_gap and outside_gap."""
    min_lead_gap = math.inf
    min_outside_gap = math.inf
    collided = False
    cut_in = False
    used_outside_lane = False
    strayed = False
    for row in trajectory:
        state, lead, outside = row['state'], row['lead_gap'], row['outside_gap']
        offset = state[1]
        if offset > LANE_WIDTH/2:
            used_outside_lane = True
        if offset < -LANE_TOLERANCE-.4 or offset > LANE_WIDTH+LANE_TOLERANCE+.4:
            strayed = True          # Off the two-lane carriageway entirely.
        if lead is not None and abs(offset) < SIDE_CLEARANCE:
            min_lead_gap = min(min_lead_gap, abs(lead))
            if overlapping(lead):
                collided = True
            # Back in the ego's own lane with the vehicle it just passed close behind:
            # that is pulling in too early, however clean the rest of the move was.
            if -SAFE_GAP < lead < 0:
                cut_in = True
        if outside is not None and abs(offset-LANE_WIDTH) < SIDE_CLEARANCE:
            min_outside_gap = min(min_outside_gap, abs(outside))
            if overlapping(outside):
                collided = True
    final = trajectory[-1]
    ahead = final['lead_gap'] is not None and final['lead_gap'] < -CAR_LENGTH
    settled = abs(final['state'][1]) <= LANE_TOLERANCE
    overtook = bool(ahead and settled)
    if case.should_overtake:
        passed = overtook and not collided and not cut_in and not strayed
    else:
        passed = (not used_outside_lane and not collided and not strayed
                  and abs(final['state'][1]) <= LANE_TOLERANCE)
    return {'kind': case.kind, 'overtake_required': bool(case.should_overtake),
            'overtook': overtook, 'used_outside_lane': bool(used_outside_lane),
            'collided': bool(collided), 'cut_in': bool(cut_in), 'strayed': bool(strayed),
            'returned_to_lane': bool(settled),
            'min_lead_gap_m': None if math.isinf(min_lead_gap) else round(float(min_lead_gap), 2),
            'min_outside_gap_m': (None if math.isinf(min_outside_gap)
                                  else round(float(min_outside_gap), 2)),
            'final_lane_offset_m': round(float(final['state'][1]), 3),
            'passed': bool(passed)}
