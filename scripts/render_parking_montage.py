#!/usr/bin/env python3
"""Present all 50 saved held-out attempts in 1/4/8/16/32 grids.

Six-times playback uses actual native samples; short trials hold their final
frame. Eleven trials reappear as the grids expand, and that is disclosed.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from flyhard.live_livery import verify_live_livery


def run(command):
    subprocess.run(command,check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--reset',required=True)
    p.add_argument('--asset',required=True);p.add_argument('--out',required=True);p.add_argument('--music',required=True);p.add_argument('--keep-recorded-artwork',action='store_true',help='Explicit user exception: preserve the existing footage and its pinned sponsor snapshot.');args=p.parse_args()
    root,out=Path(args.run),Path(args.out);out.mkdir(parents=True,exist_ok=False)
    if args.keep_recorded_artwork:
        manifest=json.loads((Path(args.asset)/'manifest.json').read_text())
        preflight=json.loads((root/'livery-preflight.json').read_text())
        for name,digest in preflight['verified_files'].items():
            assert hashlib.sha256((Path(args.asset)/name).read_bytes()).hexdigest()==digest,name
        preflight.update(status='preserved_by_user_request',artwork_policy='User asked to keep existing videos; no sponsor rerender.')
        (out/'livery-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (out/'livery-preflight.json').write_text(json.dumps(preflight,indent=2)+'\n')
    else:
        manifest=verify_live_livery(args.asset,out)
    recorded=json.loads((root/'livery-manifest.json').read_text())
    old=json.loads((root/'livery-preflight.json').read_text())['verified_files']
    current=json.loads((out/'livery-preflight.json').read_text())['verified_files']
    if (manifest['revision'],manifest['layoutVersion'],manifest['sponsors']) != (recorded['revision'],recorded['layoutVersion'],recorded['sponsors']):
        raise RuntimeError('Live livery changed. Recompose saved native RGB/depth with fresh artwork before montage.')
    for item in manifest['sponsors']:
        if old[item['texture']]!=current[item['texture']]:raise RuntimeError('Artwork bytes changed; recompose the saved cameras.')
    if old['render-panels.npz']!=current['render-panels.npz']:
        raise RuntimeError('Sponsor geometry changed; recompose the saved cameras.')
    trials=json.loads((root/'trials.json').read_text());stats=json.loads((root/'metrics.json').read_text())
    reset=json.loads((Path(args.reset)/'metrics.json').read_text())
    assert len(trials)==stats['trials']==reset['trials']==50
    assert len({r['seed'] for r in trials})==50
    for field in ['checkpoint_sha256','cases_sha256','selector_sensory_masked','policy_hz','measured_control_hz']:
        assert stats[field]==reset[field],field
    assert not stats['core_reset'] and reset['core_reset']
    trials.sort(key=lambda r:r['seed'])
    for trial in trials:
        config=json.loads((root/str(trial['seed'])/'config.json').read_text())
        if (config['sponsor_revision'],config['sponsor_layout'])!=(manifest['revision'],manifest['layoutVersion']):
            raise RuntimeError('A trial uses older sponsor artwork; recompose its saved RGB/depth.')
    groups=[[0],list(range(1,5)),list(range(5,13)),list(range(13,29)),list(range(18,50))]
    assert set(sum(groups,[]))==set(range(50))
    layouts=[(1,1,1260,944),(2,2,630,472),(4,2,472,354),(4,4,314,236),(8,4,236,178)]
    font_path='assets/fonts/Geist.ttf'
    font=lambda size:ImageFont.truetype(font_path,size)
    # Frame-aligned cuts on strong attacks in the chosen Mozart recording.
    cut_frames=[0,474,939,1450,1904,2385]
    segments=[];frame_maps=[]
    for stage,(group,layout) in enumerate(zip(groups,layouts),1):
        duration=(cut_frames[stage]-cut_frames[stage-1])/60
        cols,rows,tw,th=layout;gw,gh=cols*tw,rows*th;ox,oy=(1920-gw)//2,64+(960-gh)//2
        background=Image.new('RGB',(1920,1080),'black');draw=ImageDraw.Draw(background)
        draw.text((24,23),'flyhard | parallel parking',font=font(26),fill='#eee')
        draw.text((1896,23),'thedrivingfly.com',anchor='ra',font=font(26),fill='#eee')
        draw.text((24,1050),f'{len(group)} attempt'+('s' if len(group)>1 else '')+' at once',font=font(24),anchor='lm',fill='#eee')
        draw.text((1896,1050),'6× replay · 50 unique trials · some reappear between grids',font=font(20),anchor='rm',fill='#aaa')
        bg=out/f'background-{stage}.png';background.save(bg)
        command=['ffmpeg','-nostdin','-v','error','-y','-filter_complex_threads','4']
        for i in group:command+=['-threads','1','-i',str(root/str(trials[i]['seed'])/'camera.mp4')]
        command+=['-loop','1','-framerate','60','-i',str(bg)]
        filters=[];names=[];coordinates=[]
        for j,i in enumerate(group):
            result=trials[i];label='PARKED' if result['success'] else 'COLLISION' if result['collision'] else 'NOT PARKED'
            color='78d99d' if result['success'] else 'f0ac64'
            # Restore readable trial numbers after scaling, even in the 32 grid.
            size=max(13,min(22,tw//24));name=f't{j}'
            filters.append(f'[{j}:v]setpts=(PTS-STARTPTS)/6,fps=60,scale={tw}:{th}:flags=lanczos,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setsar=1,drawbox=x=0:y=0:w=iw:h=ih:color=0x222222:t=2,drawtext=fontfile={font_path}:text=\'# {i+1:02}\':x=8:y=h-th-{round(th*50/720)+8}:fontsize={size}:fontcolor=white:box=1:boxcolor=black:boxborderw=3,drawtext=fontfile={font_path}:text=\'{label}\':x=w-tw-8:y=5:fontsize={size}:fontcolor=0x{color}:box=1:boxcolor=black:boxborderw=3:enable=\'gte(t,{duration-.5})\'[{name}]')
            names.append(f'[{name}]');coordinates.append(f'{(j%cols)*tw}_{(j//cols)*th}')
        if len(group)==1:filters.append('[t0]null[grid]')
        else:filters.append(''.join(names)+f'xstack=inputs={len(group)}:layout='+ '|'.join(coordinates)+':fill=black[grid]')
        filters.append(f'[{len(group)}:v][grid]overlay={ox}:{oy}:shortest=1,format=yuv420p[v]')
        script=out/f'filters-{stage}.txt';script.write_text(';\n'.join(filters))
        segment=out/f'stage-{stage}.mp4'
        command+=['-filter_complex_script',str(script),'-map','[v]','-an','-frames:v',str(cut_frames[stage]-cut_frames[stage-1]),'-r','60','-c:v','libx264','-preset','veryfast','-crf','18','-threads','8','-movflags','+faststart',str(segment)]
        run(command);segments.append(segment)
        frame_maps.append({'stage':stage,'trials':[trials[i]['seed'] for i in group],'start_seconds':cut_frames[stage-1]/60,'duration_seconds':duration,'speed':6,'short_trials':'hold last recorded frame'})
        print(json.dumps({'stage':stage,'attempts':len(group),'status':'encoded'}),flush=True)
    card=Image.new('RGB',(1920,1080),'black');draw=ImageDraw.Draw(card)
    draw.text((72,64),'50 parking attempts. Same learned controller.',font=font(44),fill='#eee')
    successes=sum(x['success'] for x in trials);collisions=sum(x['collision'] for x in trials)
    lines=[f'{successes}/50 parked  ·  {collisions}/50 collisions',
           f"Mean final error: {stats['mean_position_error_m']:.2f} m / {stats['mean_yaw_error_deg']:.1f}°",
           f"Mean time: {stats['mean_time_seconds']:.1f}s  ·  direction changes: {stats['mean_direction_changes']:.1f}",
           f"Reset learned core: {round(reset['success_rate']*50)}/50 parked, {round(reset['collision_rate']*50)}/50 collisions",
           'Target: 40/50 collision-free parks, inside bay, within 0.3 m / 10°',
           'Scoped benchmark: '+('passed' if stats['full_gate_passed'] else 'not passed')]
    for i,line in enumerate(lines):draw.text((72,190+i*83),line,font=font(32),fill='#eee' if i in [0,5] else '#bbb')
    credits=['Structured geometry input · scoped parking benchmark',
             'CARLA 0.9.16 · CVC / UAB   |   MaleCNS · Janelia   |   NeuroMechFly / FlyGym · EPFL',
             f"Sponsor surfaces composited · livery r{manifest['revision']}, layout {manifest['layoutVersion']}",
             'Mozart · K. 525, I. Allegro · Musopen / European Archive · public-domain recording']
    for i,line in enumerate(credits):draw.text((72,772+i*48),line,font=font(24),fill='#999')
    draw.text((1848,1008),'thedrivingfly.com',anchor='ra',font=font(32),fill='#eee');card.save(out/'results.png')
    end=out/'results.mp4';run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-framerate','60','-i',str(out/'results.png'),'-t','6','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','8','-pix_fmt','yuv420p',str(end)])
    segments.append(end);concat=out/'concat.txt';concat.write_text(''.join("file '"+str(s.resolve())+"'\n" for s in segments))
    final=out/'flyhard-50-parking-attempts.mp4'
    total=(cut_frames[-1]+360)/60
    run(['ffmpeg','-nostdin','-v','error','-y','-f','concat','-safe','0','-i',str(concat),
         '-i',args.music,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2',
         '-af',f'atrim=duration={total},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=out:st={total-1}:d=1',
         '-t',str(total),'-metadata','title=Flyhard | 50 parallel parking attempts',
         '-metadata','comment=Mozart K. 525 I. Allegro; public-domain recording from Musopen / European Archive via Wikimedia Commons',
         '-movflags','+faststart',str(final)])
    receipt={'duration_seconds':total,'music':{'title':'Mozart: Eine kleine Nachtmusik, K. 525: I. Allegro','source':'https://commons.wikimedia.org/wiki/File:Mozart_K525_Serenade_in_G_Major_1_-_Allegro.ogg','source_sha256':hashlib.sha256(Path(args.music).read_bytes()).hexdigest(),'edit':'opening excerpt, -16 LUFS normalization, one-second ending fade'},'frame_count':cut_frames[-1]+360,'fps':60,'unique_trials':50,'stages':frame_maps,'learned':stats,'reset':reset,
             'sponsor_revision':manifest['revision'],'sponsor_layout':manifest['layoutVersion'],'artwork_policy':'preserved by user request' if args.keep_recorded_artwork else 'latest live snapshot',
             'video_sha256':hashlib.sha256(final.read_bytes()).hexdigest()}
    (out/'render-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'video':str(final),'sha256':receipt['video_sha256']}))


if __name__=='__main__':main()
