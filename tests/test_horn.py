import numpy as np
import pytest

from flyhard.horn import (FIELDS, HISTORY, HornCase, ObservationHistory,
                         encode_history, episode, make_cases, observation, score)


def test_already_green_has_identical_initial_and_later_observations():
    c = HornCase(1, 'arrive_green', 5, 2)
    h = ObservationHistory()
    initial = encode_history(h.update(observation(c, 0)))
    for t in np.arange(.1, 2, .1):
        assert np.array_equal(initial, encode_history(h.update(observation(c, t))))


def test_same_green_scene_requires_past_observations():
    waited = HornCase(1, 'wait_then_green', 5, 2)
    arrived = HornCase(2, 'arrive_green', 5, 2)
    a,b = ObservationHistory(),ObservationHistory()
    for t in np.arange(0, 2.1, .1):
        x = a.update(observation(waited, t));y = b.update(observation(arrived, t))
    assert np.array_equal(x[-1], y[-1])
    assert not np.array_equal(encode_history(x), encode_history(y))


def test_all_negative_scenarios_are_quiet_and_test_geometries_are_held_out():
    train, test = make_cases('train', 2), make_cases('test', 2)
    assert {c.seed for c in train}.isdisjoint(c.seed for c in test)
    assert max(c.gap_m for c in train) < min(c.gap_m for c in test)
    assert max(c.green_at for c in train) < min(c.green_at for c in test)
    for c in test:
        _,_,y = episode(c)
        assert y.any() == (c.kind == 'wait_then_green')


def test_metric_rejects_early_beep_repeated_beeps_and_stuck_button():
    c = HornCase(1, 'wait_then_green', 5, 2)
    times = np.arange(0, 6, .05)
    good = (times >= 2.25) & (times < 2.8)
    assert score(c, times, good)['passed']
    for bad in [good | (times < .2), good | ((times >= 3) & (times < 3.4)), times >= 2.25]:
        assert not score(c, times, bad)['passed']
    assert not score(c, times, np.zeros(len(times), dtype=bool))['passed']
    assert not score(HornCase(2,'arrive_green',5,2),times,good)['passed']


def test_observation_encoder_rejects_nonfinite_or_incomplete_data():
    with pytest.raises(ValueError):encode_history(np.zeros((HISTORY-1,len(FIELDS))))
    with pytest.raises(ValueError):ObservationHistory().update([float('nan')]*len(FIELDS))


def test_beep_audio_stays_silent_outside_measured_press(tmp_path):
    import wave
    from flyhard.horn_audio import press_intervals,write_horn_audio
    times=np.arange(60)/60;pressed=(times>=.4)&(times<.6)
    intervals=press_intervals(times,pressed,1/60)
    path=tmp_path/'horn.wav';write_horn_audio(path,intervals,1.)
    with wave.open(str(path)) as f:pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,2)
    assert not pcm[:round(.4*48000)].any()
    assert pcm[round(.41*48000):round(.59*48000)].any()
    assert not pcm[round(.6*48000):].any()
    assert press_intervals(times,np.zeros(60,dtype=bool),1/60)==[]


def test_recording_rejects_transient_red_observations():
    from flyhard.horn import valid_light_sequence
    assert valid_light_sequence('arrive_green',[1,1,1],[1]*18)
    assert not valid_light_sequence('arrive_green',[1,0,1],[1]*18)
    assert not valid_light_sequence('arrive_green',[1,1,1],[1,1,0,1])
    assert valid_light_sequence('wait_then_green',[0,0,1,1],[0]*6+[1]*18)
    assert not valid_light_sequence('wait_then_green',[0,1,0,1],[0,1,1,1])
    assert not valid_light_sequence('no_car',[0,0,0],[0]*18)
