#!/usr/bin/env python3
"""Refresh sponsor surfaces in the cached main edit, without starting CARLA."""
import argparse,json,math,subprocess,hashlib
from pathlib import Path
import imageio.v2 as imageio
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from flyhard.live_livery import verify_live_livery
from flyhard.parking import rectangle
from flyhard.sponsor_view import SponsorView


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--run',required=True);p.add_argument('--asset',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();base,run,out=Path(args.base),Path(args.run),Path(args.out);out.mkdir(parents=True,exist_ok=False)
    manifest=verify_live_livery(args.asset,out)
    receipt=json.loads((base/'render-receipt.json').read_text());frames=json.loads((run/'frames.json').read_text());config=json.loads((run/'config.json').read_text())
    assert receipt['frames']==1500 and receipt['hero_color_rgb']==[48,84,43] and not receipt['outcome_caption']
    for name in ['frames.json','body-trace.npz','neural-trace.npz']:
        assert hashlib.sha256((run/name).read_bytes()).hexdigest()==receipt['source_sha256'][name]
    w,h=1248,960;view=SponsorView(args.asset,manifest,config['vehicle_bounds']['location'],w,h)
    fonts={n:ImageFont.truetype('assets/fonts/Geist.ttf',n) for n in [22,24]}
    angle=math.radians(config['scene_yaw']);rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    corners=rectangle(0,0,0,config['case']['length'],config['case']['width'])@rotation.T+np.asarray(config['origin'])[:2]
    bay=np.column_stack([corners,np.full(4,.035),np.ones(4)])
    points=np.concatenate([a[None]+np.linspace(0,1,800)[:,None]*(b-a)[None] for a,b in zip(bay,np.roll(bay,-1,axis=0))])
    video=out/'flyhard-parking-25s.mp4'
    writer=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','60','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','8','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
    updated=[]
    try:
        with imageio.get_reader(base/'flyhard-parking-25s.mp4') as presentation,imageio.get_reader(base/'native-camera.mp4') as cameras,imageio.get_reader(base/'native-depth.mkv') as depths:
            for index,record in enumerate(receipt['frame_map']):
                canvas=Image.fromarray(presentation.get_next_data());raw=cameras.get_next_data().copy();packed=depths.get_next_data().astype(np.float32)
                depth=(packed[:,:,0]+256*packed[:,:,1]+65536*packed[:,:,2])*(1000/16777215)
                matrix=np.asarray(record['camera_world_matrix']);cp=points@np.linalg.inv(matrix).T
                f=w/(2*math.tan(math.radians(record['fov'])/2));den=np.maximum(cp[:,0],.01)
                u=np.rint(w/2+f*cp[:,1]/den).astype(int);v=np.rint(h/2-f*cp[:,2]/den).astype(int)
                ok=(cp[:,0]>.1)&(u>=2)&(u<w-2)&(v>=2)&(v<h-2);ids=np.flatnonzero(ok);ids=ids[depth[v[ids],u[ids]]>=cp[ids,0]-.08]
                for dx in [-1,0,1]:
                    for dy in [-1,0,1]:raw[v[ids]+dy,u[ids]+dx]=[217,190,92]
                relative=np.linalg.inv(np.asarray(record['vehicle_matrix']))@matrix
                raw,count=view.render(relative,record['fov'],raw,depth);canvas.paste(Image.fromarray(raw),(24,64))
                row=frames[int(record['source_index'])];draw=ImageDraw.Draw(canvas);gear=row['applied_controls']['gear']
                draw.rounded_rectangle((48,87,270,136),radius=8,fill='black')
                draw.text((64,111),{-1:'REVERSE',0:'NEUTRAL',1:'FORWARD'}[gear],font=fonts[24],anchor='lm',fill='#ffbd59' if gear==-1 else '#eee')
                draw.text((1252,92),f"{row['speed_m_s']*3.6:.1f} km/h",font=fonts[24],anchor='ra',fill='white',stroke_width=2,stroke_fill='black')
                draw.text((48,980),f"Attempt 1 · {record['source_index']*.05:.1f}s elapsed",font=fonts[22],fill='white',stroke_width=2,stroke_fill='black')
                if index>=1380:
                    draw.rectangle((1296,584,1896,1023),fill='black')
                    lines=['One attempt · benchmark pending','CARLA 0.9.16 · CVC / UAB','MaleCNS · Janelia','NeuroMechFly / FlyGym · EPFL',f"Livery r{manifest['revision']} · layout {manifest['layoutVersion']}",'Recorded motion replayed at 60 fps','Sponsor surfaces composited']
                    for j,line in enumerate(lines):draw.text((1310,622+j*49),line,font=fonts[22],fill='#bbb')
                writer.stdin.write(np.asarray(canvas).tobytes());updated.append({**record,'sponsor_pixels':count})
                if index in [540,1379]:canvas.save(out/f'preview-{index:04}.png')
                if index%300==0:print(json.dumps({'frame':index,'sponsor_pixels':count}),flush=True)
    finally:
        writer.stdin.close();code=writer.wait();view.close()
        if code:raise RuntimeError('Encoder failed')
    receipt.update(sponsor_revision=manifest['revision'],sponsor_layout=manifest['layoutVersion'],frame_map=updated,video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),recomposition_source=str(base.resolve()),native_camera_cache='Read from the original cached main edit; no CARLA rerun.')
    (out/'render-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'video':str(video),'sha256':receipt['video_sha256']}))


if __name__=='__main__':main()
