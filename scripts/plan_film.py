#!/usr/bin/env python3
"""Build an edit plan from the clip library, cutting each take at its own events.

Shot boundaries come from the recorded trace, not from guesses: the approach ends
where the car first touches the brake, the decision runs from there to rest, and the
resume starts when it moves off again. Editing the film afterwards is a matter of
changing this plan, or the JSON it writes, and re-running the assembler.
"""
import argparse
from itertools import zip_longest
import json
import math
from pathlib import Path

import numpy as np

from flyhard.clips import ClipLibrary

# One angle per beat, in the order the beats happen, so a scenario is seen from
# outside, from behind the car and from over the fly's own controls. Where a take has
# more shots than beats the angle keeps rotating through this order rather than
# repeating, because holding one camera for eight seconds is what made the first cut
# drag on exactly the takes that have no event to cut around.
BEAT_CAMERAS = {'approach': 'wide', 'decision': 'chase', 'resume': 'cabin'}
CAMERA_ORDER = ('wide', 'chase', 'cabin')
# One section per behaviour, not per scenario: the junction policy holds two of them
# and they are worth showing as two, because the interesting part is that one policy
# tells them apart.
SECTIONS = [
    ('crossing', None, 'Stopping for pedestrians'),
    ('junction', ('right', 'left'), 'Giving way to the right'),
    ('junction', ('priority',), 'Stopping for a priority vehicle'),
    ('overtake', None, 'Overtaking on the highway'),
]


def events(take_dir, fps):
    """Times of the moments worth cutting on, read from the take's own trace."""
    trace_path = Path(take_dir)/'trace.json'
    if not trace_path.exists():
        return None
    rows = json.loads(trace_path.read_text())
    if not rows:
        return None
    total = rows[-1]['time']
    braked = [r['time'] for r in rows if r['measured_brake'] > .2]
    resting = [r['time'] for r in rows if r['speed_m_s'] < .4]
    moving_after = [r['time'] for r in rows
                    if resting and r['time'] > resting[-1] and r['speed_m_s'] > 1.5]
    first_brake = braked[0] if braked else None
    stopped = resting[0] if resting else None
    resumed = moving_after[0] if moving_after else None
    # Overtaking has no stop to cut on. Its decisive moment is the wheel going over,
    # and its equivalent of resuming is the car coming back into its own lane.
    out = [r['time'] for r in rows if abs(r.get('lane_offset') or 0.) > 1.]
    returned = [r['time'] for r in rows
                if out and r['time'] > out[-1] and abs(r.get('lane_offset') or 0.) < .5]
    # A policy that stops and stays there leaves twenty-odd seconds of parked car. The
    # film should not spend its budget on that, so remember when the car last moved.
    moving = [r['time'] for r in rows if r['speed_m_s'] > 1.5]
    return {'total': total, 'first_brake': first_brake, 'stopped': stopped,
            'resumed': resumed, 'pulled_out': out[0] if out else None,
            'returned': returned[0] if returned else None,
            'moving_until': moving[-1] if moving else None,
            'peak_speed_time': max(rows, key=lambda r: r['speed_m_s'])['time']}


# Roughly half a car, used as the radius of a sphere around its origin. A shot only
# counts as being on the car when that whole sphere is inside the frustum, so a car
# clipping the corner of frame does not pass for a shot of it.
CAR_RADIUS = 2.4


