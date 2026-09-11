#!/usr/bin/env python3
"""Check the exported clip and its synchronized native indicator evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import imageio.v2 as imageio
import numpy as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--run', required=True)
a = p.parse_args(); root = Path(a.run)
r = json.loads((root/'render-receipt.json').read_text())
v = root/'flyhard-smooth-60fps.mp4'
probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(v)]))['streams'][0]
assert (probe['width'],probe['height'],probe['avg_frame_rate'],int(probe['nb_frames'])) == (1920,1080,'60/1',1500)
assert float(probe['duration']) == 25
assert r['frames'] == 1500 and r['native_motion_frames'] == 1380
assert hashlib.sha256(v.read_bytes()).hexdigest() == r['video_sha256']
rows = r['frame_map']
assert len(rows) == 1380
assert np.all(np.diff([x['source_index'] for x in rows]) > 0)
assert all(x['neural_index'] == int(x['source_index']) for x in rows)
assert max(x['position_error_m'] for x in rows) < .12
assert all(x['sponsor_pixels'] > 0 for x in rows if x['camera'] in ['rear_left','rear_wide'])
with np.load(root/'rendered-body.npz') as b:
    movement = np.max(np.abs(np.diff(b['qpos'],axis=0)),axis=1)
assert np.all(movement > 0)
active = [x for x in rows if x['native_light_bits'] & 16]
assert active and all(x['signal'] == 'RIGHT' for x in active)
on, off = active[0]['output_frame'], active[-1]['output_frame']+1
assert all(x['native_light_bits'] == 0 for x in rows[:on]+rows[off:])
# CARLA switches the signal after the physical stalk crosses its threshold.
assert rows[on]['stalk_angle'] >= .18
assert rows[off]['stalk_angle'] < .18
lamp = [x for x in active if x['camera'] == 'rear_lamp']
bright = [x for x in lamp if x['lamp_bright_pixels'] > 2000]
dark = [x for x in lamp if x['lamp_bright_pixels'] < 200]
assert len(bright) > 30 and len(dark) > 30, 'Lamp did not visibly cycle'
# Exclude the short temporal anti-aliasing decay directly after cancellation.
off_lamp = [x for x in rows if x['camera'] == 'rear_lamp' and (x['output_frame'] < on or x['output_frame'] > off+15)]
assert max(x['lamp_bright_pixels'] for x in off_lamp) < 200
flashes = []
for previous, current in zip(rows, rows[1:]):
    if previous['camera'] == current['camera'] == 'rear_lamp' and current['signal'] == 'RIGHT':
        if previous['lamp_bright_pixels'] <= 2000 < current['lamp_bright_pixels']:
            flashes.append(current['output_time'])
assert len(flashes) >= 3, flashes
count = 0; duplicate_road = []; duplicate_body = []; previous = None
with imageio.get_reader(v) as reader:
    for frame in reader:
        if previous is not None and count < 1380:
            if np.array_equal(frame[64:1024,24:1272],previous[64:1024,24:1272]): duplicate_road.append(count)
            if np.array_equal(frame[584:1024,1296:1896],previous[584:1024,1296:1896]): duplicate_body.append(count)
        count += 1; previous = frame
assert count == 1500
assert not duplicate_road and not duplicate_body, (duplicate_road,duplicate_body)
result = {'status':'verified','full_decode':'passed','width':1920,'height':1080,'fps':60,'frames':count,'duration_seconds':25,
    'native_motion_frames':1380,'repeated_adjacent_road_frames':0,'repeated_adjacent_body_frames':0,
    'maximum_native_position_error_m':r['maximum_position_error_m'],
    'signal_on_output_seconds':on/60,'signal_off_output_seconds':off/60,
    'physical_stalk_at_signal_on_radians':rows[on]['stalk_angle'],'physical_stalk_at_signal_off_radians':rows[off]['stalk_angle'],
    'lamp_bright_frames_while_signalling':len(bright),'lamp_dark_frames_while_signalling':len(dark),
    'visible_native_flash_onsets_seconds':flashes,'lamp_dark_before_and_after_signal':True,
    'neural_states_are_held_original_samples':True,'livery_revision':r['sponsor_revision'],'livery_layout':r['sponsor_layout'],
    'sponsor_count':r['sponsor_count'],'video_sha256':r['video_sha256']}
(root/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
