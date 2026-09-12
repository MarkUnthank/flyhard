#!/usr/bin/env python3
"""Verify an exported edit against its recorded controls, clock and audio."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True)
    args=parser.parse_args();root=Path(args.run)
    receipt=json.loads((root/'render-metrics.json').read_text())
    videos=list(root.glob('Flyhard-*.mp4'));assert len(videos)==1
    video=videos[0];assert sha(video)==receipt['video_sha256']
    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(video)]))['streams']
    picture=next(s for s in streams if s['codec_type']=='video')
    sound=next(s for s in streams if s['codec_type']=='audio')
    assert (picture['width'],picture['height'],picture['avg_frame_rate'],picture['r_frame_rate'])==(1920,1080,'60/1','60/1')
    assert int(picture['nb_frames'])==receipt['frames']
    assert abs(float(picture['duration'])-receipt['duration_seconds'])<1e-6
    assert sound['codec_name']=='aac' and int(sound['sample_rate'])==48000
    subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
    mapping=json.loads((root/'frame-map.json').read_text());assert len(mapping)+120==receipt['frames']
    sources={name:json.loads((Path(name)/'frames.json').read_text()) for name in {r['source'] for r in mapping}}
    checkpoints=set();max_clock_error=0.;native_frames=0;behaviour={}
    for name,rows in sources.items():
        config=json.loads((Path(name)/'config.json').read_text());checkpoints.add(config['checkpoint_sha256'])
        metrics=json.loads((Path(name)/'metrics.json').read_text())
        assert metrics['status']=='capture_complete' and metrics['scenario_light_sequence_valid']
        behaviour[name]=metrics['score']
        assert np.all(np.diff([r['carla_frame'] for r in rows])==1)
        max_clock_error=max(max_clock_error,max(abs(r['camera_time']-r['body_time']) for r in rows))
        assert max_clock_error<1e-4
        assert max(abs(r['applied_steer']-np.clip(r['wheel_angle']*1.7,-.85,.85)) for r in rows)<1e-7
        native_frames+=len(rows)
    assert len(checkpoints)==1, 'Use one frozen controller throughout an edit'
    allowed=np.zeros(receipt['frames']*800,dtype=bool)
    for index,row in enumerate(mapping):
        original=sources[row['source']][row['source_frame']]
        assert row['output_frame']==index and row['horn_pressed']==original['horn_pressed']
        assert row['neural_index']==original['neural_index']
        if row.get('camera')=='cabin':
            camera=original['cabin']
            assert camera['rgb_frame']==camera['depth_frame']==original['carla_frame']
            assert abs(camera['camera_time']-original['body_time'])<1e-4
        if row['horn_pressed']:allowed[index*800:(index+1)*800]=True
    with wave.open(str(root/'horn.wav')) as wav:
        assert wav.getframerate()==48000 and wav.getnchannels()==2 and wav.getsampwidth()==2
        pcm=np.frombuffer(wav.readframes(wav.getnframes()),'<i2').reshape(-1,2)
    assert len(pcm)==len(allowed) and not pcm[~allowed].any()
    assert allowed.any() and pcm[allowed].any()
    result={'status':'verified','video':video.name,'sha256':sha(video),'full_decode':'passed',
            'width':1920,'height':1080,'fps':60,'frames':receipt['frames'],
            'duration_seconds':receipt['duration_seconds'],'native_source_frames':native_frames,
            'source_camera_frames_consecutive':True,'max_clock_error_seconds':max_clock_error,
            'interior_frames':sum(r.get('camera')=='cabin' for r in mapping),
            'checkpoint_sha256':next(iter(checkpoints)),
            'behaviour_scores':behaviour,
            'audio_silent_outside_measured_press':True,'recorded_audio_source':receipt['audio']['source'],
            'livery_revision':receipt['livery_revision'],'livery_layout':receipt['livery_layout']}
    (root/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
