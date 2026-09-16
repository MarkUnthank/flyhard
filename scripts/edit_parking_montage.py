#!/usr/bin/env python3
"""Edit existing MP4s only: faster grids, real close-ups and independent fly replay."""
import hashlib,json,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/parking-punchy-edit'
DESKTOP=Path.home()/'Desktop'
SAVED=DESKTOP/'Flyhard-parking-2026-09-10'
MONTAGE=SAVED/'Flyhard-50-parking-attempts-Mozart-r20.mp4'
MAIN=SAVED/'Flyhard-parallel-parking-r20-25s.mp4'
MUSIC=ROOT/'assets/music/mozart-k525/allegro.ogg'
FONT=ROOT/'assets/fonts/Geist.ttf'
# Existing montage coordinates. Reflow 8 and 32 into denser grids beside the fly.
LAYOUTS={1:(330,72,1260,944,1,1),4:(330,72,630,472,2,2),8:(16,190,472,354,4,3),16:(332,72,314,236,4,4),32:(16,188,236,178,8,6)}
SHOTS=[
 {'kind':'grid','count':1,'start':.4,'duration':1.6},
 {'kind':'grid','count':4,'start':8.3,'duration':1.6},
 {'kind':'grid','count':8,'start':16.1,'duration':1.6},
 {'kind':'grid','count':16,'start':24.5,'duration':1.6},
 {'kind':'grid','count':32,'start':32.0,'duration':3.2},
 {'kind':'solo','seed':34024,'start':25.,'duration':3.2},
 {'kind':'grid','count':32,'start':36.2,'duration':2.4},
 {'kind':'solo','seed':34048,'start':4.1,'duration':2.4},
 {'kind':'grid','count':8,'start':21.8,'duration':1.6},
 {'kind':'grid','count':32,'start':33.5,'duration':3.2},
 {'kind':'solo','seed':34049,'start':25.,'duration':2.4},
 {'kind':'grid','count':32,'start':36.3,'duration':3.2},
 {'kind':'card','duration':2.0},
]

def run(cmd):subprocess.run(cmd,check=True)
def font(n):return ImageFont.truetype(str(FONT),n)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def background(shot,index):
 im=Image.new('RGBA',(1920,1080),(0,0,0,0));d=ImageDraw.Draw(im)
 d.text((24,23),'flyhard | parallel parking',font=font(26),fill='#eee')
 d.text((1896,23),'thedrivingfly.com',anchor='ra',font=font(26),fill='#eee')
 d.text((1400,300),'Fly replay',font=font(26),fill='#eee')
 d.text((1400,730),'Original take · independent replay',font=font(19),fill='#999')
 label=f"{shot['count']} attempt"+('s' if shot.get('count',0)>1 else '') if shot['kind']=='grid' else f"Attempt {shot['seed']-33999}" if shot['kind']=='solo' else '50 trials'
 d.text((24,1050),label,font=font(27),anchor='lm',fill='#eee')
 d.text((1896,1050),'Edited excerpts · 6× driving replay',font=font(21),anchor='rm',fill='#aaa')
 if shot['kind']=='card':
  d.text((90,375),'50 attempts.',font=font(70),fill='#eee')
  d.text((90,480),'0 passed the parking gate.',font=font(48),fill='#eee')
  d.text((90,580),'10 collision flags · full results saved with the video',font=font(26),fill='#aaa')
  d.text((90,740),'CARLA · CVC / UAB   |   MaleCNS · Janelia   |   FlyGym · EPFL',font=font(21),fill='#888')
  d.text((90,784),'Mozart · K. 525, I. Allegro   |   Musopen / European Archive',font=font(21),fill='#888')
  d.text((90,828),'Saved footage · sponsor artwork r20 / layout 5',font=font(21),fill='#888')
 p=OUT/f'edit-bg-{index:02}.png';im.save(p);return p

