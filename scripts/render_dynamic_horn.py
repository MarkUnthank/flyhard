#!/usr/bin/env python3
"""Edit moving horn scenarios with synchronized body control and recorded audio."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw, ImageFont

from flyhard.horn_audio import press_intervals
from flyhard.recorded_horn_audio import write_horn_audio
from flyhard.horn_rig import make_horn_rig
from flyhard.live_livery import verify_live_livery
from flyhard.steering_hud import draw_steering_readout
from flyhard.video_branding import draw_site_brand
from train_horn import sha



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', nargs='+', required=True)
    p.add_argument('--title', default='horn etiquette')
    p.add_argument('--ranges', nargs='+', help='Optional start:end in source seconds for each run')
    p.add_argument('--asset', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--geometry', default='data/cns-geometry-v1/geometry-display.npz')
    p.add_argument('--preview-only', action='store_true')
    p.add_argument('--layer-workers', type=int, default=3)
    args = p.parse_args()
    if args.preview_only and args.ranges:
        p.error('Inspect the full-source previews before selecting final edit ranges')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = verify_live_livery(args.asset, out)
    sources = [Path(run) for run in args.runs]
    configurations = [json.loads((r/'config.json').read_text()) for r in sources]
    for root in sources:
        receipt=json.loads((root/'metrics.json').read_text())
        assert receipt['status']=='capture_complete' and receipt['score']['passed'], 'Source has not passed the requested behaviour checks'
    if not 1<=args.layer_workers<=4:p.error('Layer workers must be between one and four')
    if args.ranges and len(args.ranges)!=len(sources):p.error('One source range per run required')
    ranges=[tuple(map(float,r.split(':'))) for r in args.ranges] if args.ranges else [(0,c['seconds']) for c in configurations]
    def prepare_layer(item):
        root,config=item
        assert config['fps'] == 60
        metric_path = root/('cns-preview-metrics.json' if args.preview_only else 'cns-render-metrics.json')
        if not metric_path.exists():
            command = [sys.executable,'scripts/render_cns.py','--run',str(root),'--geometry',args.geometry]
            if args.preview_only:
                command.append('--preview-only')
            subprocess.run(command, check=True)
        metrics = json.loads(metric_path.read_text())
        assert metrics['frames_sha256'] == sha(root/'frames.json')
        assert metrics['neural_trace_sha256'] == sha(root/'neural-trace.npz')
        road = root/f"sponsors-r{manifest['revision']}-layout{manifest['layoutVersion']}-{sha(Path(args.asset)/'manifest.json')[:12]}"
        road_metric = road/('preview-metrics.json' if args.preview_only else 'metrics.json')
        if not road_metric.exists():
            command = [sys.executable,'scripts/render_horn_road.py','--run',str(root),'--asset',args.asset,'--out',str(road)]
            if args.preview_only:command.append('--preview-only')
            subprocess.run(command,check=True)
        road_meta = json.loads(road_metric.read_text())
        assert road_meta['frames_sha256'] == sha(root/'frames.json')
        assert road_meta['asset_manifest_sha256'] == sha(Path(args.asset)/'manifest.json')
        return str(root.resolve()),(road,road_meta)
    # Each child owns its EGL context. Independent recordings can prepare their
    # source layers together; repeated edit ranges reuse one preparation job.
    unique={str(root.resolve()):(root,config) for root,config in zip(sources,configurations)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.layer_workers) as pool:
        prepared=dict(pool.map(prepare_layer,unique.values()))
    roads=[prepared[str(root.resolve())] for root in sources]
    rig = make_horn_rig()
    replay = mj.MjData(rig.model)
    renderer = mj.Renderer(rig.model, height=440, width=600)
    gpu = GL.glGetString(GL.GL_RENDERER).decode()
    assert 'NVIDIA' in gpu
    rig.model.geom_rgba[rig.model.geom_bodyid == 0,:3] = .025
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body('wheel').id,:3] = [.3,.3,.3]
    camera = mj.MjvCamera()
    camera.lookat[:] = [.2,0.,1.1]
    camera.distance = 4.6
    camera.azimuth = 125
    camera.elevation = -24
    fonts = {s:ImageFont.truetype('assets/fonts/Geist.ttf',s) for s in [20,24,28,32,38]}
    video_path = out/'picture.mp4'
    writer = None if args.preview_only else imageio.get_writer(video_path, fps=60, codec='libx264',
        macro_block_size=1, ffmpeg_params=['-crf','17','-preset','fast','-profile:v','baseline','-bf','0','-refs','1',
                                         '-level','4.2','-threads','4','-movflags','+faststart'])
    frame_map, intervals, source_metrics = [], [], []
    offset = 0
    started = time.monotonic()
    try:
        for case_number, (root, config, (road_root,road_meta), interval) in enumerate(zip(sources, configurations,roads,ranges), 1):
            frames = json.loads((root/'frames.json').read_text())
            metrics = json.loads((root/'metrics.json').read_text())
            assert metrics['status'] == 'capture_complete'
            assert metrics['score']['passed'], 'The final edit requires the requested measured behaviour and motion'
            with np.load(root/'body-trace.npz') as archive:
                body = {k:archive[k] for k in archive.files}
            begin,end=round(interval[0]*60),round(interval[1]*60)
            assert 0<=begin<end<=len(frames)
            wanted = {begin,min(begin+100,end-1),min(begin+200,end-1),min(begin+400,end-1),end-1}
            raw_reader = None if args.preview_only else imageio.get_reader(road_root/'road.mp4', input_params=['-threads','1'])
            lamp_reader = imageio.get_reader(root/'traffic-light.mp4', input_params=['-threads','1'])
            cns_reader = None if args.preview_only else imageio.get_reader(root/'cns-layer.mp4', input_params=['-threads','1'])
            press = np.array([row['horn_pressed'] for row in frames])
            intervals.extend(press_intervals((np.arange(end-begin)+offset)/60, press[begin:end], 1/60))
            if not args.preview_only and press.any():wanted.add(min(int(np.flatnonzero(press)[0])+6,len(frames)-1))
            try:
                for i, lamp in enumerate(lamp_reader):
                    if args.preview_only and i not in wanted:
                        continue
                    road = np.asarray(Image.open(road_root/f'road-{i:04}.png')) if args.preview_only else raw_reader.get_next_data()
                    row = frames[i]
                    assert row['body_index'] == i and row['neural_index'] == body['decision_index'][i]
                    assert abs(body['time'][i]-row['camera_time']) < 1e-4
                    cns = (np.asarray(Image.open(root/f'cns-preview-{i:04}.png')) if args.preview_only else cns_reader.get_next_data())
                    if not begin<=i<end:continue
                    replay.qpos[:] = body['qpos'][i]
                    replay.qvel[:] = body['qvel'][i]
                    replay.ctrl[:] = body['ctrl'][i]
                    replay.time = body['time'][i]
                    mj.mj_forward(rig.model,replay)
                    rig.model.geom_rgba[rig.model.geom('horn_button_pad').id,:3] = (
                        [1.,.7,.12] if row['horn_pressed'] else [.9,.25,.2])
                    renderer.update_scene(replay,camera=camera)
                    renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
                    canvas = Image.new('RGB',(1920,1080),'black')
                    canvas.paste(Image.fromarray(road),(24,64))
                    canvas.paste(Image.fromarray(cns),(1296,64))
                    canvas.paste(Image.fromarray(renderer.render()),(1296,584))
                    draw = ImageDraw.Draw(canvas)
                    draw.text((24,23),'flyhard | '+args.title,font=fonts[24],fill='#eee')
                    draw_site_brand(canvas)
                    draw.text((1296,520),'Neural activity',font=fonts[24],fill='#aaa')
                    beep = row['horn_pressed']
                    draw.text((1296,562),'Fly',font=fonts[24],fill='#eee')
                    draw.text((1896,562),'BEEP' if beep else 'HORN OFF',anchor='ra',font=fonts[28],fill='#ffd25e' if beep else '#888')
                    if config['kind'] in {'empty','wait_green','arrive_green'}:
                        draw.rounded_rectangle((44,84,384,344),radius=10,fill='#080808')
                        canvas.paste(Image.fromarray(lamp),(54,94))
                    draw_steering_readout(canvas,requested_angle=row['requested_angle'],wheel_angle=row['wheel_angle'],applied_steer=row['applied_steer'])
                    draw.text((960,1052),f"Button {row['horn_travel']*100:.0f}% · Stalk inactive",anchor='mm',font=fonts[24],fill='#ffd25e' if beep else '#aaa')
                    if i in wanted:
                        canvas.save(out/f'preview-case{case_number}-{i:04}.png')
                        Image.fromarray(road).save(out/f'sponsored-case{case_number}-{i:04}.png')
                    if writer:
                        writer.append_data(np.asarray(canvas))
                    frame_map.append({'output_frame':offset+i-begin,'source':str(root),'source_frame':i,
                                      'neural_index':row['neural_index'],'horn_pressed':bool(beep)})
                    if i % 180 == 0:
                        print(json.dumps({'case':case_number,'frame':i,'wall_seconds':time.monotonic()-started}),flush=True)
                if not args.preview_only:
                    assert i+1 == len(frames)
            finally:
                if raw_reader:raw_reader.close()
                lamp_reader.close()
                if cns_reader:
                    cns_reader.close()
            source_metrics.append({'source':str(root),'score':metrics['score'],
                                   'minimum_sponsor_pixels':road_meta['minimum_sponsor_pixels'],
                                   'frames_sha256':sha(root/'frames.json'),
                                   'body_sha256':sha(root/'body-trace.npz'),
                                   'neural_sha256':sha(root/'neural-trace.npz')})
            offset += end-begin
        if writer:
            credit = Image.new('RGB',(1920,1080),'black')
            draw = ImageDraw.Draw(credit)
            lines = ['thedrivingfly.com',
                     'Learned steering/horn · structured observations · directed traffic and pace',
                     'CARLA 0.9.16 · CVC, Universitat Autònoma de Barcelona',
                     'MaleCNS / Janelia · NeuroMechFly / FlyGym, EPFL',
                     f"Live sponsor livery r{manifest['revision']} · layout {manifest['layoutVersion']}",
                     'Recorded horn: 15HPanska_Ruttner_Jan · CC0']
            for j,line in enumerate(lines):
                draw.text((960,374+j*56),line,anchor='mm',font=fonts[32] if j==0 else fonts[24],fill='#eee' if j==0 else '#aaa')
            draw_site_brand(credit)
            for _ in range(120):
                writer.append_data(np.asarray(credit))
    finally:
        renderer.close()
        if writer:
            writer.close()
    result = {'status':'previewed' if args.preview_only else 'rendered','sources':source_metrics,
              'fps':60,'frames':offset+120,'duration_seconds':offset/60+2,
              'livery_revision':manifest['revision'],'livery_layout':manifest['layoutVersion'],
              'gpu':gpu,'audio_intervals':intervals,
              'claim':'Single learned core operates both forelegs. Directed route, speed, traffic and rage mode; measured steering and horn. Recorded neural and body states share one clock.',
              'sponsor_note':'Exact live sponsor meshes composited with native CARLA camera and depth; not native Unreal materials.'}
    if writer:
        result['audio'] = write_horn_audio(out/'horn.wav',intervals,result['duration_seconds'])
        output = out/('Flyhard-'+args.title.replace(' ','-')+'.mp4')
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(video_path),'-i',str(out/'horn.wav'),
            '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000',
            '-movflags','+faststart','-metadata',f"comment=Live livery r{manifest['revision']} layout {manifest['layoutVersion']}. Vehicle CARLA 0.9.16 CVC UAB. Measured body-operated horn.",str(output)],check=True)
        result['video_sha256'] = sha(output)
        (out/'frame-map.json').write_text(json.dumps(frame_map)+'\n')
    (out/('preview-metrics.json' if args.preview_only else 'render-metrics.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    main()
