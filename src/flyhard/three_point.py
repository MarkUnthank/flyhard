"""Structured goal geometry for a scoped three-point-turn pilot."""
from dataclasses import dataclass,asdict
import math
import numpy as np
from flyhard.parking import (REAR_TO_CENTER,rectangle,body_center,WHEELBASE,
                            MAX_ROAD_WHEEL_ANGLE,WHEEL_TO_CARLA)

@dataclass(frozen=True)
class TurnCase:
    seed:int
    split:str
    width:float
    start_x:float
    start_y:float
    start_yaw:float
    goal_x:float
    goal_y:float

    def record(self):return asdict(self)
    @property
    def start(self):
        return np.array([self.start_x-REAR_TO_CENTER*math.cos(self.start_yaw),
                         self.start_y-REAR_TO_CENTER*math.sin(self.start_yaw),self.start_yaw,0.])
    @property
    def goal(self):return np.array([self.goal_x+REAR_TO_CENTER,self.goal_y,math.pi])


def cases(split,count):
    base={'train':51000,'validation':61000,'heldout':71000}[split]
    result=[]
    for i in range(count):
        r=np.random.default_rng(base+i)
        width=float(r.choice([9.5,10.5] if split=='train' else [10.]))
        # Width 10 m is absent from training. Independent starts and target poses.
        result.append(TurnCase(base+i,split,width,float(r.uniform(-.25,.25)),
            float(r.uniform(-2.2,-1.8)),float(r.uniform(-.04,.04)),
            float(r.uniform(-6.25,-5.75)),float(r.uniform(1.8,2.2))))
    return result


def wrap(x):return np.arctan2(np.sin(x),np.cos(x))


def metrics(state,case):
    center=body_center(state);corners=rectangle(*center,state[2])
    position=float(np.linalg.norm(center-[case.goal_x,case.goal_y]))
    yaw=abs(float(wrap(state[2]-math.pi)))
    clearance=float(min(corners[:,1].min()+case.width/2,case.width/2-corners[:,1].max()))
    return {'position_error_m':position,'yaw_error_deg':math.degrees(yaw),
        'boundary_clearance_m':clearance,'collision':clearance<=0,
        'pose_passed':position<=.6 and yaw<=math.radians(12)}


OBSERVATION_FIELDS=['rear_x_minus_goal','rear_y_minus_goal','yaw_minus_goal',
    'signed_speed','measured_selector','lower_boundary_minus_rear_y',
    'upper_boundary_minus_rear_y','goal_x','goal_y','road_width','measured_wheel']


def observation(state,case,selector,wheel=0.):
    return np.array([state[0]-case.goal[0],state[1]-case.goal[1],wrap(state[2]-math.pi),
        state[3],selector,-case.width/2-state[1],case.width/2-state[1],
        case.goal_x,case.goal_y,case.width,wheel],np.float32)


def encode(observations):
    a=np.atleast_2d(np.asarray(observations,dtype=np.float32))
    if a.shape[1]!=11 or not np.isfinite(a).all():raise ValueError('Expected finite relative turn geometry')
    x=a[:,0]/6;y=a[:,1]/5;yaw=a[:,2]
    raw=np.column_stack([np.ones(len(a)),x,y,np.sin(yaw),np.cos(yaw),a[:,3]/1.2,
        a[:,4],a[:,5]/5,a[:,6]/5,a[:,7]/6,a[:,8]/5,a[:,9]/10,a[:,10]/.35])
    grid=np.stack(np.meshgrid(np.linspace(-.7,1.5,9),np.linspace(-1.5,.6,7),
        np.linspace(-np.pi,np.pi,13,endpoint=False),indexing='ij'),axis=-1).reshape(-1,3)
    dx=(x[:,None]-grid[:,0])/.28;dy=(y[:,None]-grid[:,1])/.28
    da=wrap(yaw[:,None]-grid[:,2])/.45
    place=np.exp(-.5*(dx*dx+dy*dy+da*da))
    return np.concatenate([raw,place,place*a[:,3,None]/1.2,place*a[:,4,None]],axis=1).astype(np.float32)


def kinematic_step(state,wheel,speed,dt=.1,curvature_scale=1.):
    state=np.array(state,float,copy=True)
    # Simple training diagnostic only. Native tests use the measured body rig.
    acceleration=np.clip((speed-state[3])*2.5,-1.5,1.5)
    state[3]+=acceleration*dt
    angle=wheel*WHEEL_TO_CARLA*MAX_ROAD_WHEEL_ANGLE
    state[2]+=curvature_scale*state[3]*math.tan(angle)/WHEELBASE*dt
    state[:2]+=state[3]*np.array([math.cos(state[2]),math.sin(state[2])])*dt
    return state
