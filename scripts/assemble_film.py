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
# Resolved against the repository, not the working directory: the film is assembled
# from wherever the clip library happens to live, which is not the checkout.
FONT = str(Path(__file__).resolve().parents[1]/'assets'/'fonts'/'Geist.ttf')


def has_drawtext():
    """Whether this ffmpeg can burn text itself. Homebrew's build often cannot."""
    probe = subprocess.run(['ffmpeg', '-hide_banner', '-filters'], capture_output=True, text=True)
    return any(line.split()[1:2] == ['drawtext'] for line in probe.stdout.splitlines()
               if len(line.split()) > 1)


def escape(text):
    """ffmpeg drawtext takes its text through two levels of parsing."""
    return (str(text).replace('\\', r'\\\\').replace(':', r'\:')
            .replace("'", r"\'").replace('%', r'\%'))


def caption_image(plan, shot, width, height, path):
    """Draw a shot's captions to a transparent PNG.

    Text is drawn here rather than by ffmpeg because drawtext needs a build with
    libfreetype and plenty do not have one; overlay is in every build. The layout is
    the same either way, and what it says still comes only from the take's own metrics.
    """
    from PIL import Image, ImageDraw, ImageFont
    scale = height/1080
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = plan.get('font', FONT)
    def face(size):
        return ImageFont.truetype(font, max(int(size*scale), 8))
    if shot['first_of_section']:
        draw.rectangle([0, int(height*.36), width, int(height*.53)], fill=(0, 0, 0, 158))
        title = shot['section'].upper()
        large = face(58)
        draw.text(((width-draw.textlength(title, font=large))/2, int(height*.40)), title,
                  font=large, fill=(255, 255, 255, 255))
    if shot.get('label'):
        small = face(34)
        text = shot['label']
        pad = int(14*scale)
        x, y = int(52*scale), height-int(58*scale)-small.size-2*pad
        box = draw.textlength(text, font=small)
        draw.rectangle([x-pad, y-pad, x+box+pad, y+small.size+pad], fill=(0, 0, 0, 140))
        draw.text((x, y), text, font=small, fill=(255, 255, 255, 255))
    badge = 'SUCCESS' if shot['outcome'] == 'success' else 'FAILURE'
    colour = (124, 224, 124, 255) if shot['outcome'] == 'success' else (255, 122, 107, 255)
    medium = face(30)
    pad = int(12*scale)
    box = draw.textlength(badge, font=medium)
    x, y = width-int(52*scale)-box, int(52*scale)
    draw.rectangle([x-pad, y-pad, x+box+pad, y+medium.size+pad], fill=(0, 0, 0, 140))
    draw.text((x, y), badge, font=medium, fill=colour)
    image.save(path)
    return path


def caption(chain, plan, shot, width, height):
    """Section title, shot label and outcome badge, burnt in over the start of a shot.

    Every caption states what the footage is; none of them adds anything the take's
    own recorded metrics do not already say.
    """
    font = plan.get('font', FONT)
    hold = float(plan.get('caption_seconds', 2.6))
    scale = height/1080
    if shot['first_of_section']:
        chain += (f",drawbox=x=0:y={int(height*.36)}:w={width}:h={int(height*.17)}:"
                  f"color=black@0.62:t=fill:enable='lt(t,{hold+.6})'")
        chain += (f",drawtext=fontfile={font}:text='{escape(shot['section'].upper())}':"
                  f"fontcolor=white:fontsize={int(58*scale)}:x=(w-text_w)/2:"
                  f"y={int(height*.40)}:enable='lt(t,{hold+.6})'")
    if shot.get('label'):
        chain += (f",drawtext=fontfile={font}:text='{escape(shot['label'])}':"
                  f"fontcolor=white:fontsize={int(34*scale)}:box=1:boxcolor=black@0.55:"
                  f"boxborderw={int(14*scale)}:x={int(52*scale)}:y=h-th-{int(58*scale)}:"
                  f"enable='lt(t,{hold})'")
    badge = 'SUCCESS' if shot['outcome'] == 'success' else 'FAILURE'
    colour = '0x7ce07c' if shot['outcome'] == 'success' else '0xff7a6b'
    chain += (f",drawtext=fontfile={font}:text='{badge}':fontcolor={colour}:"
              f"fontsize={int(30*scale)}:box=1:boxcolor=black@0.55:boxborderw={int(12*scale)}:"
              f"x=w-text_w-{int(52*scale)}:y={int(52*scale)}:enable='lt(t,{hold})'")
    return chain


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve(plan, library):
    """Expand the plan into a flat shot list with absolute sources and timeline offsets."""
    shots, offset = [], 0.
    for section in plan['sections']:
        for index, shot in enumerate(section['shots']):
            source, record = library.resolve(shot['take'], shot['camera'],
                                             sponsored=plan.get('sponsored', False))
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


