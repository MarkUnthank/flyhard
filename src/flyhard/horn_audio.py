"""Original two-tone sound synthesized only during measured horn presses."""
from pathlib import Path
import wave
import numpy as np


def press_intervals(times,pressed,frame_period):
    times=np.asarray(times,dtype=float);pressed=np.asarray(pressed,dtype=bool)
    if times.ndim!=1 or len(times)!=len(pressed) or np.any(np.diff(times)<=0):
        raise ValueError('Expected ordered measured horn samples')
    starts=np.flatnonzero(pressed & ~np.r_[False,pressed[:-1]])
    ends=np.flatnonzero(pressed & ~np.r_[pressed[1:],False])
    return [(float(times[a]),float(times[b]+frame_period)) for a,b in zip(starts,ends)]


def write_horn_audio(path,intervals,duration,sample_rate=48000):
    sound=np.zeros(round(duration*sample_rate),dtype=np.float64)
    for start,end in intervals:
        a=max(0,round(start*sample_rate));b=min(len(sound),round(end*sample_rate))
        if b<=a:continue
        t=np.arange(b-a)/sample_rate
        # Nasal small-car horn. This is an original synthesized sound, not a
        # recording of CARLA's engine or a claimed native CARLA horn API.
        tone=(np.sin(2*np.pi*420*t)+.8*np.sin(2*np.pi*510*t)+.18*np.sin(2*np.pi*1260*t))
        envelope=np.minimum(1,np.minimum(t/.005,(len(t)/sample_rate-t)/.008))
        sound[a:b]+=.38*tone*envelope
    pcm=np.rint(np.clip(sound,-.95,.95)*32767).astype('<i2')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(sample_rate)
        f.writeframes(np.repeat(pcm[:,None],2,axis=1).tobytes())
    return {'sample_rate':sample_rate,'samples':len(sound),'duration_seconds':len(sound)/sample_rate,
            'intervals':intervals,'source':'Original two-tone synthesis; gated only by measured passive button position'}
