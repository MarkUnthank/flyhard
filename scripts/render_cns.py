#!/usr/bin/env python3
"""Render the anatomical layer in its own process to isolate the VTK GPU context."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import imageio.v2 as imageio
import numpy as np
from PIL import Image
from flyhard.cns_view import CNSView


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',required=True)
    parser.add_argument('--geometry',required=True)
    parser.add_argument('--preview-only',action='store_true')
    args=parser.parse_args()
    root=Path(args.run)
    fps=json.loads((root/'config.json').read_text()).get('fps',25)
    frames=json.loads((root/'frames.json').read_text())
    # Materialize once: NpzFile indexing otherwise rereads the full state
    # matrix for every video frame, which is especially costly on Pod NFS.
    with np.load(root/'neural-trace.npz') as archive:
        activity=archive['activity']
        neural_time=archive['time']
    start=time.perf_counter()
    view=CNSView(args.geometry,activity)
    print(json.dumps({'anatomy_ready_seconds':time.perf_counter()-start,
                     'renderer':view.gpu_capabilities}),flush=True)
    path=root/'cns-layer.mp4'
    writer=None if args.preview_only else imageio.get_writer(path,fps=fps,codec='libx264',
        quality=None,macro_block_size=1,ffmpeg_params=['-crf','14','-preset','fast'])
    wanted={0,min(100,len(frames)-1),min(200,len(frames)-1),min(400,len(frames)-1),len(frames)-1}
    previous=-1
    frame_map=[]
    for index,record in enumerate(frames):
        if args.preview_only and index not in wanted:continue
        decision=record['neural_index']
        if decision != previous:
            image=view.render(activity[decision])
            previous=decision
        if writer is not None:writer.append_data(image)
        if index in wanted:Image.fromarray(image).save(root/f'cns-preview-{index:04}.png')
        frame_map.append({'index':index,'neural_index':decision,'body_time':record['body_time'],
                          'neural_time':float(neural_time[decision])})
        if index % 100 == 0:print(json.dumps({'cns_frame':index}),flush=True)
    if writer is not None:writer.close()
    result={'status':'previewed' if args.preview_only else 'rendered',
        'frames':len(frame_map),'fps':fps,'width':600,'height':440,
        'geometry_sha256':sha(args.geometry),'neural_trace_sha256':sha(root/'neural-trace.npz'),
        'frames_sha256':sha(root/'frames.json'),'surface_sha256':view.surface_sha256,
        'model_rate_color_scale':view.scale,'vtk_window':view.renderer_name,
        'gpu_capabilities':view.gpu_capabilities,'frame_map':frame_map,
        'renderer_script_sha256':sha(__file__),'cns_view_sha256':sha('src/flyhard/cns_view.py'),
        'wall_seconds':time.perf_counter()-start}
    if writer is not None:result['video_sha256']=sha(path)
    view.close()
    (root/('cns-preview-metrics.json' if args.preview_only else 'cns-render-metrics.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='frame_map'},indent=2),flush=True)


if __name__=='__main__':main()
