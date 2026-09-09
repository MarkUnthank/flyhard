#!/usr/bin/env python3
"""Export a continuous prefix of the composite without changing playback speed."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--end-frame', type=int, required=True)
    args = parser.parse_args()
    root = Path(args.run)
    source = root / 'flyhard-16x9.mp4'
    metrics = json.loads((root / 'render-metrics.json').read_text())
    assert sha(source) == metrics['video_sha256']
    assert 0 < args.end_frame <= metrics['frames']
    output = root / 'social-16x9.mp4'
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
               '-y', '-i', str(source), '-frames:v', str(args.end_frame), '-an',
               '-c:v', 'libx264', '-crf', '17', '-preset', 'slow',
               '-movflags', '+faststart', str(output)]
    subprocess.run(command, check=True)
    result = {'status': 'exported', 'source_video_sha256': metrics['video_sha256'],
              'video_sha256': sha(output), 'source_frame_range': [0, args.end_frame],
              'frame_range_convention': 'Start inclusive, end exclusive',
              'width': metrics['width'], 'height': metrics['height'],
              'fps': metrics['fps'], 'frames': args.end_frame,
              'duration_s': args.end_frame / metrics['fps'], 'playback_speed': 1.0,
              'edit': 'Continuous prefix of the complete composite; stationary tail removed after the crash. No panels retimed or replaced.',
              'source_render_metrics_sha256': sha(root / 'render-metrics.json'),
              'export_script_sha256': sha(Path(__file__))}
    (root / 'social-export.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
