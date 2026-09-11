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


def test_calibration_changes_curvature_without_changing_speed():
    original=kinematic_step([0,0,0,.7],.3,.7)
    calibrated=kinematic_step([0,0,0,.7],.3,.7,curvature_scale=.793)
    assert calibrated[3]==original[3]
    np.testing.assert_allclose(calibrated[2],original[2]*.793)


def test_wheel_range_is_stored_in_checkpoint_interface():
    import torch
    from flyhard.three_point_policy import ThreePointPolicy
    # Same neural output, different explicitly saved actuator range.
    policy=ThreePointPolicy.__new__(ThreePointPolicy)
    torch.nn.Module.__init__(policy)
    policy.register_buffer('scale',torch.tensor([.35,1.2]))
    raw=torch.tensor([[1.,0.,0.,0.,2.]])
    policy.raw=lambda features:(raw,torch.ones(2,1))
    features=torch.zeros(1,1)
    old=policy(features)
    policy.scale[0]=.46
    new=policy(features)
    torch.testing.assert_close(new[:,0],old[:,0]*(.46/.35))
    torch.testing.assert_close(new[:,1],old[:,1])
    wheel,speed,_=policy.training_outputs(features)
    torch.testing.assert_close(wheel,new[:,0]);torch.testing.assert_close(speed,new[:,1])
