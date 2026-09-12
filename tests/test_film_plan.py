"""Which camera can actually see the car, and when.

The wide camera is planted beside the junction and aimed at it, so the approaching car
is behind the lens for most of its run. The first cut of the film opened several
scenarios on four seconds of empty road because the planner estimated that window from
the distance to the stop line instead of measuring it. These check the measurement and
the shot placement built on it.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

from plan_film import clamp, covered, in_frame, place


WIDTH, HEIGHT, FPS = 1248, 960, 20


def pose(position, target):
    """A camera at `position` in the car's frame, aimed at `target` in the same frame."""
    delta = np.asarray(target, float)-np.asarray(position, float)
    yaw = math.atan2(delta[1], delta[0])
    pitch = math.atan2(delta[2], math.hypot(delta[0], delta[1]))
    forward = np.array([math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch),
                        math.sin(pitch)])
    right = np.array([-math.sin(yaw), math.cos(yaw), 0.])
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack([forward, right, np.cross(right, forward)])
    matrix[:3, 3] = np.asarray(position, float)
    return matrix.tolist()


def manifest(tmp_path, poses, fov=50, attached=False):
    """One take's camera manifest, `poses` being the wide camera's pose per frame."""
    directory = tmp_path/'take'
    directory.mkdir(exist_ok=True)
    (directory/'cameras.json').write_text(json.dumps({
        'width': WIDTH, 'height': HEIGHT, 'fps': FPS,
        'views': {'wide': {'fov': fov, 'attached': attached}},
        'frames': [{'index': i, 'views': {'wide': {'fov': fov, 'attached': attached,
                                                   'relative_matrix': matrix}}}
                   for i, matrix in enumerate(poses)]}))
    return directory


def test_a_camera_aimed_at_the_car_has_it_in_frame(tmp_path):
    take = manifest(tmp_path, [pose((40., 11., 6.), (0., 0., .9))]*10)
    assert in_frame(take)['wide'] == (0., 9/FPS)


def test_a_camera_aimed_past_the_car_does_not_have_it(tmp_path):
    """The real fault: the wide camera looks at the junction, not at the car."""
    take = manifest(tmp_path, [pose((40., 11., 6.), (57., 0., .9))]*10)
    assert in_frame(take)['wide'] is None


def drive_past(focus=17., side=11., height=6.2, distances=(40., 30., 20., 10., 0., -12.)):
    """A world-fixed camera beside the road, as the car drives up to and past the focus.

    The camera keeps its world pose, so in the car's own frame it slides backwards as
    the car advances. This is the junction rig, and it is the geometry that broke the
    first cut of the film.
    """
    return [pose((behind, side, height), (behind+focus, 0., .9)) for behind in distances]


def test_the_car_is_behind_the_lens_for_most_of_a_junction_approach(tmp_path):
    """The camera looks forward at the junction; the car spends the run coming up behind it."""
    take = manifest(tmp_path, drive_past())
    opened, _ = in_frame(take)['wide']
    assert opened > 4/FPS, 'the window opened while the car was still on its way in'


def test_the_window_opens_only_once_the_car_is_past_the_focus(tmp_path):
    take = manifest(tmp_path, drive_past(distances=(40., 20., 0.)))
    assert in_frame(take)['wide'] is None
    take = manifest(tmp_path, drive_past(distances=(40., 20., 0., -12.)))
    assert in_frame(take)['wide'] == (3/FPS, 3/FPS)


def off_axis(degrees, reach=12.):
    """A camera `reach` behind the car with the car that many degrees off its axis."""
    angle = math.radians(degrees)
    position = (-reach, 0., 0.)
    return pose(position, (position[0]+reach*math.cos(angle), reach*math.sin(angle), 0.))


def test_a_car_clipping_the_frame_edge_does_not_count_as_a_shot_of_it(tmp_path):
    """Half a car in the corner is what the first cut called an establishing shot."""
    assert in_frame(manifest(tmp_path, [off_axis(25.)]))['wide'] is None, 'car on the edge'
    assert in_frame(manifest(tmp_path, [off_axis(18.)]))['wide'] is None, 'car half out'
    assert in_frame(manifest(tmp_path, [off_axis(5.)]))['wide'] == (0., 0.)


