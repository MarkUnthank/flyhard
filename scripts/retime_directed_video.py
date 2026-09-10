#!/usr/bin/env python3
"""Retime a synchronized composite without separating its neural/body/car clock."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from flyhard.live_livery import verify_live_livery


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--asset', type=Path, required=True, help='Fresh live sponsor export')
    parser.add_argument('--source-receipt', type=Path, required=True, help='Receipt proving the source video uses the same livery')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--encoder', choices=['h264_nvenc', 'libx264'], default='h264_nvenc')
    args = parser.parse_args()
    manifest = verify_live_livery(args.asset, args.output.parent)
    source_receipt = json.loads(args.source_receipt.read_text())
    if (source_receipt['sponsor_revision'], source_receipt['sponsor_layout']) != (manifest['revision'], manifest['layoutVersion']):
        raise RuntimeError('Source video contains stale sponsors: render from the 3D episode with the fresh livery')
    if source_receipt['video_sha256'] != sha(args.input):
        raise RuntimeError('Source receipt belongs to a different video')
    plan = json.loads(args.plan.read_text())
    assert sha(args.input) == plan['source_sha256'], 'Edit plan belongs to another source video'
    assert args.input.resolve() != args.output.resolve()
    assert not args.output.exists(), 'Preserve existing renders; use a new output name'
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(args.input)]))
    assert len(probe['streams']) == 1 and probe['streams'][0]['codec_type'] == 'video', 'This edit expects a silent master'
    stream = probe['streams'][0]
    width, height = stream['width'], stream['height']
    fps = plan['fps']
    assert (width, height) == (1920, 1080)
    assert stream['avg_frame_rate'] == f'{fps}/1'
    assert int(stream['nb_frames']) == plan['source_frames']
    timeline = []; cuts = []; expected_start = 0
    for shot in plan['shots']:
        start, end = shot['source_start'], shot['source_end']
        count = shot['output_frames']
        assert start == expected_start and end > start and count >= end - start
        speed = (end - start) / count
        assert speed == 1 or shot['slow_motion'], 'Slow footage must be visibly labelled'
        cuts.append({**shot, 'start_seconds': len(timeline) / fps, 'duration_seconds': count / fps, 'playback_speed': speed})
        timeline.extend({'source_frame': start + i * (end - start) // count,
                         'shot': shot['name'], 'slow_motion': shot['slow_motion']} for i in range(count))
        expected_start = end
    assert expected_start == plan['source_frames']
    assert len(timeline) == plan['output_frames']
    repeats = Counter(row['source_frame'] for row in timeline)
    labels = {row['source_frame']: row['slow_motion'] for row in timeline}
    assert len(repeats) == plan['source_frames'], 'Every original frame must be retained'
    font = ImageFont.truetype(str(Path(__file__).resolve().parents[1] / 'assets/fonts/Geist.ttf'), 22)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'rawvideo',
               '-pixel_format', 'rgb24', '-video_size', f'{width}x{height}', '-framerate', str(fps),
               '-i', 'pipe:0', '-an', '-c:v', args.encoder]
    if args.encoder == 'h264_nvenc':
        command += ['-preset', 'p5', '-rc', 'vbr', '-cq', '18', '-b:v', '0']
    else:
        command += ['-preset', 'fast', '-crf', '17', '-threads', '4']
    command += ['-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-metadata',
                f"comment=Retimed synchronized CARLA/fly/CNS replay. Slow motion labelled. Sponsor livery r{manifest['revision']} layout{manifest['layoutVersion']}. Vehicle: CARLA 0.9.16, CVC, Universitat Autonoma de Barcelona.", str(args.output)]
    started = time.perf_counter()
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    emitted = 0
    try:
        with imageio.get_reader(args.input) as reader:
            for index in range(plan['source_frames']):
                frame = reader.get_next_data()
                if labels[index]:
                    canvas = Image.fromarray(frame)
                    ImageDraw.Draw(canvas).text((990, 38), 'SLOW MOTION', font=font, anchor='rm', fill='#aaa')
                    frame = np.asarray(canvas)
                pixels = frame.tobytes()
                for _ in range(repeats[index]):
                    process.stdin.write(pixels)
                    emitted += 1
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('Video encoder failed')
    except BaseException:
        process.kill(); process.wait()
        raise
    assert emitted == plan['output_frames']
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(args.output), '-f', 'null', '-'], check=True, stdin=subprocess.DEVNULL)
    output_probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(args.output)]))['streams'][0]
    assert int(output_probe['nb_frames']) == emitted
    assert abs(float(output_probe['duration']) - emitted / fps) < 1e-6
    receipt = {'status': 'verified', 'duration_seconds': emitted / fps, 'frames': emitted,
               'fps': fps, 'width': width, 'height': height, 'encoder': args.encoder,
               'source_sha256': sha(args.input), 'plan_sha256': sha(args.plan),
               'script_sha256': sha(__file__), 'video_sha256': sha(args.output),
               'cuts': cuts, 'frame_map': timeline, 'full_decode': 'passed',
               'interpolated_frames': False, 'all_panels_share_source_frame': True,
               'sponsor_revision': manifest['revision'], 'sponsor_layout': manifest['layoutVersion'],
               'wall_seconds': time.perf_counter() - started}
    args.output.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'frame_map'}, indent=2))


if __name__ == '__main__':
    main()
