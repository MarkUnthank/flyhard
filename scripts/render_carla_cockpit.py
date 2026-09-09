#!/usr/bin/env python3
"""Minimal 16:9 video: CARLA, anatomical neural activity, physical fly."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import subprocess
import sys

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from flyhard.cockpit import WheelRig


WIDTH, HEIGHT = 1920,1080
CAR_X, CAR_Y, CAR_W, CAR_H = 24,64,1248,960
RIGHT_X, RIGHT_W = 1296,600
CNS_Y, CNS_H = 64,440
FLY_Y, FLY_H = 584,440


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',required=True)
    parser.add_argument('--geometry',default='data/cns-geometry-v1/geometry.npz')
    parser.add_argument('--preview-only',action='store_true')
    args = parser.parse_args()
    root = Path(args.run)
    config = json.loads((root/'config.json').read_text())
    capture = json.loads((root/'metrics.json').read_text())
    assert capture['status'] == 'capture_complete'
    frames = json.loads((root/'frames.json').read_text())
    with np.load(root/'body-trace.npz') as archive:
        body = {name:archive[name] for name in archive.files}
    with np.load(root/'neural-trace.npz') as archive:
        neural_time = archive['time']
    # VTK and MuJoCo manage EGL display lifetime differently. Give each its
    # own process, while keeping both layers indexed to the same saved frames.
    command=[sys.executable,'scripts/render_cns.py','--run',str(root),'--geometry',args.geometry]
    if args.preview_only:command.append('--preview-only')
    subprocess.run(command,check=True)
    cns_metrics=json.loads((root/('cns-preview-metrics.json' if args.preview_only else 'cns-render-metrics.json')).read_text())
    assert cns_metrics['frames_sha256'] == hashlib.sha256((root/'frames.json').read_bytes()).hexdigest()
    assert cns_metrics['neural_trace_sha256'] == hashlib.sha256((root/'neural-trace.npz').read_bytes()).hexdigest()
    cns_map={row['index']:row for row in cns_metrics['frame_map']}
    cns_reader=None if args.preview_only else imageio.get_reader(root/'cns-layer.mp4')
    font = {size:ImageFont.truetype('assets/fonts/Geist.ttf',size) for size in [18,24,28]}
    rig = WheelRig(support_hand=config['support_hand'])
    replay = mj.MjData(rig.model)
    renderer = mj.Renderer(rig.model,height=FLY_H,width=RIGHT_W)
    # Recolor only display geometry. The captured physical model is unchanged.
    rig.model.geom_rgba[rig.model.geom_bodyid == 0,:3] = 0.065
    for i in range(rig.model.ngeom):
        if rig.model.geom_bodyid[i] == rig.model.body('wheel').id:
            rig.model.geom_rgba[i,:3] = [0.34,0.34,0.34]
    camera = mj.MjvCamera()
    camera.lookat[:] = [0.2,0,1.1]
    camera.distance = 5.0
    camera.azimuth = 155
    camera.elevation = -20
    start = time.perf_counter()
    replay_error,clock_error = 0.0,0.0
    source = imageio.get_reader(root/'carla-camera.mp4')
    video_path = root/'flyhard-16x9.mp4'
    writer = None if args.preview_only else imageio.get_writer(video_path,fps=25,codec='libx264',
        quality=None,macro_block_size=1,ffmpeg_params=['-crf','17','-preset','slow','-movflags','+faststart'])
    wanted = {0,min(100,len(frames)-1),min(200,len(frames)-1),min(400,len(frames)-1),len(frames)-1}
    written = 0
    for index,car_image in enumerate(source):
        if args.preview_only and index not in wanted:
            continue
        record = frames[index]
        bi,ni = record['body_index'],record['neural_index']
        assert body['decision_index'][bi] == ni
        assert neural_time[ni] <= body['time'][bi]+1e-10
        clock_error = max(clock_error,abs(record['camera_time']-body['time'][bi]))
        assert cns_map[index]['neural_index'] == ni and cns_map[index]['body_time'] == record['body_time']
        neural_image = (np.asarray(Image.open(root/f'cns-preview-{index:04}.png'))
                        if args.preview_only else cns_reader.get_next_data())
        replay.qpos[:] = body['qpos'][bi]
        replay.qvel[:] = body['qvel'][bi]
        replay.ctrl[:] = body['ctrl'][bi]
        replay.time = body['time'][bi]
        replay.eq_active[rig.grip_id] = not config['disable_grip']
        if rig.support_grip_id is not None:
            replay.eq_active[rig.support_grip_id] = not config['disable_grip']
        mj.mj_forward(rig.model,replay)
        replay_error = max(replay_error,float(np.max(np.abs(replay.qpos-body['qpos'][bi]))))
        renderer.update_scene(replay,camera=camera)
        renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
        fly_image = renderer.render()
        assert car_image.shape == (CAR_H,CAR_W,3)
        canvas = Image.new('RGB',(WIDTH,HEIGHT),'black')
        canvas.paste(Image.fromarray(car_image),(CAR_X,CAR_Y))
        canvas.paste(Image.fromarray(neural_image),(RIGHT_X,CNS_Y))
        canvas.paste(Image.fromarray(fly_image),(RIGHT_X,FLY_Y))
        draw = ImageDraw.Draw(canvas)
        draw.text((CAR_X,24),'CARLA',font=font[24],fill='#eeeeee')
        draw.text((CAR_X+CAR_W,24),f'{record["speed_m_s"]*3.6:.0f} km/h',anchor='ra',font=font[28],fill='white')
        draw.text((RIGHT_X,24),'Neural activity',font=font[24],fill='#eeeeee')
        draw.text((RIGHT_X,544),'Fly',font=font[24],fill='#eeeeee')
        if writer is not None:
            writer.append_data(np.asarray(canvas))
        written += 1
        if index in wanted:
            canvas.save(root/f'preview-{index:04}.png')
        if index % 100 == 0:
            print(json.dumps({'frame':index,'wall_seconds':time.perf_counter()-start}),flush=True)
    source.close()
    if writer is not None:
        writer.close()
    renderer.close()
    if cns_reader is not None:cns_reader.close()
    assert replay_error == 0 and clock_error < 1e-4
    result = {'status':'previewed' if args.preview_only else 'rendered',
        'width':WIDTH,'height':HEIGHT,'fps':25,'frames':written,'duration_s':len(frames)/25,
        'playback_speed':1.0,'same_episode':True,'max_camera_body_clock_error_s':clock_error,
        'replay_max_qpos_error':replay_error,'model_rate_color_scale':cns_metrics['model_rate_color_scale'],
        'vtk_window':cns_metrics['vtk_window'],'gpu_capabilities':cns_metrics['gpu_capabilities'],
        'neural_display':'Actual MaleCNS skeletons and neuropil meshes. Fixed 512-neuron subset, colored by its recorded signed model states; no invented activation.',
        'geometry_sha256':hashlib.sha256(Path(args.geometry).read_bytes()).hexdigest(),
        'renderer_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cns_renderer_sha256':hashlib.sha256(Path('src/flyhard/cns_view.py').read_bytes()).hexdigest(),
        'render_wall_seconds':time.perf_counter()-start}
    if not args.preview_only:
        assert written == len(frames)
        result['video_sha256'] = hashlib.sha256(video_path.read_bytes()).hexdigest()
    (root/('preview-metrics.json' if args.preview_only else 'render-metrics.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    main()
