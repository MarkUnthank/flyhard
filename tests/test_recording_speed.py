"""The two things that made a recorded trial slow, and the properties of their fixes.

A trial spent about 520 ms per control step, of which roughly 450 was sponsor
compositing and video encoding, serialised in one process on one core. Neither fix may
change a single output pixel, so that is what these check.
"""
import numpy as np
import pytest

from flyhard.scenario_cameras import Encoder


def test_the_srgb_table_matches_the_formula_it_replaces_for_every_value():
    """pyrender returns 8-bit colour, so 256 entries cover it exactly, not approximately."""
    exposure = 2.51
    levels = np.clip(np.arange(256, dtype=np.float32)/255*exposure, 0., 1.)
    table = 255*np.power(levels, 1/2.2)
    for value in range(256):
        direct = 255*np.power(np.clip(np.float32(value)/255*exposure, 0., 1.), 1/2.2)
        assert table[value] == pytest.approx(direct, abs=0, rel=0)


def test_indexing_the_table_with_an_image_reproduces_the_whole_frame_encode():
    exposure = 2.51
    levels = np.clip(np.arange(256, dtype=np.float32)/255*exposure, 0., 1.)
    table = 255*np.power(levels, 1/2.2)
    image = np.random.default_rng(0).integers(0, 256, (40, 60, 3), dtype=np.uint8)
    whole = 255*np.power(np.clip(image.astype(np.float32)/255*exposure, 0., 1.), 1/2.2)
    assert np.array_equal(table[image], whole)


def test_the_covering_box_holds_every_drawn_pixel():
    """The blend runs over the panels' bounding box; nothing outside it may be lit."""
    alpha = np.zeros((80, 120), np.uint8)
    alpha[30:44, 70:96] = 200
    rows = np.nonzero(alpha.any(axis=1))[0]
    columns = np.nonzero(alpha.any(axis=0))[0]
    box = (slice(rows[0], rows[-1]+1), slice(columns[0], columns[-1]+1))
    assert alpha[box].sum() == alpha.sum()
    outside = alpha.copy()
    outside[box] = 0
    assert not outside.any()


def test_an_empty_frame_yields_no_box_rather_than_a_bad_slice():
    alpha = np.zeros((10, 10), np.uint8)
    assert not len(np.nonzero(alpha.any(axis=1))[0])


class Recorder:
    """Stands in for an imageio writer."""

    def __init__(self, fail_on=None):
        self.frames, self.closed, self.fail_on = [], False, fail_on

    def append_data(self, frame):
        if self.fail_on is not None and len(self.frames) == self.fail_on:
            raise RuntimeError('encoder died')
        self.frames.append(int(frame[0, 0]))

    def close(self):
        self.closed = True


def test_the_threaded_encoder_writes_every_frame_in_order():
    recorder = Recorder()
    encoder = Encoder(recorder)
    for i in range(50):
        encoder.append_data(np.full((2, 2), i % 250, np.uint8))
    encoder.close()
    assert recorder.frames == [i % 250 for i in range(50)]
    assert recorder.closed


def test_an_encoder_failure_is_raised_rather_than_swallowed():
    """A dead encoder silently dropping frames would produce a short, wrong video."""
    encoder = Encoder(Recorder(fail_on=3), depth=1)
    with pytest.raises(RuntimeError, match='encoder died'):
        for i in range(60):
            encoder.append_data(np.full((2, 2), i % 250, np.uint8))
        encoder.close()


def test_the_queue_is_bounded_so_a_slow_encoder_pushes_back():
    encoder = Encoder(Recorder(), depth=4)
    assert encoder.queue.maxsize == 4
    encoder.close()
