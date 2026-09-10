"""Observed traffic-light history, held-out scenarios, and horn evaluation.

Scenario labels are used only by training/evaluation. Inference receives raw
light/car observations in a fixed rolling buffer, never the transition time,
scenario identity, teacher label or a precomputed red-to-green flag.
"""
from collections import deque
from dataclasses import asdict, dataclass

import numpy as np


DT = .1
HISTORY = 11
FIELDS = ['light_red', 'light_green', 'lead_in_lane', 'lead_distance_m',
          'lead_speed_m_s', 'ego_speed_m_s']
KINDS = ['wait_then_green', 'no_car', 'arrive_green', 'stays_red',
         'car_leaves_on_red', 'car_in_other_lane']
PULSE_SECONDS = .6


class ObservationHistory:
    def __init__(self):
        self.samples = deque(maxlen=HISTORY)

    def update(self, observation):
        x = np.asarray(observation, dtype=np.float32)
        if x.shape != (len(FIELDS),) or not np.isfinite(x).all():
            raise ValueError('Expected finite horn observations')
        if not self.samples:
            self.samples.extend(x.copy() for _ in range(HISTORY))
        else:
            self.samples.append(x.copy())
        return np.asarray(self.samples, dtype=np.float32)


def encode_history(history):
    x = np.asarray(history, dtype=np.float32)
    single = x.ndim == 2
    x = x[None] if single else x
    if x.shape[1:] != (HISTORY, len(FIELDS)) or not np.isfinite(x).all():
        raise ValueError('Expected a complete finite raw observation history')
    x = x.copy()
    x[:, :, 3] = np.clip(x[:, :, 3], 0, 30) / 15
    x[:, :, 4:6] = np.clip(x[:, :, 4:6], -5, 5) / 5
    flat = x.reshape(len(x), -1)
    # Frozen generic random features mix observations without a target-specific
    # conjunction. The seed/projection never depend on labels or test outcomes.
    rng = np.random.default_rng(501)
    projection = rng.normal(0, .4, (flat.shape[1], 128)).astype(np.float32)
    offset = rng.uniform(-1, 1, 128).astype(np.float32)
    features = np.concatenate([np.ones((len(x), 1)), flat,
                               np.tanh(flat @ projection + offset)], axis=1).astype(np.float32)
    return features[0] if single else features


@dataclass(frozen=True)
class HornCase:
    seed: int
    kind: str
    gap_m: float
    green_at: float
    duration: float = 6.
    ego_speed: float = 0.
    lead_speed: float = 0.

    def as_dict(self):
        return asdict(self)


def make_cases(split, per_kind=30):
    offsets = {'train':110000, 'validation':120000, 'test':130000}
    if split not in offsets:
        raise ValueError('Unknown split')
    cases = []
    for k, kind in enumerate(KINDS):
        for i in range(per_kind):
            seed = offsets[split] + k * 1000 + i
            rng = np.random.default_rng(seed)
            gap = rng.uniform(3, 6) if split == 'train' else rng.uniform(6.5, 9.5)
            switch = rng.uniform(1.5, 3.0) if split == 'train' else rng.uniform(3.2, 4.4)
            cases.append(HornCase(seed, kind, float(gap), float(switch),
                                 ego_speed=float(rng.uniform(0, 2.)),
                                 lead_speed=float(rng.uniform(0, .1))))
    return cases


def observation(case, time):
    green = case.kind == 'arrive_green' or (time >= case.green_at and case.kind != 'stays_red')
    present = case.kind not in {'no_car', 'car_in_other_lane'}
    if case.kind == 'car_leaves_on_red' and time >= case.green_at - .7:
        present = False
    return np.array([not green, green, present, case.gap_m if present else 30.,
                     case.lead_speed if present else 0., case.ego_speed], dtype=np.float32)


def teacher(case, time):
    return case.kind == 'wait_then_green' and case.green_at <= time < case.green_at + PULSE_SECONDS


def episode(case):
    history = ObservationHistory()
    times = np.arange(round(case.duration / DT), dtype=np.float64) * DT
    features = np.stack([encode_history(history.update(observation(case, t))) for t in times])
    labels = np.array([teacher(case, t) for t in times], dtype=bool)
    return times, features, labels


def score(case, times, pressed):
    times, pressed = np.asarray(times), np.asarray(pressed, dtype=bool)
    if len(times) != len(pressed) or not len(times) or np.any(np.diff(times) <= 0):
        raise ValueError('A horn trial needs one ordered press measurement per tick')
    onset = np.flatnonzero(pressed & ~np.r_[False, pressed[:-1]])
    expected = case.kind == 'wait_then_green'
    before = bool(np.any(pressed[times < case.green_at])) if expected else bool(np.any(pressed))
    latency = float(times[onset[0]] - case.green_at) if expected and len(onset) else None
    timely = latency is not None and 0 <= latency <= .8
    release = (not pressed[-1] and not np.any(pressed[times >= case.green_at + 1.6])) if expected else not before
    return {'seed':case.seed, 'kind':case.kind, 'expected_beep':expected,
            'beep_count':len(onset), 'beep_onsets_seconds':times[onset].tolist(),
            'reaction_seconds':latency, 'false_beep':before,
            'pressed_seconds':float(pressed.sum() * np.median(np.diff(times))),
            'passed':bool(timely and len(onset) == 1 and not before and release) if expected else not before}


def valid_light_sequence(kind, neural_green, displayed_green):
    """Reject a recording whose actual light observations break the scenario."""
    streams = [np.asarray(neural_green,dtype=bool),np.asarray(displayed_green,dtype=bool)]
    if any(s.ndim != 1 or not len(s) for s in streams):
        return False
    if kind == 'arrive_green':
        return all(bool(s.all()) for s in streams)
    if kind not in {'wait_then_green','no_car'}:
        raise ValueError('Unsupported recorded horn scenario')
    return all(bool(not s[0] and s[-1] and not np.any(np.diff(s.astype(int)) < 0)) for s in streams)
