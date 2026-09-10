import numpy as np
from flyhard.three_point import cases,metrics,observation,encode,kinematic_step
from flyhard.parking import REAR_TO_CENTER


def test_target_requires_opposite_heading_and_full_car_inside_road():
    c=cases('validation',1)[0];s=np.r_[c.goal,0]
    assert metrics(s,c)['pose_passed'] and not metrics(s,c)['collision']
    s[2]=0
    assert not metrics(s,c)['pose_passed']
    s=np.r_[c.goal,0];s[1]=c.width/2
    assert metrics(s,c)['collision']


def test_frozen_split_widths_and_seeds_do_not_overlap():
    train=cases('train',64);held=cases('heldout',8)
    assert not {c.seed for c in train}&{c.seed for c in held}
    assert not {c.width for c in train}&{c.width for c in held}


def test_heading_encoder_is_periodic_at_wrap_boundary():
    c=cases('train',1)[0];a=observation(c.start,c,0);b=a.copy();b[2]+=2*np.pi
    np.testing.assert_allclose(encode(a),encode(b),atol=2e-6)


def test_vehicle_step_reverse_turn_changes_heading_oppositely():
    left=kinematic_step([0,0,0,.5],.2,.5)
    reverse=kinematic_step([0,0,0,-.5],.2,-.5)
    assert left[2]>0 and reverse[2]<0
