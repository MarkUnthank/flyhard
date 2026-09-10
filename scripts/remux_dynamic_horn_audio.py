#!/usr/bin/env python3
"""Refresh/check the live livery and replace audio without rendering 3D again."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from flyhard.live_livery import verify_live_livery
from flyhard.recorded_horn_audio import write_horn_audio
from train_horn import sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--asset',required=True);args=parser.parse_args()
    root,out=Path(args.run),Path(args.out);out.mkdir(parents=True,exist_ok=False)
    manifest=verify_live_livery(args.asset,out)
    before=json.loads((root/'livery-preflight.json').read_text())
    after=json.loads((out/'livery-preflight.json').read_text())
    # Export timestamps can change. Every actual texture and panel must match.
    content=lambda record:{k:v for k,v in record['verified_files'].items() if k!='manifest.json'}
    assert content(before)==content(after), 'Sponsor content changed; render the visual layers again'
    assert (before['revision'],before['layout'])==(after['revision'],after['layout'])
    result=json.loads((root/'render-metrics.json').read_text())
    for path in root.iterdir():
        if path.suffix=='.png' or path.name in {'picture.mp4','frame-map.json'}:
            os.link(path,out/path.name)
    old_hash=result['video_sha256']
    result['audio']=write_horn_audio(out/'horn.wav',result['audio_intervals'],result['duration_seconds'])
    result['audio_intervals']=result['audio']['intervals']
    result['audio_finalization']={'prior_video_sha256':old_hash,'picture_sha256':sha(out/'picture.mp4'),
        'script_sha256':sha(__file__),'audio_source_sha256':sha('src/flyhard/recorded_horn_audio.py'),
        'method':'Retain one continuous measured press across touching edit segments; picture unchanged'}
    name=next(root.glob('Flyhard-*.mp4')).name;video=out/name
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(out/'picture.mp4'),'-i',str(out/'horn.wav'),
        '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000',
        '-movflags','+faststart','-metadata',f"comment=Live livery r{manifest['revision']} layout {manifest['layoutVersion']}. CARLA 0.9.16 CVC UAB. Measured body-operated horn.",str(video)],check=True)
    result['video_sha256']=sha(video)
    (out/'render-metrics.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'video':str(video),'sha256':result['video_sha256'],'audio_intervals':result['audio_intervals']}))


if __name__=='__main__':main()
