#!/usr/bin/env python3
"""Assemble a multi-scenario film from the clip library using a declarative plan.

The plan names takes by identifier, never by path. Re-cutting the film is a plan
edit followed by another run of this script; no CARLA run or capture is repeated.
Use --dry-run to print the resolved timeline and check pacing before rendering.
"""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

from flyhard.clips import ClipLibrary

TRANSITIONS = ('cut', 'fade')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve(plan, library):
    """Expand the plan into a flat shot list with absolute sources and timeline offsets."""
    shots, offset = [], 0.
    for section in plan['sections']:
        for index, shot in enumerate(section['shots']):
            source, record = library.resolve(shot['take'], shot['camera'])
            start = float(shot.get('start', 0.))
            duration = float(shot['duration'])
            if duration <= 0:
                raise ValueError(f'Shot {shot["take"]}/{shot["camera"]} has non-positive duration')
            available = record['duration_seconds'] - start
            if duration > available + 1e-6:
                raise ValueError(
                    f'Shot {shot["take"]}/{shot["camera"]} wants {duration:.2f}s from {start:.2f}s '
                    f'but the take only has {available:.2f}s left')
            transition = shot.get('transition', 'cut')
            if transition not in TRANSITIONS:
                raise ValueError(f'Unknown transition {transition!r}; expected one of {TRANSITIONS}')
            shots.append({'section': section['title'], 'scenario': section['scenario'],
                          'take': shot['take'], 'camera': shot['camera'], 'outcome': record['outcome'],
                          'label': shot.get('label', record.get('label', '')),
                          'source': str(source), 'start': start, 'duration': duration,
                          'transition': transition, 'timeline_start': round(offset, 3),
                          'first_of_section': index == 0})
            offset += duration
    return shots, round(offset, 3)


def build_filters(shots, inputs, plan):
    """One trim per shot, concatenated in order. Fades are applied per shot, not cross-faded,
    so a shot's own frames are never blended with a different take's frames."""
    parts, labels = [], []
    fade = float(plan.get('fade_seconds', .25))
    width, height = plan.get('resolution', [1920, 1080])
    for i, shot in enumerate(shots):
        stream = inputs[shot['source']]
        end = shot['start'] + shot['duration']
        chain = (f"[{stream}:v]trim=start={shot['start']}:end={end},setpts=PTS-STARTPTS,"
                 f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1")
        if shot['transition'] == 'fade':
            chain += f",fade=t=in:st=0:d={fade}"
        parts.append(f"{chain}[v{i}]")
        labels.append(f'[v{i}]')
    parts.append(''.join(labels) + f'concat=n={len(shots)}:v=1:a=0[joined]')
    return parts, '[joined]'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--library', required=True, help='Clip library root')
    parser.add_argument('--out', required=True)
    parser.add_argument('--dry-run', action='store_true', help='Print the timeline without rendering')
    parser.add_argument('--tolerance', type=float, default=5.,
                        help='Permitted deviation from the plan target duration, in seconds')
    args = parser.parse_args()

    plan = json.loads(Path(args.plan).read_text())
    library = ClipLibrary(args.library)
    shots, total = resolve(plan, library)

    target = float(plan.get('target_seconds', 0))
    timeline = {'title': plan.get('title', ''), 'shot_count': len(shots), 'total_seconds': total,
                'target_seconds': target,
                'by_scenario': {}, 'by_outcome': {'success': 0., 'failure': 0.}}
    for shot in shots:
        timeline['by_scenario'][shot['scenario']] = round(
            timeline['by_scenario'].get(shot['scenario'], 0.) + shot['duration'], 3)
        timeline['by_outcome'][shot['outcome']] = round(
            timeline['by_outcome'][shot['outcome']] + shot['duration'], 3)

    if args.dry_run:
        print(json.dumps({'timeline': timeline, 'shots': shots}, indent=2))
        return

    if target and abs(total-target) > args.tolerance:
        raise SystemExit(f'Timeline is {total:.1f}s but the plan targets {target:.1f}s '
                         f'(tolerance {args.tolerance:.1f}s). Adjust the plan and re-run.')

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    ordered = list(dict.fromkeys(shot['source'] for shot in shots))
    inputs = {source: i for i, source in enumerate(ordered)}
    parts, video = build_filters(shots, inputs, plan)

    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y']
    for source in ordered:
        command += ['-i', source]
    maps = ['-map', video]
    music = plan.get('music')
    if music:
        if sha(music['file']) != music['sha256']:
            raise SystemExit('Music file does not match its recorded checksum')
        command += ['-i', music['file']]
        index = len(ordered)
        parts.append(f"[{index}:a]atrim=start={music.get('start_seconds', 0)}:duration={total},"
                     f"asetpts=PTS-STARTPTS,loudnorm=I=-17:TP=-1.5:LRA=11,"
                     f"afade=t=in:d=0.1,afade=t=out:st={max(total-1.5, 0)}:d=1.5[a]")
        maps += ['-map', '[a]']

    filter_file = out / 'filters.txt'
    filter_file.write_text(';\n'.join(parts))
    output = out / plan.get('filename', 'film.mp4')
    command += ['-filter_complex_script', str(filter_file), *maps,
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                '-r', str(plan.get('fps', 60)), '-fps_mode', 'cfr', '-threads', '8']
    if music:
        command += ['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2']
    command += ['-movflags', '+faststart', str(output)]
    subprocess.run(command, check=True)

    receipt = {'output': str(output), 'sha256': sha(output), 'timeline': timeline, 'shots': shots,
               'plan_sha256': sha(args.plan), 'assembler_sha256': sha(__file__),
               'library_root': str(library.root),
               'edit_environment': {'os': platform.system(), 'architecture': platform.machine(),
                                    'ffmpeg': shutil.which('ffmpeg')},
               'claim': 'Montage of separately recorded takes. Every shot is real recorded footage '
                        'selected by identifier from the clip library; no frames are synthesised, '
                        'retimed or blended between takes. Failures are shown as failures.'}
    (out / 'edit-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'timeline': timeline}, indent=2))


if __name__ == '__main__':
    main()