def encode(pair):
 index,shot=pair;duration=shot['duration'];frames=round(duration*60);bg=background(shot,index)
 cmd=['ffmpeg','-nostdin','-v','error','-y','-filter_complex_threads','3']
 filters=[]
 if shot['kind']!='card':
  source=MONTAGE if shot['kind']=='grid' else OUT/str(shot['seed'])/'camera.mp4'
  rate=1 if shot['kind']=='grid' else 6
  cmd+=['-threads','1','-ss',str(shot['start']),'-t',str(duration*rate+.1),'-i',str(source)]
  if shot['kind']=='grid':
   n=shot['count'];x,y,cw,ch,source_cols,cols=LAYOUTS[n];tw,th=1248//cols,936//cols
   names=[];coords=[]
   filters.append('[0:v]setpts=PTS-STARTPTS,split='+str(n)+''.join(f'[c{i}]' for i in range(n)))
   for i in range(n):
    filters.append(f'[c{i}]crop={cw}:{ch}:{x+(i%source_cols)*cw}:{y+(i//source_cols)*ch},scale={tw}:{th}:flags=lanczos,setsar=1[t{i}]')
    last_row=(i//cols)==(n-1)//cols;row_count=n%cols if last_row and n%cols else cols
    offset=(1248-row_count*tw)//2 if last_row else 0
    names.append(f'[t{i}]');coords.append(f'{offset+(i%cols)*tw}_{(i//cols)*th}')
   if n==1:filters.append('[t0]null[drive]')
   else:filters.append(''.join(names)+f'xstack=inputs={n}:layout='+ '|'.join(coords)+':fill=black[drive]')
  else:
   filters.append('[0:v]setpts=(PTS-STARTPTS)/6,fps=60,scale=1248:936:flags=lanczos,setsar=1[drive]')
  bgindex=1;flyindex=2
 else:bgindex=0;flyindex=1
 cmd+=['-threads','1','-loop','1','-framerate','60','-i',str(bg),'-stream_loop','-1','-threads','1','-ss',str(shot['timeline_start']%20),'-i',str(OUT/'fly-replay.mp4'),'-f','lavfi','-i','color=c=black:s=1920x1080:r=60']
 if shot['kind']!='card':filters.append(f'[{flyindex+1}:v][drive]overlay=72:80:eof_action=pass:shortest=1[base]')
 else:filters.append(f'[{flyindex+1}:v]null[base]')
 filters.append(f'[{flyindex}:v]setpts=PTS-STARTPTS,scale=496:364:flags=lanczos[fly]')
 filters.append('[base][fly]overlay=1400:350:shortest=1[pictures]')
 filters.append(f'[pictures][{bgindex}:v]overlay=0:0:shortest=1,format=yuv420p[v]')
 script=OUT/f'edit-filters-{index:02}.txt';script.write_text(';\n'.join(filters))
 dest=OUT/f'edit-shot-{index:02}.mp4'
 cmd+=['-filter_complex_script',str(script),'-map','[v]','-an','-frames:v',str(frames),'-r','60','-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-movflags','+faststart',str(dest)]
 run(cmd);print(json.dumps({'shot':index,'kind':shot['kind'],'count':shot.get('count'),'encoded':True}),flush=True)
 return dest

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 # Crop an existing fly rendering; exclude its credits. No 3D rendering occurs.
 if '--assemble-only' not in sys.argv:run(['ffmpeg','-nostdin','-v','error','-y','-ss','1.5','-i',str(MAIN),'-t','20','-vf','crop=600:440:1296:584','-an','-c:v','libx264','-preset','veryfast','-crf','17','-threads','4',str(OUT/'fly-replay.mp4')])
 elapsed=0
 for shot in SHOTS:shot['timeline_start']=elapsed;elapsed+=shot['duration']
 assert abs(elapsed-30)<1e-7
 if '--assemble-only' in sys.argv:
  segments=[OUT/f'edit-shot-{i:02}.mp4' for i in range(len(SHOTS))]
 else:
  with ThreadPoolExecutor(max_workers=2) as pool:segments=list(pool.map(encode,enumerate(SHOTS)))
 concat=OUT/'punchy-concat.txt';concat.write_text(''.join("file '"+str(p)+"'\n" for p in segments))
 final=DESKTOP/'Flyhard-parking-Mozart-fast-edit.mp4'
 run(['ffmpeg','-nostdin','-v','error','-y','-threads','1','-f','concat','-safe','0','-i',str(concat),'-ss','0.4','-i',str(MUSIC),'-map','0:v','-map','1:a','-c:v','libx264','-profile:v','baseline','-level:v','4.2','-bf','0','-refs','1','-preset','veryfast','-crf','17','-threads','4','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-af','atrim=duration=30,asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=out:st=29:d=1','-t','30','-movflags','+faststart',str(final)])
 receipt={'output':str(final),'sha256':sha(final),'duration_seconds':30,'frames':1800,'fps':60,'max_grid_at_seconds':6.4,'shots':SHOTS,'fly':'Crop of existing original take, looped independently. Labelled Fly replay; not synchronized to each trial.','driving':'Existing recorded video excerpts only; no resimulation, no added steering or new viewpoints.','artwork':'Preserved r20 under user instruction; no refresh or 3D regeneration.','sources':{str(p):sha(p) for p in [MONTAGE,MAIN,MUSIC,*[OUT/str(s)/'camera.mp4' for s in [34024,34048,34049]]]}}
 (OUT/'fast-edit-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'output':str(final),'sha256':receipt['sha256']}),flush=True)
if __name__=='__main__':main()
