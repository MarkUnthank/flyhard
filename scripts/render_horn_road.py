#!/usr/bin/env python3
"""Render sponsor meshes in a process owning its own EGL display lifecycle."""
import argparse,json,time
from pathlib import Path
import imageio.v2 as imageio
import numpy as np
from PIL import Image
from flyhard.live_livery import verify_live_livery
from flyhard.sponsor_view import SponsorView
from train_horn import sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True);p.add_argument('--asset',required=True);p.add_argument('--out',required=True)
    p.add_argument('--preview-only',action='store_true');args=p.parse_args()
    root,out=Path(args.run),Path(args.out);out.mkdir(parents=True,exist_ok=True)
    manifest=verify_live_livery(args.asset,out)
    config=json.loads((root/'config.json').read_text());frames=json.loads((root/'frames.json').read_text())
    view=SponsorView(args.asset,manifest,config['vehicle_bounds']['location'])
    from OpenGL import GL
    gpu=GL.glGetString(GL.GL_RENDERER).decode();assert 'NVIDIA' in gpu
    wanted={0,min(100,len(frames)-1),min(200,len(frames)-1),min(400,len(frames)-1),len(frames)-1}
    cached=args.preview_only and all((root/f'depth-preview-{i:04}.png').exists() and
                                    (root/f'carla-preview-{i:04}.png').exists() for i in wanted)
    rgb_reader=None if cached else imageio.get_reader(root/'carla-camera.mp4',input_params=['-threads','1'])
    depth_reader=None if cached else imageio.get_reader(root/'native-depth.mkv',input_params=['-threads','1'])
    writer=None if args.preview_only else imageio.get_writer(out/'road.mp4',fps=60,codec='libx264',macro_block_size=1,
        ffmpeg_params=['-crf','14','-preset','fast','-profile:v','baseline','-bf','0','-refs','1','-threads','2'])
    visible=[];started=time.monotonic()
    try:
        samples=((i,np.asarray(Image.open(root/f'carla-preview-{i:04}.png')),
                     np.asarray(Image.open(root/f'depth-preview-{i:04}.png'))) for i in sorted(wanted)) if cached else (
                     (i,raw,encoded) for i,(raw,encoded) in enumerate(zip(rgb_reader,depth_reader)))
        for i,raw,encoded in samples:
            if args.preview_only and i not in wanted:continue
            row=frames[i];encoded=encoded.astype(np.float32)
            depth=(encoded[:,:,0]+256*encoded[:,:,1]+65536*encoded[:,:,2])*(1000/16777215)
            relative=np.linalg.inv(np.asarray(row['vehicle_matrix']))@np.asarray(row['camera_matrix'])
            road,count=view.render(relative,config['fov_degrees'],raw,depth);visible.append(count)
            if i in wanted:Image.fromarray(road).save(out/f'road-{i:04}.png')
            if writer:writer.append_data(road)
        assert i+1==len(frames)
    finally:
        if rgb_reader:rgb_reader.close()
        if depth_reader:depth_reader.close()
        if writer:writer.close()
        view.close()
    result={'status':'previewed' if args.preview_only else 'rendered','frames':len(frames),
            'frames_sha256':sha(root/'frames.json'),'native_rgb_sha256':sha(root/'carla-camera.mp4'),
            'native_depth_sha256':sha(root/'native-depth.mkv'),
            'asset_manifest_sha256':sha(Path(args.asset)/'manifest.json'),
            'revision':manifest['revision'],'layout':manifest['layoutVersion'],
            'minimum_sponsor_pixels':min(visible),'gpu':gpu,'wall_seconds':time.monotonic()-started}
    result['exact_preview_cache']=cached
    if writer:result['video_sha256']=sha(out/'road.mp4')
    (out/('preview-metrics.json' if args.preview_only else 'metrics.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
