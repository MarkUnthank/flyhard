import numpy as np
from flyhard.parking import (cases,rectangle,overlap,pose_metrics,collision,observation,
                             encode,motor_requests,REAR_TO_CENTER)


def test_heldout_dimensions_are_disjoint_and_frozen():
    train=cases('train',128);held=cases('heldout',50)
    for field in ['length','width','front_extra','rear_extra']:
        assert {getattr(c,field) for c in train}.isdisjoint({getattr(c,field) for c in held})
    assert held==cases('heldout',50)


def test_collision_and_full_vehicle_containment():
    case=cases('heldout',1)[0]
    state=[-REAR_TO_CENTER,0,0,0]
    assert pose_metrics(state,case)['pose_passed'] and not collision(state,case)
    assert not pose_metrics([-REAR_TO_CENTER,case.width/2,0,0],case)['inside_bay']
    x,y,_,_=case.obstacles[0]
    assert collision([x-REAR_TO_CENTER,y,0,0],case)


def test_contact_is_collision_and_rotated_separation():
    a=rectangle(0,0,0,length=2,width=2)
    assert overlap(a,rectangle(2,0,0,length=2,width=2))
    assert not overlap(a,rectangle(4,0,.6,length=2,width=2))


def test_observation_contains_geometry_not_requested_controls():
    case=cases('heldout',1)[0]
    obs=observation([-1,2,.3,-.8],case,-1)
    assert obs.shape==(11,) and np.isfinite(encode(obs)).all()
    assert not np.array_equal(encode(obs),encode(observation([-1,2,.3,-.8],case,1)))


def test_direction_change_brakes_before_selector_movement():
    a=motor_requests(.2,-1,1,1)
    assert a[1]==0 and a[2]>0 and a[3]==0
    a=motor_requests(.2,-1,0,1)
    assert a[1]==0 and a[2]>0 and a[3]==-1
    a=motor_requests(.2,-1,0,-1)
    assert a[1]>0 and a[2]==0 and a[3]==-1


def test_zero_speed_request_stops():
    a=motor_requests(0,0,.7,1)
    assert a[1]==0 and a[2]>0