def build_filters(shots, inputs, plan, overlays=None):
    """One trim per shot, concatenated in order. Fades are applied per shot, not cross-faded,
    so a shot's own frames are never blended with a different take's frames.

    `overlays` maps a shot index to the input index of its caption image; where it is
    given the captions arrive as pictures instead of through drawtext.
    """
    parts, labels = [], []
    fade = float(plan.get('fade_seconds', .25))
    hold = float(plan.get('caption_seconds', 2.6))
    width, height = plan.get('resolution', [1920, 1080])
    fit = plan.get('fit', 'native')
    overlays = overlays or {}
    for i, shot in enumerate(shots):
        stream = inputs[shot['source']]
        end = shot['start'] + shot['duration']
        # The cameras render 4:3 and the film is 16:9. `native` puts the recorded frame
        # in the canvas at its own size, which is the default because the alternatives
        # both damage it: filling the frame scales 1248x960 up by half and then throws
        # away a quarter of the height, and scaling to fit is the same upscale without
        # the crop. Neither adds detail. The bars beside a native frame are where the
        # flyhard films have always put the readout panels.
        if fit == 'native':
            # Never resample: crop what is bigger than the canvas, pad what is smaller.
            # A 1920x1440 capture becomes a 16:9 master by losing its top and bottom,
            # every remaining pixel the one CARLA drew.
            geometry = (f"crop='min(iw,{width})':'min(ih,{height})',"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2")
        elif fit == 'contain':
            geometry = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2")
        else:
            geometry = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height}")
        chain = (f"[{stream}:v]trim=start={shot['start']}:end={end},setpts=PTS-STARTPTS,"
                 f"{geometry},setsar=1")
        if plan.get('captions', True) and i not in overlays:
            chain = caption(chain, plan, shot, width, height)
        if i in overlays:
            parts.append(f"{chain}[base{i}]")
            # The caption holds a little longer on a section's first shot, which is the
            # one carrying the title card.
            shown = hold+(.6 if shot['first_of_section'] else 0.)
            parts.append(f"[{overlays[i]}:v]scale={width}:{height},setsar=1[cap{i}]")
            chain = (f"[base{i}][cap{i}]overlay=0:0:format=auto:"
                     f"enable='lt(t,{shown})'")
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
    width, height = plan.get('resolution', [1920, 1080])
    # Where ffmpeg cannot burn text itself, draw the captions to images and overlay
    # them. The result is the same and it does not depend on how ffmpeg was built.
    overlays, caption_files = {}, []
    if plan.get('captions', True) and not has_drawtext():
        captions = out/'captions'
        captions.mkdir()
        for i, shot in enumerate(shots):
            path = caption_image(plan, shot, width, height, captions/f'shot-{i:03d}.png')
            overlays[i] = len(ordered)+len(caption_files)
            caption_files.append(str(path))
    parts, video = build_filters(shots, inputs, plan, overlays)

    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y']
    for source in ordered:
        command += ['-i', source]
    for path in caption_files:
        command += ['-i', path]
    maps = ['-map', video]
    music = plan.get('music')
    if music:
        if sha(music['file']) != music['sha256']:
            raise SystemExit('Music file does not match its recorded checksum')
        command += ['-i', music['file']]
        index = len(ordered)+len(caption_files)
        parts.append(f"[{index}:a]atrim=start={music.get('start_seconds', 0)}:duration={total},"
                     f"asetpts=PTS-STARTPTS,loudnorm=I=-17:TP=-1.5:LRA=11,"
                     f"afade=t=in:d=0.1,afade=t=out:st={max(total-1.5, 0)}:d=1.5[a]")
        maps += ['-map', '[a]']

    filter_file = out / 'filters.txt'
    filter_file.write_text(';\n'.join(parts))
    output = out / plan.get('filename', 'film.mp4')
    command += ['-filter_complex_script', str(filter_file), *maps,
                # The takes are already compressed, so the cut is a second generation.
                # veryfast at crf 18 halved their bitrate and showed it; these are the
                # settings the flyhard films are mastered with.
                '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
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
               'captions': bool(plan.get('captions', True)),
               'caption_method': 'overlaid images' if overlays else 'ffmpeg drawtext',
               'claim': 'Montage of separately recorded takes. Every shot is real recorded footage '
                        'selected by identifier from the clip library; no frames are synthesised, '
                        'retimed or blended between takes. Failures are shown as failures, and '
                        'every burnt-in caption restates what that take\'s own metrics record.'}
    (out / 'edit-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'timeline': timeline}, indent=2))


if __name__ == '__main__':
    main()
