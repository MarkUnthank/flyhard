"""Structured observations for jointly learned steering and horn behaviour.

The instructed road-rage mode and wheel request are explicit task inputs.
Elapsed time, episode labels and teacher horn state never enter inference.
"""
from collections import deque
from dataclasses import asdict, dataclass
from functools import lru_cache
import numpy as np

DT = .1
HISTORY = 41
HISTORY_INDICES = [0, 10, 20, 25, 30, 34, 36, 37, 38, 39, 40]
ENCODING = 'raw-multiscale-history-current-wheel-v2'
FIELDS = ['red', 'green', 'lead_in_lane', 'gap_m', 'lead_speed_m_s',
          'ego_speed_m_s', 'nearby_car', 'nearest_car_m', 'rage_mode', 'wheel_request_rad']
KINDS = ['wait_green', 'empty', 'arrive_green', 'stays_red', 'lead_leaves',
         'side_car', 'cut_in', 'cut_in_clears', 'rage_cars', 'rage_empty']


class History:
    def __init__(self):
        self.samples = deque(maxlen=HISTORY)

    def update(self, observation):
        row = np.asarray(observation, np.float32)
        if row.shape != (len(FIELDS),) or not np.isfinite(row).all():
            raise ValueError('Expected ten finite observed/task fields')
        if not self.samples:
            self.samples.extend(row.copy() for _ in range(HISTORY))
        else:
            self.samples.append(row.copy())
        return np.asarray(self.samples)


@lru_cache(maxsize=1)
def projection():
    rng = np.random.default_rng(802)
    count = len(HISTORY_INDICES)*(len(FIELDS)-1)+1
    return rng.normal(0, .4, (count, 128)).astype(np.float32), rng.uniform(-1, 1, 128).astype(np.float32)


def encode(history):
    x = np.asarray(history, np.float32)
    single = x.ndim == 2
    x = x[None] if single else x
    if x.shape[1:] != (HISTORY, len(FIELDS)) or not np.isfinite(x).all():
        raise ValueError('Expected full finite observation histories')
    x = x.copy()
    x[:, :, [3, 7]] = np.clip(x[:, :, [3, 7]], 0, 40)/20
    x[:, :, 4:6] = np.clip(x[:, :, 4:6], 0, 20)/12
    x[:, :, 9] = np.clip(x[:, :, 9]/.4, -1, 1)
    # Route history has no bearing on horn etiquette. The steering task receives
    # its current request; traffic retains raw samples spanning four seconds.
    flat = np.c_[x[:, HISTORY_INDICES, :-1].reshape(len(x), -1), x[:, -1, -1]]
    matrix, bias = projection()
    result = np.concatenate([np.ones((len(x), 1)), flat, np.tanh(flat@matrix+bias)], axis=1).astype(np.float32)
    return result[0] if single else result


@dataclass(frozen=True)
class Case:
    seed: int
    kind: str
    event: float
    gap: float
    speed: float
    wheel: float
    phase: float
    duration: float = 12.

    def as_dict(self):
        return asdict(self)


def cases(split, per_kind):
    base = {'train':810000, 'validation':820000, 'test':830000}[split]
    result = []
    for k, kind in enumerate(KINDS):
        for i in range(per_kind):
            seed = base+k*1000+i
            rng = np.random.default_rng(seed)
            event_max = 4. if kind.startswith('rage_') else 7. if kind in {'wait_green','empty','stays_red','lead_leaves'} else 5.
            result.append(Case(seed, kind, float(rng.uniform(2., event_max)),
                               float(rng.uniform(2.5, 16.)), float(rng.uniform(3., 11.)),
                               float(rng.uniform(-.32, .32)), float(rng.uniform(0, 6.28))))
    return result


def observed(case, t):
    k, event = case.kind, case.event
    rage = k.startswith('rage_')
    green = k in {'arrive_green', 'side_car', 'cut_in', 'cut_in_clears'} or rage
    green |= t >= event and k in {'wait_green', 'empty', 'lead_leaves'}
    lead = k in {'wait_green', 'arrive_green', 'stays_red', 'lead_leaves'}
    if k == 'lead_leaves' and t > event-.7:
        lead = False
    if k in {'cut_in', 'cut_in_clears'}:
        lead = t >= event and (k != 'cut_in_clears' or t < event+1.5)
    nearby = lead or k == 'side_car'
    if k == 'rage_cars':
        nearby = event <= t < event+1.6 or event+3 <= t < event+4.6 or event+6 <= t < event+7.6
    if rage:
        lead = False
    gap = max(.5, case.gap - .7*(t-event)) if lead else 40.
    moving = green and k != 'stays_red'
    speed = case.speed if moving else max(0., case.speed*(1-t/max(event-.6, .5)))
    if k in {'wait_green', 'empty'} and green:
        speed = min(case.speed, max(0., (t-event-1.)*2.))
    lead_speed = (max(0., case.speed-2) if moving else speed) if lead else 0.
    if k == 'wait_green' and green:
        lead_speed = min(case.speed, max(0., (t-event-.7)*2.))
    nearest = min(40., gap+4.6) if lead else min(case.gap+2,13.) if nearby else 40.
    nearby = nearest < 14.
    # Static, varying and reversing requests exercise both legs simultaneously.
    wheel = case.wheel*np.sin(t*.6+case.phase)
    return np.array([not green, green, lead, gap, lead_speed, speed,
                     nearby, nearest, rage, wheel], np.float32)


def teacher(case, t):
    if case.kind == 'wait_green':
        return case.event <= t < case.event+.6
    if case.kind == 'cut_in':
        return case.event <= t < case.event+3.
    if case.kind == 'cut_in_clears':
        return case.event <= t < case.event+1.5
    if case.kind == 'rage_cars':
        return bool(observed(case, t)[6])
    return False


def episode(case):
    h = History()
    times = np.arange(round(case.duration/DT))*DT
    rows = np.array([observed(case, t) for t in times])
    inputs = encode(np.array([h.update(row) for row in rows]))
    labels = np.array([teacher(case, t) for t in times])
    return times, inputs, labels, rows[:, -1]
