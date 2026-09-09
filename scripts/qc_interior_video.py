#!/usr/bin/env python3
"""Stream-decode both cabin videos and verify dimensions, motion and hashes."""
import argparse
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',default='runs/interior-replay-v1')
    root = Path(parser.parse_args().run)
    expected = json.loads((root/'render-metrics.json').read_text()); results = {}
    for name,digest in expected['videos'].items():
        path = root/f'{name}.mp4'; reader = imageio.get_reader(path)
        meta = reader.get_meta_data()
        assert meta['fps'] == expected['fps']
        assert list(meta['size']) == [expected['width'],expected['height']]
        count,changed,total_change,previous = 0,0,0.,None
        for frame in reader:
            assert frame.shape == (expected['height'],expected['width'],3)
            sample = frame[64::4,::4].astype(np.int16)
            assert sample.std() > 1, 'Blank frame'
            if previous is not None:
                change = float(np.abs(sample-previous).mean())
                total_change += change; changed += change > .02
            previous = sample; count += 1
        reader.close()
        assert count == expected['frames'] and changed >= .9*(count-1)
        with path.open('rb') as stream:actual = hashlib.file_digest(stream,'sha256').hexdigest()
        assert actual == digest
        results[name] = {'status':'passed','frames_decoded':count,'width':expected['width'],
            'height':expected['height'],'fps':meta['fps'],'duration_s':count/meta['fps'],
            'changed_frame_pairs':changed,'mean_pixel_change':total_change/(count-1),
            'sha256':actual,'bytes':path.stat().st_size}
    (root/'local-video-qc.json').write_text(json.dumps(results,indent=2)); print(json.dumps(results,indent=2))


if __name__ == '__main__':main()
