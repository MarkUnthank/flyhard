"""Decoding CARLA's sensor buffers: the fast spelling must equal the obvious one.

Both of these run on every captured frame of every camera, so at six megapixels they
were costing more in copying than in arithmetic. Speeding them up is only allowed if
not a single pixel or distance changes, which is what these check.
"""
import numpy as np
import pytest

from flyhard.frames import colour, depth_metres


def buffer(shape=(48, 64), seed=1):
    return np.random.default_rng(seed).integers(0, 256, (*shape, 4), dtype=np.uint8)


def test_the_picture_matches_the_reversed_copy_it_replaces():
    bgra = buffer()
    assert np.array_equal(colour(bgra), bgra[:, :, :3][:, :, ::-1])


def test_the_picture_is_rgb_rather_than_the_bgra_it_came_from():
    bgra = np.zeros((1, 1, 4), np.uint8)
    bgra[0, 0] = [10, 20, 30, 255]          # B, G, R, A
    assert list(colour(bgra)[0, 0]) == [30, 20, 10]


def test_the_picture_is_its_own_array_and_not_a_view_of_the_buffer():
    """The buffer is CARLA's; a view of it would change under the encoder thread."""
    bgra = buffer()
    picture = colour(bgra)
    bgra[:] = 0
    assert picture.any()


def test_depth_off_the_raw_buffer_matches_depth_off_a_reversed_copy():
    bgra = buffer(seed=2)
    rgb = bgra[:, :, :3][:, :, ::-1].copy()
    was = 1000.*(rgb[:, :, 0].astype(np.float32)+rgb[:, :, 1].astype(np.float32)*256.
                 + rgb[:, :, 2].astype(np.float32)*65536.)/(256.**3-1)
    assert np.array_equal(depth_metres(bgra), was)


def test_depth_spans_the_full_kilometre_the_sensor_encodes():
    assert depth_metres(np.full((1, 1, 4), 255, np.uint8))[0, 0] == pytest.approx(1000.)
    assert depth_metres(np.zeros((1, 1, 4), np.uint8))[0, 0] == 0.


def test_depth_reads_the_channels_in_the_order_carla_packs_them():
    """CARLA documents R + G*256 + B*65536: red is the low byte and blue the high one.

    Reading them the other way round is wrong by a factor of 65536, which is the
    difference between a car two metres ahead and one past the horizon.
    """
    red, blue = np.zeros((1, 1, 4), np.uint8), np.zeros((1, 1, 4), np.uint8)
    red[0, 0, 2] = 1                         # BGRA, so index 2 is red
    blue[0, 0, 0] = 1
    assert depth_metres(blue)[0, 0] == pytest.approx(depth_metres(red)[0, 0]*65536)