def in_frame(take_dir):
    """When each world-fixed camera actually has the car in shot, from the recorded poses.

    The wide camera is planted off the near side of the approach and aimed at the
    junction, so the car spends most of its run *behind* the lens and arrives in frame
    about a second before the line. Estimating that from the distance to the stop line
    was wrong by a factor of seven and put four seconds of empty junction in the film.
    Every frame already records the camera's pose in the car's own frame, so this is
    measured rather than guessed.

    Attached cameras ride the car and are left out: they always have it.
    """
    manifest_path = Path(take_dir)/'cameras.json'
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text())
    fps = manifest.get('fps', 20)
    width, height = manifest['width'], manifest['height']
    windows = {}
    for name, view in manifest['views'].items():
        if view.get('attached', True):
            continue
        seen = []
        for frame in manifest['frames']:
            recorded = frame['views'].get(name)
            if recorded is None or 'relative_matrix' not in recorded:
                continue
            matrix = np.asarray(recorded['relative_matrix'], float)
            # The camera's pose in the car's frame, so the car's origin in the camera's
            # frame is the rotation's transpose applied to minus the translation.
            forward, right, up = matrix[:3, :3].T @ -matrix[:3, 3]
            if forward <= CAR_RADIUS:
                continue
            across = view['fov']/2
            down = math.degrees(math.atan(math.tan(math.radians(across))*height/width))
            margin = math.degrees(math.asin(min(1., CAR_RADIUS/forward)))
            if (abs(math.degrees(math.atan2(right, forward))) < across-margin
                    and abs(math.degrees(math.atan2(up, forward))) < down-margin):
                seen.append(frame['index']/fps)
        windows[name] = (seen[0], seen[-1]) if seen else None
    return windows


# Per beat: how long it wants to be, and how long it may stretch to when a scenario
# has screen time to spare. Nothing is ever stretched past the take's own footage.
BEAT_LIMITS = {'approach': (2.6, 5.0), 'decision': (3.4, 5.4), 'resume': (2.0, 4.5)}