def test_an_attached_camera_gets_no_window_because_it_rides_the_car(tmp_path):
    take = manifest(tmp_path, [pose((40., 11., 6.), (57., 0., .9))], attached=True)
    assert in_frame(take) == {}


def test_a_take_with_no_manifest_constrains_nothing(tmp_path):
    assert in_frame(tmp_path/'missing') == {}


def test_a_shot_slides_into_the_window_rather_than_being_cut_short():
    shot = clamp({'beat': 'decision', 'start': 2., 'duration': 3.}, (6., 20.), 25.)
    assert (shot['start'], shot['duration']) == (6., 3.)


def test_a_shot_is_shortened_only_when_the_window_runs_out():
    shot = clamp({'beat': 'decision', 'start': 2., 'duration': 5.}, (6., 9.), 25.)
    assert (shot['start'], shot['duration']) == (6., 3.)


def test_a_shot_that_cannot_fit_at_all_is_left_where_it_was():
    """Better a shot the planner chose than a half-second flash of nothing."""
    shot = clamp({'beat': 'decision', 'start': 2., 'duration': 4.}, (9.5, 10.), 10.)
    assert (shot['start'], shot['duration']) == (2., 4.)


def test_the_window_never_runs_past_the_end_of_the_footage():
    shot = clamp({'beat': 'resume', 'start': 1., 'duration': 8.}, (2., None), 6.)
    assert shot['start']+shot['duration'] <= 6.


def test_covered_counts_only_the_overlap():
    shot = {'start': 4., 'duration': 4.}
    assert covered((6., 20.), shot) == 2.
    assert covered((0., 3.), shot) == 0.
    assert covered(None, shot) == 0.


RECORD = {'cameras': {'wide': 1, 'chase': 1, 'cabin': 1}, 'duration_seconds': 14.}


def test_a_take_is_seen_from_a_different_angle_in_every_shot():
    shots = [{'beat': 'approach', 'start': 1., 'duration': 3.},
             {'beat': 'decision', 'start': 5., 'duration': 4.},
             {'beat': 'resume', 'start': 10., 'duration': 3.}]
    chosen = [camera for camera, _ in place(RECORD, shots, {})]
    assert chosen[0] == 'wide', 'the first beat should open on its own angle'
    assert len(set(chosen)) == 3, 'the same angle twice in one take'


def test_an_unconstrained_shot_is_not_moved():
    shots = [{'beat': 'decision', 'start': 5., 'duration': 4.}]
    assert place(RECORD, shots, {})[0][1]['start'] == 5.


def test_a_camera_that_never_sees_the_car_is_passed_over():
    shots = [{'beat': 'approach', 'start': 1., 'duration': 3.}]
    assert place(RECORD, shots, {'wide': None})[0][0] == 'chase'


def test_the_approach_is_not_given_a_wide_shot_of_an_empty_junction():
    """The junction's real numbers: the car reaches the wide camera's frame at 9.4 s."""
    shots = [{'beat': 'approach', 'start': 4.15, 'duration': 4.3},
             {'beat': 'decision', 'start': 8.9, 'duration': 4.}]
    placed = place(RECORD, shots, {'wide': (9.4, 12.9)})
    assert placed[0][0] != 'wide', 'the approach happens before the wide camera sees anything'
    for camera, shot in placed:
        if camera == 'wide':
            assert shot['start'] >= 9.4, 'a wide shot starting on an empty junction'


def test_a_shot_forced_onto_a_late_camera_is_moved_into_its_window():
    """With only the wide camera, the shot moves rather than showing an empty road."""
    record = {'cameras': {'wide': 1}, 'duration_seconds': 14.}
    shots = [{'beat': 'approach', 'start': 4.15, 'duration': 3.}]
    camera, shot = place(record, shots, {'wide': (9.4, 12.9)})[0]
    assert camera == 'wide' and shot['start'] == pytest.approx(9.4)


def test_a_moment_the_wide_camera_catches_is_spent_on_the_wide_camera():
    """The chase and cabin angles ride the car; wide has it for seconds, so it wins ties."""
    shots = [{'beat': 'resume', 'start': 10., 'duration': 3.}]
    camera, _ = place(RECORD, shots, {'wide': (9.4, 13.5)})[0]
    assert camera == 'wide'


