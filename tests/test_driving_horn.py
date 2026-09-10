import importlib.util
from dataclasses import replace
from pathlib import Path
import wave
import numpy as np
import pytest

from flyhard.driving_horn import Case, History, encode, observed
from flyhard.recorded_horn_audio import write_horn_audio


def test_same_current_car_scene_distinguishes_arrival_and_cut_in_history():
    cut=Case(1,'cut_in',2.,8.,6.,.2,.1)
    arrive=replace(cut,kind='arrive_green')
    a,b=History(),History()
    for t in np.arange(0,2.01,.1):
        left=a.update(observed(cut,t));right=b.update(observed(arrive,t))
    assert np.array_equal(left[-1],right[-1])
    assert not np.array_equal(encode(left),encode(right))


def test_initial_history_does_not_invent_a_car_or_light_transition():
    case=Case(1,'arrive_green',2.,8.,6.,0.,0.)
    row=observed(case,0)
    history=History().update(row)
    assert np.all(history==row)
    assert np.all(history[:,1]==1) and np.all(history[:,2]==1)


def test_steering_uses_current_request_without_past_route_as_horn_cue():
    case=Case(1,'arrive_green',2.,8.,6.,0.,0.)
    original=History().update(observed(case,0)); changed=original.copy()
    changed[:-1,-1]=np.linspace(-.4,.4,len(changed)-1)
    assert np.array_equal(encode(original),encode(changed))
    changed[-1,-1]=.3
    assert not np.array_equal(encode(original),encode(changed))


def test_button_contact_requires_real_press_and_releases_with_fixed_margin():
    from flyhard.horn_rig import HornButton
    class MeasuredButton(HornButton):
        def __init__(self):self._contact_closed=False;self.travel_reading=0.
        @property
        def value(self):return self.travel_reading
    button=MeasuredButton()
    for travel,expected in [(.54,False),(.55,True),(.51,True),(.46,True),(.44,False),(.53,False),(.58,True),(0.,False)]:
        button.travel_reading=travel
        assert button.pressed is expected


def test_real_recording_audio_follows_measured_hold_and_stays_silent_elsewhere(tmp_path):
    output=tmp_path/'horn.wav'
    metadata=write_horn_audio(output,[(.2,.8),(1.2,3.8)],4.)
    assert metadata['source']['license']=='CC0-1.0'
    with wave.open(str(output)) as f:
        pcm=np.frombuffer(f.readframes(f.getnframes()),'<i2').reshape(-1,2)
    assert not pcm[:9600].any()
    assert pcm[12000:35000].any()
    assert not pcm[38400:57600].any()
    assert pcm[80000:170000].any()
    assert not pcm[182400:].any()


def test_resume_replaces_expired_timer_and_rejects_ambiguous_startup(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'scripts'))
    from resume_pod import renewed_arguments
    original="bash -lc 'python /opt/flyhard/scripts/pod_deadline.py --deadline 123.4 & exec /start.sh'"
    assert renewed_arguments(original,999.5)==original.replace('123.4','999.5')
    for bad in [None,'exec /start.sh',original+' --deadline 567']:
        with pytest.raises(RuntimeError):renewed_arguments(bad,999.5)
