#!/usr/bin/env python3
"""Assemble genuine training excerpts, fade to black, then a verified full success."""
import argparse,json,subprocess,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from flyhard.live_livery import verify_live_livery

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--learning',nargs='+',required=True)
    p.add_argument('--success',required=True);p.add_argument('--out',required=True)
    p.add_argument('--asset',required=True);p.add_argument('--music',default='assets/music/mozart-k525/allegro.ogg');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    manifest=verify_live_livery(a.asset,out)
    files=[Path(x) for x in a.learning]+[Path(a.success)]
    receipts=[json.loads((x.parent/'render-receipt.json').read_text()) for x in files]
    assert receipts[-1]['actual_result']['success'], 'A failed take cannot be the successful reveal'
    assert receipts[-1]['playback_rate']==1 and receipts[-1]['source_start_seconds']==0
    revision={(r['sponsor_revision'],r['sponsor_layout']) for r in receipts}
    assert revision=={(manifest['revision'],manifest['layoutVersion'])},'Sponsors changed: recompose the saved footage first'
    assert len(revision)==1,'Rebuild every segment with the same current sponsors'
    for f,r in zip(files,receipts):assert sha(f)==r['video_sha256']
    learning_seconds=sum(r['duration'] for r in receipts[:-1]);success_seconds=receipts[-1]['duration']
    cmd=['ffmpeg','-nostdin','-v','error','-y','-filter_complex_threads','2']
    for f in files:cmd+=['-threads','1','-i',str(f)]
    card=Image.new('RGBA',(600,440),(0,0,0,255));d=ImageDraw.Draw(card);font=ImageFont.truetype('assets/fonts/Geist.ttf',22)
    lines=['CARLA 0.9.16 · CVC / UAB','MaleCNS · Janelia','NeuroMechFly / FlyGym · EPFL','Mozart K. 525 · I. Allegro','Musopen / European Archive',f"Livery r{manifest['revision']} · layout {manifest['layoutVersion']}",'Recorded poses replayed at 60 fps','Sponsor surfaces composited']
    for j,line in enumerate(lines):d.text((14,22+j*49),line,font=font,fill='#bbb')
    card.save(out/'credits.png')
    cmd+=['-i',a.music,'-loop','1','-framerate','60','-i',str(out/'credits.png')]
    parts=[]
    for i in range(len(a.learning)):parts.append(f'[{i}:v]setpts=PTS-STARTPTS,setsar=1[l{i}]')
    parts.append(''.join(f'[l{i}]' for i in range(len(a.learning)))+f'concat=n={len(a.learning)}:v=1:a=0,fade=t=out:st={learning_seconds-.65}:d=0.65[learning]')
    parts.append('color=black:s=1920x1080:r=60:d=1.1[black]')
    parts.append(f'[{len(files)-1}:v]setpts=PTS-STARTPTS,setsar=1,fade=t=in:st=0:d=0.65,tpad=stop_mode=clone:stop_duration=3[success]')
    parts.append('[learning][black][success]concat=n=3:v=1:a=0[cut]')
    parts.append(f"[cut][{len(files)+1}:v]overlay=1296:584:enable='gte(t,{learning_seconds+1.1+success_seconds})'[v]")
    duration=learning_seconds+1.1+success_seconds+3
    # Mozart continues through the black interval and real-time reveal.
    parts.append(f'[{len(files)}:a]atrim=duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-17:TP=-1.5:LRA=11,afade=t=out:st={duration-1.5}:d=1.5[a]')
    filters=out/'filters.txt';filters.write_text(';\n'.join(parts))
    final=out/'Flyhard-three-point-turn-Mozart.mp4'
    cmd+=['-filter_complex_script',str(filters),'-map','[v]','-map','[a]','-r','60','-fps_mode','cfr','-c:v','libx264','-preset','veryfast','-crf','18','-threads','6','-profile:v','high','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',str(duration),'-movflags','+faststart',str(final)]
    subprocess.run(cmd,check=True)
    receipt={'output':str(final),'sha256':sha(final),'duration_seconds':duration,'fps':60,
        'learning_seconds':learning_seconds,'black_seconds':1.1,'successful_reveal_start':learning_seconds+1.1,
        'success_playback':'Complete recorded successful attempt at real-time speed; final 3-second still hold.',
        'artwork':{'revision':receipts[-1]['sponsor_revision'],'layout':receipts[-1]['sponsor_layout']},
        'sources':[{ 'file':str(f),'sha256':sha(f),'result':r['actual_result'],'rate':r['playback_rate']} for f,r in zip(files,receipts)],
        'music':{'file':a.music,'sha256':sha(a.music),'title':'Mozart K. 525: I. Allegro','recording':'Musopen European Archive; Wikimedia Commons public-domain recording; see assets/music/mozart-k525/README.md'},
        'claim':'Scoped learned three-point turn from structured relative geometry. Measured body controls drive CARLA. Presentation interpolates recorded poses to 60 fps; sponsor meshes composited. No invented steering mistakes or neural activity.'}
    (out/'edit-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