def test_a_take_is_still_seen_from_three_sides_when_the_wide_is_late():
    windows = {'wide': (9.4, 14.)}
    shots = [{'beat': 'approach', 'start': 2., 'duration': 3.},
             {'beat': 'decision', 'start': 5.5, 'duration': 3.5},
             {'beat': 'resume', 'start': 10., 'duration': 3.}]
    chosen = [camera for camera, _ in place(RECORD, shots, windows)]
    assert len(set(chosen)) == 3, f'repeated an angle: {chosen}'
    assert chosen[2] == 'wide', 'the one shot the wide camera could hold went elsewhere'


def test_the_wide_angle_is_not_reused_when_a_cheaper_angle_would_do():
    windows = {'wide': (0., None)}          # A wide that rides the car, as overtaking has.
    shots = [{'beat': 'approach', 'start': 1., 'duration': 3.},
             {'beat': 'decision', 'start': 5., 'duration': 3.}]
    chosen = [camera for camera, _ in place(RECORD, shots, windows)]
    assert len(set(chosen)) == 2


def test_an_approach_is_never_slid_forward_to_reach_a_camera():
    """Sliding an approach past its own anchor turns it into a different shot."""
    shots = [{'beat': 'approach', 'start': 4., 'duration': 3.}]
    assert place(RECORD, shots, {'wide': (6., 14.)})[0][0] != 'wide'


def test_a_resume_slides_a_little_to_reach_the_wide_angle():
    """The priority-vehicle takes: the wide window opens 1.5 s after the car moves off."""
    record = dict(RECORD, duration_seconds=15.4)
    shots = [{'beat': 'resume', 'start': 9.8, 'duration': 3.45}]
    camera, shot = place(record, shots, {'wide': (11.25, 15.35)})[0]
    assert camera == 'wide'
    assert shot['start'] == pytest.approx(11.25) and shot['duration'] == pytest.approx(3.45)


def test_a_resume_will_not_slide_further_than_its_allowance():
    shots = [{'beat': 'resume', 'start': 6., 'duration': 3.}]
    assert place(RECORD, shots, {'wide': (11., 14.)})[0][0] != 'wide'


def library_with(tmp_path, relative):
    """A one-take library whose chase camera points at `relative`."""
    take = tmp_path/'overtake'/'failure'/'overtake-s00001-a01'
    (take/'cameras'/'chase').mkdir(parents=True)
    for name in ('rgb.mp4', 'rgb-sponsored.mp4'):
        (take/'cameras'/'chase'/name).write_bytes(b'x')
    (take/'take.json').write_text(json.dumps({
        'schema': 'flyhard-clip-library-v1', 'id': 'overtake-s00001-a01', 'scenario': 'overtake',
        'seed': 1, 'attempt': 1, 'outcome': 'failure', 'duration_seconds': 5., 'fps': 20,
        'cameras': {'chase': relative}}))
    return take.parents[2]


def test_a_sponsor_free_cut_uses_the_plain_render_beside_the_sponsored_one(tmp_path):
    from flyhard.clips import ClipLibrary
    root = library_with(tmp_path, 'cameras/chase/rgb-sponsored.mp4')
    library = ClipLibrary(root)
    assert library.resolve('overtake-s00001-a01', 'chase')[0].name == 'rgb-sponsored.mp4'
    assert library.resolve('overtake-s00001-a01', 'chase', sponsored=False)[0].name == 'rgb.mp4'


def test_a_camera_that_was_never_sponsored_resolves_the_same_either_way(tmp_path):
    """The cabin view carries the fly, not a sponsor, so there is no plain twin to swap to."""
    from flyhard.clips import ClipLibrary
    root = library_with(tmp_path, 'cameras/chase/rgb-fly.mp4')
    (root/'overtake'/'failure'/'overtake-s00001-a01'/'cameras'/'chase'/'rgb-fly.mp4').write_bytes(b'x')
    library = ClipLibrary(root)
    both = [library.resolve('overtake-s00001-a01', 'chase', sponsored=s)[0] for s in (True, False)]
    assert both[0] == both[1] == root/'overtake'/'failure'/'overtake-s00001-a01'/'cameras'/'chase'/'rgb-fly.mp4'
