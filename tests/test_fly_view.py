"""The placement maths behind compositing the fly into a cabin frame.

Every one of these caught a real fault while the view was being built: a mirrored
lateral axis, a camera convention that put the lens inside the fly, and an anchor on
the wrong part of the rig. They are pure geometry and need neither MuJoCo nor CARLA.
"""
import math

import numpy as np
import pytest

from flyhard.fly_view import HUB_IN_CAR, REFLECT, WHEEL_DIAMETER


CABIN = {'location': (-.45, .08, 1.35), 'yaw': -23., 'pitch': -12., 'fov': 90.}


def cabin_matrix():
    """The cabin camera's pose in the car's frame, as CARLA reports it."""
    yaw, pitch = math.radians(CABIN['yaw']), math.radians(CABIN['pitch'])
    forward = np.array([math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch),
                        math.sin(pitch)])
    right = np.array([-math.sin(yaw), math.cos(yaw), 0.])
    up = np.cross(right, forward)
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack([forward, right, up])
    matrix[:3, 3] = CABIN['location']
    return matrix


def test_the_lateral_axis_is_mirrored_and_the_others_are_not():
    """CARLA is left handed and MuJoCo is right handed; only y changes sign."""
    assert list(REFLECT) == [1., -1., 1.]


def test_the_hub_sits_ahead_of_the_cabin_camera_and_on_the_driver_s_side():
    hub = np.asarray(HUB_IN_CAR)
    camera = np.asarray(CABIN['location'])
    assert hub[0] > camera[0], 'the wheel is behind the camera'
    assert hub[1] < camera[1], 'the wheel is not on the side the camera looks towards'
    assert hub[2] < camera[2], 'the wheel is above the camera'
    assert .3 < np.linalg.norm(hub-camera) < 1.1, 'the wheel is at an implausible reach'


def test_the_hub_lands_inside_the_frame_and_not_at_its_edge():
    """A hub the camera cannot see would put the fly off screen, which happened."""
    matrix = cabin_matrix()
    width, height = 1248, 960
    delta = np.asarray(HUB_IN_CAR)-matrix[:3, 3]
    local = matrix[:3, :3].T @ delta                   # forward, right, up
    assert local[0] > .2, 'the wheel is not in front of the lens'
    focal = (width/2)/math.tan(math.radians(CABIN['fov'])/2)
    u = width/2+focal*local[1]/local[0]
    v = height/2-focal*local[2]/local[0]
    assert width*.2 < u < width*.8, f'horizontally at {u:.0f} px of {width}'
    assert height*.2 < v < height*.9, f'vertically at {v:.0f} px of {height}'


def test_the_drawn_rig_is_a_readable_size_rather_than_a_fly_sized_speck():
    """The rig is modelled at fly scale; drawn at that scale it would be invisible."""
    matrix = cabin_matrix()
    distance = np.linalg.norm(np.asarray(HUB_IN_CAR)-matrix[:3, 3])
    focal = (1248/2)/math.tan(math.radians(CABIN['fov'])/2)
    pixels = WHEEL_DIAMETER*focal/distance
    assert 150 < pixels < 450, f'the wheel would be {pixels:.0f} px across'


def test_free_camera_round_trips_a_pose_through_azimuth_and_elevation():
    """MuJoCo's angles give the view direction itself; negating them aimed it backwards."""
    from flyhard.fly_view import free_camera
    mj = pytest.importorskip('mujoco')
    for position, forward in [((-3.2, -2.7, 2.8), (.9, .38, -.21)),
                              ((0., -5., 1.), (0., 1., 0.)),
                              ((-4., 0., 1.), (1., 0., 0.)),
                              ((2., 2., 4.), (-.5, -.5, -.707))]:
        camera = free_camera(position, forward)
        azimuth, elevation = math.radians(camera.azimuth), math.radians(camera.elevation)
        direction = np.array([math.cos(elevation)*math.cos(azimuth),
                              math.cos(elevation)*math.sin(azimuth), math.sin(elevation)])
        wanted = np.asarray(forward, float)/np.linalg.norm(forward)
        assert np.allclose(direction, wanted, atol=1e-6), 'the camera aims the wrong way'
        # MuJoCo steps back from the lookat along that direction, landing at `position`.
        assert np.allclose(np.asarray(camera.lookat)-camera.distance*direction,
                           np.asarray(position, float), atol=1e-6)
        assert camera.type == mj.mjtCamera.mjCAMERA_FREE
