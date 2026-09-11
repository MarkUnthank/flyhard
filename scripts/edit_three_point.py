#!/usr/bin/env python3
"""Finish one complete successful recorded attempt, without cuts or retiming."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from flyhard.live_livery import verify_live_livery


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--asset', required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    manifest = verify_live_livery(args.asset, out)
    source = Path(plan['source'])
    recorded = json.loads((source.parent/'render-receipt.json').read_text())
    assert sha(source) == recorded['video_sha256']
    assert (recorded['sponsor_revision'], recorded['sponsor_layout']) == (manifest['revision'], manifest['layoutVersion'])
    assert recorded['actual_result']['success'], 'Use a genuinely successful recorded take'
    assert recorded['source_start_seconds'] == 0 and recorded['playback_rate'] == 1
    count = round(recorded['actual_result']['time_seconds']*20)
    indices = {int(frame['source_index']) for frame in recorded['frame_map']}
    assert set(range(count)) <= indices, 'The source must include every recorded state, including the finish'
    seconds = recorded['duration']
    assert abs(seconds-recorded['actual_result']['time_seconds']) < .06
    hold = plan['end_hold_seconds']
    assert hold >= 0
    duration = seconds+hold
    music = plan['music']
    assert sha(music['file']) == music['sha256']
    card = Image.new('RGBA', (600,440), (0,0,0,255))
    draw = ImageDraw.Draw(card)
    font = ImageFont.truetype('assets/fonts/Geist.ttf',22)
    lines = ['CARLA 0.9.16 · CVC / UAB','MaleCNS · Janelia','NeuroMechFly / FlyGym · EPFL',
             music['credit_title'],music['credit_recording'],
             f"Livery r{manifest['revision']} · layout {manifest['layoutVersion']}",
             'Recorded poses replayed at 60 fps','Sponsor surfaces composited']
    for i,line in enumerate(lines):
        draw.text((14,22+49*i),line,font=font,fill='#bbb')
    card.save(out/'credits.png')
    filters = [f'[0:v]setsar=1,tpad=stop_mode=clone:stop_duration={hold}[held]',
               f"[held][2:v]overlay=1296:584:enable='gte(t,{seconds})'[v]",
               f'[1:a]atrim=start={music["start_seconds"]}:duration={duration},asetpts=PTS-STARTPTS,'
               f'loudnorm=I=-17:TP=-1.5:LRA=11,afade=t=in:d=0.06,afade=t=out:st={duration-1}:d=1[a]']
    filter_file = out/'filters.txt'
    filter_file.write_text(';\n'.join(filters))
    output = out/plan['filename']
    command = ['ffmpeg','-nostdin','-v','error','-y','-filter_complex_threads','2','-i',str(source),
               '-i',music['file'],'-loop','1','-framerate','60','-i',str(out/'credits.png'),
               '-filter_complex_script',str(filter_file),'-map','[v]','-map','[a]',
               '-c:v','libx264','-preset','veryfast','-crf','18','-threads','6','-pix_fmt','yuv420p',
               '-r','60','-fps_mode','cfr','-c:a','aac','-b:a','192k','-ar','48000','-ac','2',
               '-t',str(duration),'-movflags','+faststart',str(output)]
    subprocess.run(command,check=True)
    receipt = {'output':str(output),'sha256':sha(output),'duration_seconds':duration,
               'attempt_seconds':seconds,'final_still_seconds':hold,'fps':60,
               'edit_environment':{'os':platform.system(),'architecture':platform.machine(),'ffmpeg':shutil.which('ffmpeg')},
               'source':str(source),'source_sha256':sha(source),'actual_result':recorded['actual_result'],
               'recorded_states_included':count,'source_first_state':min(indices),'source_last_state':max(indices),
               'artwork':{'revision':manifest['revision'],'layout':manifest['layoutVersion']},
               'music':music,'editor_sha256':sha(__file__),'plan_sha256':sha(args.plan),
               'claim':'One complete successful recorded attempt at normal speed. No montage, teaser, '
                       'time cuts, extra steering corrections or new driving run. The full original '
                       'source plays once; a final still remains after the attempt is over.'}
    (out/'edit-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__ == '__main__':
    main()
