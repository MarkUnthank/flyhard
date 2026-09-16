"""Real CC0 horn recording, edited only to fit measured button presses."""
import hashlib
import json
from pathlib import Path
import wave
import numpy as np
from scipy.io import wavfile


def write_horn_audio(path, intervals, duration, sample_rate=48000):
    root=Path(__file__).resolve().parents[2]/'assets/audio'
    source=root/'car-horn-jan-ruttner.wav'
    metadata=json.loads((root/'car-horn-source.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==metadata['sha256']
    rate,data=wavfile.read(source)
    assert rate==sample_rate and data.dtype==np.int32
    data=data.astype(np.float64)/(2**31)
    if data.ndim==1:data=np.repeat(data[:,None],2,axis=1)
    # Recorded attack and steady portion of the second real honk. The steady
    # waveform is crossfaded in a loop for long physical holds, never synthesized.
    attack=data[round(1.885*rate):round(1.98*rate)]
    loop=data[round(1.98*rate):round(2.10*rate)]
    fade=round(.012*rate)
    ramp=np.linspace(0,1,fade)[:,None]
    sound=np.zeros((round(duration*rate),2),np.float64)
    spans=[]
    for start,end in sorted(intervals):
        a=max(0,round(start*rate));b=min(len(sound),round(end*rate))
        if b<=a:continue
        if spans and a<=spans[-1][1]:spans[-1][1]=max(spans[-1][1],b)
        else:spans.append([a,b])
    # Adjacent edit segments can retain one continuous measured press. Do not
    # introduce a fresh attack or a silent dip merely because the camera cut.
    for a,b in spans:
        length=b-a
        if length<=0:continue
        clip=attack.copy()
        while len(clip)<length+fade:
            overlap=clip[-fade:]*(1-ramp)+loop[:fade]*ramp
            clip=np.concatenate([clip[:-fade],overlap,loop[fade:]])
        clip=clip[:length].copy()
        edge=min(round(.006*rate),length//2)
        if edge:
            clip[:edge]*=np.linspace(0,1,edge)[:,None]
            clip[-edge:]*=np.linspace(1,0,edge)[:,None]
        sound[a:b]+=clip*1.35
    pcm=np.rint(np.clip(sound,-.96,.96)*32767).astype('<i2')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate);f.writeframes(pcm.tobytes())
    return {'source':metadata,'sample_rate':rate,'samples':len(sound),'duration_seconds':len(sound)/rate,
            'intervals':[[a/rate,b/rate] for a,b in spans],
            'editing':'Recorded attack and crossfaded steady recording; gated exclusively by measured button travel; touching edit spans retain one continuous horn'}
