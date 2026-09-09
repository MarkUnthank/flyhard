#!/usr/bin/env python3
"""Decode every delivered frame and check the synchronized composite format."""
import argparse
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--video', default='flyhard-16x9.mp4')
    parser.add_argument('--metrics', default='render-metrics.json')
    parser.add_argument('--output')
    args = parser.parse_args()
    root = Path(args.run)
    video = root / args.video
    expected = json.loads((root / args.metrics).read_text())
    reader = imageio.get_reader(video)
    metadata = reader.get_meta_data()
    assert metadata['fps'] == expected['fps'] == 25
    assert tuple(metadata['size']) == (1920, 1080)
    regions = {'carla': (24, 64, 1248, 960),
               'cns': (1296, 64, 600, 440),
               'fly': (1296, 584, 600, 440)}
    previous = {}
    changed = {name: 0 for name in regions}
    greatest_change = {name: 0.0 for name in regions}
    count = 0
    for frame in reader:
        assert frame.shape == (1080, 1920, 3)
        for name, (x, y, width, height) in regions.items():
            sample = frame[y:y+height:4, x:x+width:4].astype(np.int16)
            assert sample.std() > 1, f'Blank {name} panel at frame {count}'
            if name in previous:
                difference = float(np.abs(sample-previous[name]).mean())
                greatest_change[name] = max(greatest_change[name], difference)
                changed[name] += difference > 0.02
            previous[name] = sample
        count += 1
    reader.close()
    assert count == expected['frames']
    assert all(value > 50 for value in changed.values()), changed
    with video.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert digest == expected['video_sha256']
    result = {'status': 'passed', 'video_sha256': digest,
              'bytes': video.stat().st_size, 'frames_decoded': count,
              'width': 1920, 'height': 1080, 'fps': 25,
              'duration_s': count / 25, 'playback_speed': expected['playback_speed'],
              'changed_frame_pairs': changed, 'largest_mean_pixel_change': greatest_change,
              'scope': 'Full decode, dimensions, frame count, video hash, nonblank moving panels. Causal checks are in validation.json.'}
    output = Path(args.output) if args.output else root / 'local-video-qc.json'
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
