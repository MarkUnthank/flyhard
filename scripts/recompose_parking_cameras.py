#!/usr/bin/env python3
"""Apply newly purchased artwork to saved native RGB/depth, without a rerun."""
import argparse
import json
import math
import subprocess
import sys
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import imageio.v2 as imageio
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from flyhard.live_livery import verify_live_livery
from flyhard.parking import rectangle
from flyhard.sponsor_view import SponsorView
from flyhard.steering_hud import draw_steering_readout


def completed_trials(source, plan_path):
    if not plan_path:
        for trial in json.loads((source/'trials.json').read_text()):
            yield source/str(trial['seed']),trial
        return
    plan=json.loads(Path(plan_path).read_text())
    assignments=[(Path(plan[k]['path']),34000+i) for k in ['primary','parallel','third'] for i in plan[k]['indices']]
    assert len(assignments)==50 and {seed for _,seed in assignments}==set(range(34000,34050))
    pending=dict((seed,root) for root,seed in assignments)
    while pending:
        found=False
        for seed,root in list(pending.items()):
            try:rows=json.loads((root/'trials.json').read_text())
            except (FileNotFoundError,json.JSONDecodeError):continue
            matches=[r for r in rows if r['seed']==seed]
            if not matches:continue
            assert len(matches)==1
            yield root/str(seed),matches[0]
            del pending[seed];found=True
        if pending and not found:time.sleep(5)


def compose_trial(asset,out,manifest,root,trial):
    font=ImageFont.truetype('assets/fonts/Geist.ttf',22);view=None
    dest=out/str(trial['seed']);dest.mkdir()
    config=json.loads((root/'config.json').read_text());rows=json.loads((root/'frames.json').read_text())
    old_manifest=json.loads((root.parent/'livery-manifest.json').read_text())
    old_files=json.loads((root.parent/'livery-preflight.json').read_text())['verified_files']
    new_files=json.loads((out/'livery-preflight.json').read_text())['verified_files']
    names=['render-panels.npz']+[s['texture'] for s in manifest['sponsors']]
    if old_manifest['sponsors']==manifest['sponsors'] and all(old_files.get(n)==new_files[n] for n in names):
        config.update(sponsor_revision=manifest['revision'],sponsor_layout=manifest['layoutVersion'],presentation_source=str(root.resolve()))
        (dest/'config.json').write_text(json.dumps(config,indent=2)+'\n')
        (dest/'metrics.json').write_bytes((root/'metrics.json').read_bytes())
        (dest/'camera.mp4').symlink_to((root/'camera.mp4').resolve())
        return {'seed':trial['seed'],'frames':len(rows),'source':str(root.resolve()),'reused_identical_livery':True}
    h,w=rows[0]['camera']['height'],rows[0]['camera']['width']
    if view is None:view=SponsorView(asset,manifest,config['vehicle_bounds']['location'],w,h)
    config.update(sponsor_revision=manifest['revision'],sponsor_layout=manifest['layoutVersion'],presentation_source=str(root.resolve()))
    (dest/'config.json').write_text(json.dumps(config,indent=2)+'\n');(dest/'metrics.json').write_bytes((root/'metrics.json').read_bytes())
    angle=math.radians(config['scene_yaw']);rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    corners=rectangle(0,0,0,config['case']['length'],config['case']['width'])@rotation.T+np.asarray(config['origin'])[:2]
    bay=np.column_stack([corners,np.full(4,.035),np.ones(4)])
    points=np.concatenate([a[None]+np.linspace(0,1,800)[:,None]*(b-a)[None] for a,b in zip(bay,np.roll(bay,-1,axis=0))])
    depth_reader=imageio.get_reader(root/'native-depth.mkv') if (root/'native-depth.mkv').exists() else None
    writer=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','20','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(dest/'camera.mp4')],stdin=subprocess.PIPE)
    visible=[]
    try:
        with imageio.get_reader(root/'native-camera.mp4') as reader:
            for i,row in enumerate(rows):
                raw=reader.get_next_data().copy()
                packed=depth_reader.get_next_data() if depth_reader else np.asarray(Image.open(root/'native-depth'/f'{i:05}.png'))
                packed=packed.astype(np.float32);depth=(packed[:,:,0]+256*packed[:,:,1]+65536*packed[:,:,2])*(1000/16777215)
                cam=row['camera'];matrix=np.asarray(cam['world_matrix']);cp=points@np.linalg.inv(matrix).T
                f=w/(2*math.tan(math.radians(cam['fov'])/2));den=np.maximum(cp[:,0],.01)
                u=np.rint(w/2+f*cp[:,1]/den).astype(int);v=np.rint(h/2-f*cp[:,2]/den).astype(int)
                ok=(cp[:,0]>.1)&(u>=2)&(u<w-2)&(v>=2)&(v<h-2);ids=np.flatnonzero(ok)
                ids=ids[depth[v[ids],u[ids]]>=cp[ids,0]-.08]
                for dx in [-1,0,1]:
                    for dy in [-1,0,1]:raw[v[ids]+dy,u[ids]+dx]=[217,190,92]
                relative=np.linalg.inv(np.asarray(row['vehicle_matrix']))@matrix
                raw,count=view.render(relative,cam['fov'],raw,depth);visible.append(count)
                canvas=Image.fromarray(raw);draw=ImageDraw.Draw(canvas);draw.rectangle((0,0,w,40),fill='black')
                gear={-1:'REVERSE',0:'NEUTRAL',1:'FORWARD'}[row['applied_controls']['gear']]
                draw.text((12,20),f"#{config['trial_number']:02}  {gear}",font=font,anchor='lm',fill='#eee')
                draw.text((w-12,20),f"{row['time']:.1f}s · {row['speed_m_s']*3.6:.1f} km/h",font=font,anchor='rm',fill='#eee')
                draw_steering_readout(canvas,requested_angle=row['requested_angle'],wheel_angle=row['wheel_angle'],applied_steer=row['applied_steer'])
                writer.stdin.write(np.asarray(canvas).tobytes())
    finally:
        writer.stdin.close();code=writer.wait()
        if depth_reader:depth_reader.close()
        if code:raise RuntimeError('Camera encoder failed')
    view.close()
    return {'seed':trial['seed'],'frames':len(rows),'sponsor_pixels_min':min(visible),'source':str(root.resolve())}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--asset',required=True);p.add_argument('--out',required=True)
    p.add_argument('--plan',help='Follow fixed recording partitions, then merge all 50.')
    p.add_argument('--workers',type=int,default=3);args=p.parse_args()
    source,out=Path(args.run),Path(args.out);out.mkdir(parents=True,exist_ok=False)
    manifest=verify_live_livery(args.asset,out);receipt=[]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn')) as pool:
        pending=[]
        def collect():
            for future in list(pending):
                if future.done():
                    row=future.result();receipt.append(row);pending.remove(future)
                    (out/'recomposition-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
                    print(json.dumps(row),flush=True)
        for root,trial in completed_trials(source,args.plan):
            collect();pending.append(pool.submit(compose_trial,args.asset,out,manifest,root,trial))
        for future in as_completed(list(pending)):
            collect()
    if args.plan:
        subprocess.run([sys.executable,'scripts/merge_parking_benchmark.py','--plan',args.plan,'--out',str(source)],check=True)
    for name in ['trials.json','metrics.json','evaluation-spec.json']:(out/name).write_bytes((source/name).read_bytes())


if __name__=='__main__':main()
