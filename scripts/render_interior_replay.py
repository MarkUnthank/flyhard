#!/usr/bin/env python3
"""Depth composite a synchronized fly replay into the native cabin camera."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from OpenGL import GL

from flyhard.cockpit import WheelRig
from flyhard.interior_view import InteriorFlyView


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',default='runs/interior-replay-v1')
    parser.add_argument('--anchor',type=float,nargs=3,default=[.27,-.41,1.03])
    parser.add_argument('--scale',type=float,default=.16)
    parser.add_argument('--start',type=float,default=2.)
    args = parser.parse_args()
    root = Path(args.run)
    config = json.loads((root/'config.json').read_text())
    capture = json.loads((root/'metrics.json').read_text())
    assert capture['status'] == 'complete'
    frames = json.loads((root/'frames.json').read_text())
    with np.load(root/'body-trace.npz') as archive:body = {k:archive[k] for k in archive.files}
    rig = WheelRig(support_hand=config['support_hand']); data = mj.MjData(rig.model)
    view = InteriorFlyView(rig,config['width'],config['height'],frames[0]['camera_car_matrix'],
        args.anchor,metres_per_rig_unit=args.scale,horizontal_fov=config['fov_horizontal'])
    device = GL.glGetString(GL.GL_RENDERER).decode()
    assert 'NVIDIA' in device, f'Remote GPU rendering required: {device}'
    font = ImageFont.truetype('assets/fonts/Geist.ttf',18)
    videos = {}
    for name in ['native-cabin','fly-shoulder-preview']:
        videos[name] = imageio.get_writer(root/f'{name}.mp4',fps=config['fps'],codec='libx264',
            quality=None,macro_block_size=1,ffmpeg_params=['-crf','16','-preset','slow','-movflags','+faststart'])
    start_index = round(args.start*config['fps'])
    samples, qpos_error,clock_error = [],0.,0.
    started = time.monotonic()
    try:
        for index in range(start_index,len(frames)):
            record = frames[index]; bi = record['body_index']
            assert record['frame'] == record['rgb_frame'] == record['depth_frame']
            assert int(body['decision_index'][bi]) == record['decision_index']
            rgb = np.asarray(Image.open(root/'rgb'/f'{index:04}.png'))
            packed = np.asarray(Image.open(root/'depth'/f'{index:04}.png'),dtype=np.float32)
            depth = (packed[:,:,0]+256*packed[:,:,1]+65536*packed[:,:,2])*(1000/(256**3-1))
            for key in ['qpos','qvel','ctrl']:getattr(data,key)[:] = body[key][bi]
            data.time = body['time'][bi]; mj.mj_forward(rig.model,data)
            qpos_error = max(qpos_error,float(np.max(np.abs(data.qpos-body['qpos'][bi]))))
            clock_error = max(clock_error,abs(data.time-record['camera_time']))
            view.camera_matrix = np.asarray(record['camera_car_matrix'])
            result,mask,_ = view.render(data,rgb,depth)
            assert mask.sum() > 5000, 'Fly not sufficiently visible'
            composite = Image.fromarray(result); draw = ImageDraw.Draw(composite)
            draw.rectangle((16,16,356,50),fill='#080808')
            draw.text((26,22),'Camera preview / composited fly',font=font,fill='#eeeeee')
            videos['native-cabin'].append_data(rgb)
            videos['fly-shoulder-preview'].append_data(np.asarray(composite))
            if index in {start_index,start_index+50,len(frames)-1}:
                composite.save(root/f'preview-{index:04}.png')
                Image.fromarray(rgb).save(root/f'native-{index:04}.png')
            samples.append({'output_index':index-start_index,'source_index':index,
                'carla_frame':record['frame'],'body_index':bi,'body_time':float(data.time),
                'decision_index':record['decision_index'],'visible_fly_and_wheel_pixels':int(mask.sum())})
            if index%25 == 0:print(json.dumps({'frame':index,'wall_seconds':time.monotonic()-started}),flush=True)
    finally:
        for video in videos.values():video.close()
        view.close()
    assert qpos_error == 0 and clock_error < 1e-4
    metrics = {'status':'rendered','native_camera':True,'native_fly':False,'gpu_renderer':device,
        'width':config['width'],'height':config['height'],'fps':config['fps'],'frames':len(samples),
        'duration_s':len(samples)/config['fps'],'playback_speed':1.,'source_start_s':args.start,
        'placement':{'wheel_anchor_car_m':args.anchor,'metres_per_rig_unit':args.scale,
            'display_wheel_diameter_m':2*rig.radius*args.scale},
        'max_pose_restore_error':qpos_error,'max_camera_body_clock_error_s':clock_error,
        'source_body_trace_sha256':sha(root/'body-trace.npz'),'frames_sha256':sha(root/'frames.json'),
        'script_sha256':sha(__file__),'view_sha256':sha('src/flyhard/interior_view.py'),
        'wall_seconds':time.monotonic()-started,
        'videos':{name:sha(root/f'{name}.mp4') for name in videos},'frame_map':samples,
        'limitations':['Fly is composited from MuJoCo, not an actor in CARLA.',
            'Camera and occlusion use CARLA RGB and depth; fly lighting comes from MuJoCo.',
            'Visual scale enlarges the fly approximately 160 times; body physics keep original units.',
            'Vehicle acceleration is not fed into the tethered body dynamics.',
            'Original learned actions are replayed; requested turns and vehicle speed remain scripted.']}
    (root/'render-metrics.json').write_text(json.dumps(metrics,indent=2))
    print(json.dumps({k:v for k,v in metrics.items() if k != 'frame_map'},indent=2),flush=True)


if __name__ == '__main__':main()