def spread(total, budget, count=3, longest=5.0, active=None):
    """Evenly spaced shots across a take that has no event worth cutting around.

    A policy that simply stops and stays there has no brake moment, no rest and no
    resume, so the event finder has nothing to anchor on. Rather than hold one camera
    on it for the whole budget, walk through the take and change angle. `active` cuts
    the walk short where the car stopped moving, so the shots land on the part of the
    take where something happens rather than on a parked car.
    """
    if active is not None:
        total = max(min(total, active+2.), 3.)
    count = max(1, min(count, int(total//2.2)))
    each = min(longest, max(1.4, budget/count))
    if count == 1:
        return [{'beat': 'decision', 'start': 0., 'duration': round(min(each, total), 2)}]
    step = max((total-each)/(count-1), 0.)
    return [{'beat': 'decision', 'start': round(i*step, 2), 'duration': round(each, 2)}
            for i in range(count)]


def beats(record, budget):
    """Split one take's screen time into beats, each anchored on a real moment."""
    marks = events(record['directory'], record['fps'])
    total = record['duration_seconds']
    if not marks:
        return spread(total, budget)
    active = marks['moving_until']
    anchor = marks['first_brake'] or marks['pulled_out'] or marks['peak_speed_time']
    settle = marks['resumed'] or marks['returned']
    shots = []
    if anchor > 2.4:
        # Run into the decision, not away from it: the seconds before the brake.
        shots.append({'beat': 'approach',
                      'start': max(0., anchor-BEAT_LIMITS['approach'][1])})
    shots.append({'beat': 'decision', 'start': max(0., anchor-.8)})
    if settle and total-settle > 1.2:
        shots.append({'beat': 'resume', 'start': max(0., settle-.8)})

    for shot in shots:
        low, high = BEAT_LIMITS[shot['beat']]
        shot['low'], shot['high'] = low, min(high, total-shot['start'])
    shots = [s for s in shots if s['high'] >= .9]
    if not shots:
        return spread(total, budget, active=active)
    if len(shots) == 1 and total > 6.:
        # One beat is not a sequence. Walk the take instead, so the angle changes.
        return spread(total, budget, active=active)
    # Give every beat its natural length, then spend or take back the difference in
    # proportion, so a scenario with spare time gets longer shots rather than more.
    floor = sum(min(s['low'], s['high']) for s in shots)
    ceiling = sum(s['high'] for s in shots)
    if budget <= floor:
        share = budget/floor
        for shot in shots:
            shot['duration'] = min(shot['low'], shot['high'])*share
    else:
        extra = (min(budget, ceiling)-floor)/max(ceiling-floor, 1e-6)
        for shot in shots:
            low = min(shot['low'], shot['high'])
            shot['duration'] = low+(shot['high']-low)*extra
    for shot in shots:
        shot['duration'] = round(max(.9, min(shot['duration'], shot['high'])), 2)
        shot['start'] = round(shot['start'], 2)
        del shot['low'], shot['high']
    return shots


def place(record, shots, windows):
    """Give every shot the angle its beat wants, skipping cameras that are not on the car.

    The beat sets the starting angle and the rotation carries on from there, so a take
    with three shots is seen from three sides. A camera whose frustum does not hold the
    car for the shot is passed over rather than used: the wide angle covers only the
    last seconds of an approach, and a shot of the empty road it sees before that is
    worse than the same moment from another angle.
    """
    placed, used = [], set()
    for index, shot in enumerate(shots):
        start_at = CAMERA_ORDER.index(BEAT_CAMERAS[shot['beat']])
        order = [CAMERA_ORDER[(start_at+index+step) % len(CAMERA_ORDER)]
                 for step in range(len(CAMERA_ORDER))]
        order = [name for name in order if name in record['cameras']]
        order = order or [next(iter(record['cameras']))]
        holds = [name for name in order
                 if holds_shot(windows.get(name, (0., None)), shot,
                               record['duration_seconds'])]
        if holds:
            # Prefer whichever of them has the car for the shortest time. The two angles
            # riding the car can cover any moment of any take, so a moment the wide
            # camera happens to catch should be spent on the wide camera; the rotation
            # only breaks ties. Angles already used in this take go last, so a take is
            # still seen from as many sides as it has shots.
            fresh = [name for name in holds if name not in used] or holds
            camera = min(fresh, key=lambda name: (span(windows.get(name, (0., None))),
                                                 fresh.index(name)))
        else:
            # Nothing frames this moment cleanly. Take the angle that holds the car
            # longest and let the clamp below move the shot into its window.
            camera = max(order, key=lambda name: covered(windows.get(name, (0., None)), shot))
        used.add(camera)
        placed.append((camera, clamp(shot, windows.get(camera, (0., None)),
                                     record['duration_seconds'])))
    return placed


def span(window):
    """How long a camera has the car for. A camera riding it has it for the whole take."""
    if window is None:
        return 0.
    first, last = window
    return math.inf if last is None else last-first


# How far a beat may be pushed later to land inside a camera's window. An approach is
# the seconds before the decision and a decision is the moment itself, so neither may
# move at all; a resume is the car getting going again, which reads as well a second or
# two in. Without this the wide camera sat unused on every take that stopped at the
# line, because its window opens just after the car pulls away.
BEAT_SLIDE = {'approach': 0., 'decision': 0., 'resume': 2.5}


def holds_shot(window, shot, total):
    """Whether a camera has the car for the whole of a shot, allowing the beat's own slide."""
    if window is None:
        return False
    first, last = window
    start = max(shot['start'], min(first, shot['start']+BEAT_SLIDE.get(shot['beat'], 0.)))
    if start < first-.05:
        return False
    end = min(total, last if last is not None else total)
    return end-start >= shot['duration']-.05


def covered(window, shot):
    """Seconds of a shot a camera actually has the car for."""
    if window is None:
        return 0.
    first, last = window
    last = shot['start']+shot['duration'] if last is None else last
    return max(0., min(shot['start']+shot['duration'], last)-max(shot['start'], first))


def clamp(shot, window, total):
    """Slide a shot into a camera's window, shortening it only if it will not fit."""
    shot = dict(shot)
    if window is None:
        return shot
    first, last = window
    last = total if last is None else min(last, total)
    start = max(shot['start'], first)
    duration = min(shot['duration'], last-start)
    if duration < .9:                   # Nowhere to put it; leave the shot alone.
        return shot
    shot['start'], shot['duration'] = round(start, 2), round(duration, 2)
    return shot


def pick(library, scenario, kinds, outcome, count):
    """Deterministic spread across the available takes rather than the first few."""
    available = [t for t in library.find(scenario=scenario, outcome=outcome)
                 if kinds is None or t.get('metrics', {}).get('kind') in kinds]
    if not available or count <= 0:
        return []
    if len(available) <= count:
        return available
    step = len(available)/count
    return [available[min(len(available)-1, int(i*step))] for i in range(count)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--target', type=float, default=180.)
    parser.add_argument('--successes', type=int, default=1,
                        help='Most successful takes a section may draw on. One is the '
                             'default because a behaviour only has to be shown working '
                             'once; the interesting footage is everything else.')
    parser.add_argument('--failures', type=int, default=8,
                        help='Most failed takes a section may draw on')
    parser.add_argument('--per-take', type=float, default=12.,
                        help='Screen time one take may occupy, in seconds')
    parser.add_argument('--title', default='A fly drives a car')
    parser.add_argument('--no-sponsors', action='store_true',
                        help='Cut the plain CARLA renders instead of the sponsored ones. '
                             'Both are kept beside every take, so this costs a re-encode '
                             'rather than another recording.')
    parser.add_argument('--captions', action='store_true',
                        help='Burn the scenario title and outcome into the picture. Off by '
                             'default: burnt-in text cannot be removed later, and captions '
                             'are better added in an editor over a clean master.')
    args = parser.parse_args()

    library = ClipLibrary(args.library)
    present = [entry for entry in SECTIONS
               if pick(library, entry[0], entry[1], None, 1)]
    if not present:
        raise SystemExit(f'No takes in {args.library}')
    share = args.target/len(present)
    sections = []
    for name, kinds, title in present:
        wins = pick(library, name, kinds, 'success', args.successes)
        losses = pick(library, name, kinds, 'failure', args.failures)
        # Alternate, so a section is not three minutes of triumph followed by the
        # failures bolted on at the end.
        chosen = [t for pair in zip_longest(wins, losses) for t in pair if t is not None]
        if not chosen:
            continue
        shots, used = [], 0.
        for record in chosen:
            # Takes are added until the section has its share of the running time, so a
            # take that turns out to be short pulls the next one in rather than leaving
            # the film under length. Hand-tuned take counts cannot do that: a stopped
            # car yields three seconds and a clean overtake twenty.
            if used >= share-1.5:
                break
            budget = min(args.per_take, share-used)
            windows = in_frame(record['directory'])
            for camera, shot in place(record, beats(record, budget), windows):
                shots.append({'take': record['id'], 'camera': camera,
                              'start': shot['start'], 'duration': shot['duration'],
                              'label': record.get('label', ''),
                              'transition': 'fade' if shot['beat'] == 'approach' else 'cut'})
                used += shot['duration']
        sections.append({'title': title, 'scenario': name,
                         'kinds': list(kinds) if kinds else None, 'shots': shots})

    total = round(sum(s['duration'] for section in sections for s in section['shots']), 2)
    plan = {'title': args.title, 'target_seconds': args.target, 'fps': 20,
            'resolution': [1920, 1080], 'captions': args.captions, 'caption_seconds': 2.6,
            'sponsored': not args.no_sponsors,
            'fade_seconds': .3, 'filename': 'flyhard-behaviours.mp4', 'sections': sections,
            'generated_total_seconds': total,
            'note': 'Generated from the clip library; edit this file and re-run '
                    'assemble_film.py to re-cut without touching CARLA.'}
    Path(args.out).write_text(json.dumps(plan, indent=2)+'\n')
    print(json.dumps({'plan': args.out, 'sections': [(s['title'], len(s['shots']))
                                                     for s in sections],
                      'total_seconds': total, 'target_seconds': args.target}, indent=2))


if __name__ == '__main__':
    main()
