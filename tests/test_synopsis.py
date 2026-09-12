"""The description beside the films has to follow the trace, not a guess about it."""
from flyhard.synopsis import beats, synopsis


def drive(speeds, offsets=None, brakes=None, gaps=None):
    offsets = offsets or [0.]*len(speeds)
    brakes = brakes or [0.]*len(speeds)
    gaps = gaps or [100.]*len(speeds)
    return [{'time': (i+1)*.05, 'speed_m_s': s, 'lane_offset': o, 'measured_brake': b,
             'lead_gap': g}
            for i, (s, o, b, g) in enumerate(zip(speeds, offsets, brakes, gaps))]


def test_empty_trace_says_nothing():
    assert beats([]) == []


def test_times_run_from_the_first_frame_not_from_the_clock():
    rows = drive([10., 10., 10.])
    rows = [{**row, 'time': row['time']+90.} for row in rows]
    assert beats(rows)[0][0] == 0.1


def test_a_collision_is_the_step_that_loses_the_most_speed():
    rows = drive([20., 20., 20., 6., 6.])
    assert any('hits something' in what for _, what in beats(rows))
    assert [when for when, what in beats(rows) if 'hits' in what] == [0.2]


def test_braking_is_not_mistaken_for_a_collision():
    rows = drive([20., 18.5, 17., 15.5, 14.], brakes=[.9]*5)
    assert not any('hits something' in what for _, what in beats(rows))
    assert any('brakes hard' in what for _, what in beats(rows))


def test_the_largest_excursion_is_described_not_the_first():
    rows = drive([20.]*5, offsets=[1.3, .2, .2, 4.5, 4.4])
    described = [what for _, what in beats(rows) if 'out of its lane' in what]
    assert described == ['4.5 m out of its lane to the right']


def test_a_car_that_never_returns_is_said_not_to():
    rows = drive([20.]*4, offsets=[0., 3., 3.5, 3.4])
    assert any('never comes back' in what for _, what in beats(rows))


def test_a_car_that_returns_is_said_to():
    rows = drive([20.]*4, offsets=[0., 3., 3.5, .1])
    assert any(what == 'back in the lane' for _, what in beats(rows))


def test_the_side_follows_the_sign_of_the_offset():
    rows = drive([20.]*3, offsets=[0., -3., -3.])
    assert any('to the left' in what for _, what in beats(rows))


def test_a_stop_is_reported_as_a_stop():
    assert any(what == 'stopped' for _, what in beats(drive([10., 5., .2])))


def test_catching_the_car_in_front_is_only_reported_when_it_is_close():
    far = beats(drive([20.]*3, gaps=[40., 38., 36.]))
    near = beats(drive([20.]*3, gaps=[40., 14., 12.]))
    assert not any('catches' in what for _, what in far)
    assert any('catches' in what for _, what in near)


def test_beats_come_out_in_order():
    rows = drive([10., 20., 20., 4.], offsets=[0., 3., 3., 3.])
    assert [when for when, _ in beats(rows)] == sorted(when for when, _ in beats(rows))


def test_synopsis_lines_carry_the_time_and_the_beat():
    line = synopsis(drive([10., 10.]))[0]
    assert line.startswith('0.1s — ') and 'mph' in line
