#!/usr/bin/env python3
"""Build an edit plan from the clip library, cutting each take at its own events.

Shot boundaries come from the recorded trace, not from guesses: the approach ends
where the car first touches the brake, the decision runs from there to rest, and the
resume starts when it moves off again. Editing the film afterwards is a matter of
changing this plan, or the JSON it writes, and re-running the assembler.
"""
import argparse
import json
from pathlib import Path

from flyhard.clips import ClipLibrary

# One angle per beat, in the order the beats happen, so a scenario is seen from
# outside, from behind the car and from over the fly's own controls.
BEAT_CAMERAS = {'approach': 'wide', 'decision': 'chase', 'resume': 'cabin'}
SECTIONS = [
    ('crossing', 'Stopping for pedestrians'),
    ('junction', 'Giving way at a junction'),
    ('overtake', 'Overtaking on the highway'),
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
    return {'total': total, 'first_brake': first_brake, 'stopped': stopped,
            'resumed': resumed,
            'peak_speed_time': max(rows, key=lambda r: r['speed_m_s'])['time']}


# Per beat: how long it wants to be, and how long it may stretch to when a scenario
# has screen time to spare. Nothing is ever stretched past the take's own footage.
BEAT_LIMITS = {'approach': (2.6, 5.0), 'decision': (3.4, 8.0), 'resume': (2.0, 4.5)}


def beats(record, budget):
    """Split one take's screen time into beats, each anchored on a real moment."""
    marks = events(record['directory'], record['fps'])
    total = record['duration_seconds']
    if not marks:
        return [{'beat': 'decision', 'start': 0., 'duration': round(min(budget, total), 2)}]
    anchor = marks['first_brake'] or marks['peak_speed_time']
    shots = []
    if anchor > 2.4:
        # Run into the decision, not away from it: the seconds before the brake.
        shots.append({'beat': 'approach', 'start': max(0., anchor-BEAT_LIMITS['approach'][1])})
    shots.append({'beat': 'decision', 'start': max(0., anchor-.8)})
    if marks['resumed'] and total-marks['resumed'] > 1.2:
        shots.append({'beat': 'resume', 'start': max(0., marks['resumed']-.8)})

    for shot in shots:
        low, high = BEAT_LIMITS[shot['beat']]
        shot['low'], shot['high'] = low, min(high, total-shot['start'])
    shots = [s for s in shots if s['high'] >= .9]
    if not shots:
        return [{'beat': 'decision', 'start': 0., 'duration': round(min(budget, total), 2)}]
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


def pick(library, scenario, outcome, count):
    """Deterministic spread across the available takes rather than the first few."""
    available = library.find(scenario=scenario, outcome=outcome)
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
    parser.add_argument('--successes', type=int, default=3)
    parser.add_argument('--failures', type=int, default=2)
    parser.add_argument('--title', default='A fly drives a car')
    args = parser.parse_args()

    library = ClipLibrary(args.library)
    present = [(name, title) for name, title in SECTIONS if library.find(scenario=name)]
    if not present:
        raise SystemExit(f'No takes in {args.library}')
    share = args.target/len(present)
    sections = []
    for name, title in present:
        chosen = ([(t, 'success') for t in pick(library, name, 'success', args.successes)]
                  + [(t, 'failure') for t in pick(library, name, 'failure', args.failures)])
        if not chosen:
            continue
        budget = share/len(chosen)
        shots = []
        for record, _ in chosen:
            for shot in beats(record, budget):
                camera = BEAT_CAMERAS[shot['beat']]
                if camera not in record['cameras']:
                    camera = next(iter(record['cameras']))
                shots.append({'take': record['id'], 'camera': camera,
                              'start': shot['start'], 'duration': shot['duration'],
                              'label': record.get('label', ''),
                              'transition': 'fade' if shot['beat'] == 'approach' else 'cut'})
        sections.append({'title': title, 'scenario': name, 'shots': shots})

    total = round(sum(s['duration'] for section in sections for s in section['shots']), 2)
    plan = {'title': args.title, 'target_seconds': args.target, 'fps': 20,
            'resolution': [1920, 1080], 'captions': True, 'caption_seconds': 2.6,
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
