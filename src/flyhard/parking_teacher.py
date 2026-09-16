"""Training-only Reeds-Shepp demonstrator. Never imported by learned inference."""
import math
import numpy as np
import rsplan
from flyhard.parking import (REAR_TO_CENTER,WHEELBASE,MAX_ROAD_WHEEL_ANGLE,
                             WHEEL_TO_CARLA,collision,pose_metrics)


def plan(state,case,selector=0):
    candidates=[]
    for radius in [4.5,5.5,6.5]:
        for runway in [0.,-.5,.5]:
            try:
                path=rsplan.path(tuple(state[:3]),(-REAR_TO_CENTER,0.,0.),radius,runway,.15,length_tolerance=0.)
            except (ValueError,ZeroDivisionError):
                continue
            points=path.waypoints()
            if any(collision([p.x,p.y,p.yaw,0],case) for p in points):continue
            switch=abs(selector)>.5 and points[0].driving_direction*selector<0
            candidates.append((path.total_length+.35*switch,path))
    if not candidates:return None
    return min(candidates,key=lambda x:x[0])[1]


def target(state,case,selector=0):
    metrics=pose_metrics(state,case)
    if metrics['position_error_m']<.16 and metrics['yaw_error_deg']<6:
        return np.array([0.,0.],np.float32)
    path=plan(state,case,selector)
    if path is None:return None
    points=path.waypoints()
    # A path can start with a millimetre-long correction segment. Select by
    # distance, not waypoint count, so that tiny segments do not alternate the
    # gearbox or hold the wheel on the wrong curvature at each control tick.
    distance_along=np.r_[0.,np.cumsum([math.hypot(b.x-a.x,b.y-a.y)
                                      for a,b in zip(points,points[1:])])]
    pick_index=min(int(np.searchsorted(distance_along,.22)),len(points)-1)
    pick=points[pick_index]
    direction=pick.driving_direction
    distance=0.
    for a,b in zip(points[pick_index:],points[pick_index+1:]):
        if b.driving_direction!=direction:break
        distance+=math.hypot(b.x-a.x,b.y-a.y)
    # Low speed approaching each direction change and the target pose.
    speed=min(1.0,max(.2,math.sqrt(max(distance,0.)*1.1)))
    wheel=math.atan(WHEELBASE*pick.curvature)/MAX_ROAD_WHEEL_ANGLE/WHEEL_TO_CARLA
    return np.array([wheel,speed*direction],np.float32)
