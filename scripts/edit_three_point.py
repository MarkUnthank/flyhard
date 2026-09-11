#!/usr/bin/env python3
"""Edit recorded checkpoint footage from an explicit, auditable shot list."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from flyhard.live_livery import verify_live_livery


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--encoder', choices=['libx264', 'h264_nvenc'], default='libx264')
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    manifest = verify_live_livery(args.asset, out)
    sources = plan['sources']
    receipts = {}
    for key, filename in sources.items():
        receipt = json.loads((Path(filename).parent / 'render-receipt.json').read_text())
        assert sha(filename) == receipt['video_sha256'], filename
        assert (receipt['sponsor_revision'], receipt['sponsor_layout']) == (
            manifest['revision'], manifest['layoutVersion']), 'Refresh sponsor composition first'
        receipts[key] = receipt
    successful = receipts[plan['success']]
    assert successful['actual_result']['success']
    assert successful['playback_rate'] == 1 and successful['source_start_seconds'] == 0
    assert abs(successful['duration'] - successful['actual_result']['time_seconds']) < .06

    shots = plan['learning']
    learning_duration = sum(shot['duration'] for shot in shots)
    black = plan['black_seconds']
    hold = plan['final_hold_seconds']
    reveal = learning_duration + black
    success_duration = successful['duration']
    duration = reveal + success_duration + hold
    assert abs(duration - plan['duration_seconds']) < 1 / 60
    font_path = 'assets/fonts/Geist.ttf'
    card = Image.new('RGBA', (600, 440), (0, 0, 0, 255))
    draw = ImageDraw.Draw(card)
    font = ImageFont.truetype(font_path, 22)
    music = plan['music']
    assert sha(music['file']) == music['sha256']
    credits = ['CARLA 0.9.16 · CVC / UAB', 'MaleCNS · Janelia',
               'NeuroMechFly / FlyGym · EPFL', music['credit_title'], music['credit_recording'],
               f"Livery r{manifest['revision']} · layout {manifest['layoutVersion']}",
               'Recorded poses replayed at 60 fps', 'Sponsor surfaces composited']
    for line, text in enumerate(credits):
        draw.text((14, 22 + 49 * line), text, font=font, fill='#bbb')
    card.save(out / 'credits.png')

    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-filter_complex_threads', '3']
    filters = []
    timeline = []
    elapsed = 0.
    for i, shot in enumerate(shots):
        receipt = receipts[shot['source']]
        assert 0 <= shot['start'] < shot['end'] <= receipt['duration'] + 1e-6
        assert shot['duration'] > 0
        rate = (shot['end'] - shot['start']) / shot['duration']
        simulation_rate = rate * receipt['playback_rate']
        command += ['-threads', '1', '-i', sources[shot['source']]]
        filters.append(f'[{i}:v]trim=start={shot["start"]}:end={shot["end"]},'
                       f'setpts=(PTS-STARTPTS)/{rate},fps=60,tpad=stop_mode=clone:stop_duration=0.05,'
                       f'trim=duration={shot["duration"]},setsar=1[trim{i}]')
        zoom = shot.get('zoom', 1.)
        assert 1 <= zoom <= 1.3
        if zoom > 1:
            width = 2 * round(1248 / zoom / 2)
            height = 2 * round(960 / zoom / 2)
            # Keep original burned-in gear/speed and stage labels outside the
            # enlarged road crop; paste their untouched HUD regions back below.
            assert height <= 964 - 145
            x, y = 24 + (1248-width)//2, 145 + (964-145-height)//2
            filters += [f'[trim{i}]split=4[base{i}][road{i}][gear{i}][speed{i}]',
                        f'[road{i}]crop={width}:{height}:{x}:{y},scale=1248:960[close{i}]',
                        f'[base{i}][close{i}]overlay=24:64[zoom{i}]',
                        f'[gear{i}]crop=224:52:48:86[g{i}]',
                        f'[zoom{i}][g{i}]overlay=48:86[withgear{i}]',
                        f'[speed{i}]crop=238:52:1026:80[s{i}]',
                        f'[withgear{i}][s{i}]overlay=1026:80[view{i}]']
        else:
            filters.append(f'[trim{i}]null[view{i}]')
        label = out / f'label-{i}.txt'
        label.write_text(f'{shot["stage"]} · {simulation_rate:.1f}×')
        # Replace the old baked playback-rate label while retaining measured controls.
        filters.append(f'[view{i}]drawbox=x=24:y=964:w=1248:h=60:color=black:t=fill,'
                       f'drawtext=fontfile={font_path}:textfile={label}:fontcolor=white:'
                       f'fontsize=22:x=48:y=980[shot{i}]')
        timeline.append({**shot, 'edit_start': elapsed, 'edit_end': elapsed + shot['duration'],
                         'simulation_playback_rate': simulation_rate,
                         'source_sha256': receipt['video_sha256']})
        elapsed += shot['duration']
    success_index, music_index, card_index = len(shots), len(shots)+1, len(shots)+2
    command += ['-threads', '1', '-i', sources[plan['success']], '-i', music['file'],
                '-loop', '1', '-framerate', '60', '-i', str(out / 'credits.png')]
    filters += [''.join(f'[shot{i}]' for i in range(len(shots))) +
                f'concat=n={len(shots)}:v=1:a=0,fade=t=out:st={learning_duration-.45}:d=0.45[learning]',
                f'color=black:s=1920x1080:r=60:d={black}[black]',
                f'[{success_index}:v]setpts=PTS-STARTPTS,setsar=1,fade=t=in:st=0:d=0.45,'
                f'tpad=stop_mode=clone:stop_duration={hold}[success]',
                '[learning][black][success]concat=n=3:v=1:a=0[cut]',
                f"[cut][{card_index}:v]overlay=1296:584:enable='gte(t,{reveal+success_duration})'[v]",
                f'[{music_index}:a]asplit=2[opening][return]',
                f'[opening]atrim=start={music["start_seconds"]}:duration={learning_duration},'
                f'asetpts=PTS-STARTPTS,afade=t=in:d=0.06,afade=t=out:st={learning_duration-.55}:d=0.55[a1]',
                f'anullsrc=r=48000:cl=stereo:d={black}[silence]',
                f'[return]atrim=start={music["reveal_start_seconds"]}:duration={success_duration+hold},'
                f'asetpts=PTS-STARTPTS,afade=t=in:d=0.12,'
                f'afade=t=out:st={success_duration+hold-.6}:d=0.6[a2]',
                '[a1][silence][a2]concat=n=3:v=0:a=1,loudnorm=I=-17:TP=-1.5:LRA=11[a]']
    filter_file = out / 'filters.txt'
    filter_file.write_text(';\n'.join(filters))
    output = out / plan['filename']
    command += ['-filter_complex_script', str(filter_file), '-map', '[v]', '-map', '[a]',
                '-r', '60', '-fps_mode', 'cfr', '-c:v', args.encoder]
    if args.encoder == 'h264_nvenc':
        command += ['-preset', 'p6', '-rc', 'vbr', '-cq', '19', '-b:v', '0']
    else:
        command += ['-preset', 'veryfast', '-crf', '18', '-threads', '6']
    command += ['-profile:v', 'high', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                '-ar', '48000', '-ac', '2', '-t', str(duration), '-movflags', '+faststart', str(output)]
    subprocess.run(command, check=True)
    receipt = {'output': str(output), 'sha256': sha(output), 'duration_seconds': duration,
               'fps': 60, 'encoder': args.encoder, 'learning_seconds': learning_duration,
               'black_seconds': black, 'successful_reveal_start': reveal,
               'success_playback': 'Complete successful take at real-time speed, then a final still hold.',
               'success_result': successful['actual_result'], 'timeline': timeline,
               'sources': {key: {'file': sources[key], 'sha256': r['video_sha256'],
                                'actual_result': r['actual_result']} for key, r in receipts.items()},
               'artwork': {'revision': manifest['revision'], 'layout': manifest['layoutVersion']},
               'music': music, 'plan_sha256': sha(args.plan), 'editor_sha256': sha(__file__),
               'claim': 'Earlier and intermediate checkpoint footage cut chronologically within each '
                        'trial. Six edit beats are not six training attempts. The intermediate '
                        'checkpoint also passed its complete trial; its finish is withheld here. '
                        'The final pre-blackout beat teases the selected successful take before '
                        'its stop; that same take is then shown in full after the blackout. '
                        'No invented mistakes, extra training or changed controller actions. '
                        'Only edit timing and modest road-view crops change.'}
    (out / 'edit-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
