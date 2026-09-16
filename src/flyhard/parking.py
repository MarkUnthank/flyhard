"""Geometry and scoring for a deliberately generous parallel-parking benchmark.

Coordinates are metres in the target car's heading frame. x/y identify the rear
axle, yaw is relative to the target, and positive y is the approach lane.
No scenario phase, route index, teacher command or time enters observations.
"""
from dataclasses import asdict, dataclass
import math
import numpy as np

# Measured from CARLA 0.9.16's Mini on the fresh GPU Pod, September 10.
WHEELBASE = 3.01
REAR_TO_CENTER = 1.609
CAR_LENGTH = 4.5527
CAR_WIDTH = 2.0971
MAX_ROAD_WHEEL_ANGLE = math.radians(70)
WHEEL_TO_CARLA = 1.7


@dataclass(frozen=True)
class ParkingCase:
    seed: int
    split: str
    length: float
    width: float
    approach_x: float
    approach_y: float
    approach_yaw: float
    front_extra: float
    rear_extra: float
    front_y: float
    rear_y: float

    def record(self):
        return asdict(self)

    @property
    def obstacles(self):
        return [(self.length/2+CAR_LENGTH/2+self.front_extra, self.front_y, CAR_LENGTH, CAR_WIDTH),
                (-self.length/2-CAR_LENGTH/2-self.rear_extra, self.rear_y, CAR_LENGTH, CAR_WIDTH)]


def cases(split, count):
    if split not in {'train', 'validation', 'heldout'}:
        raise ValueError('Unknown parking split')
    base = {'train': 14000, 'validation': 24000, 'heldout': 34000}[split]
    result=[]
    for index in range(count):
        seed=base+index; rng=np.random.default_rng(seed)
        train=split=='train'
        result.append(ParkingCase(seed,split,
            float(rng.choice([9.,10.,11.] if train else [9.5,10.5])),
            float(rng.choice([3.,3.4,3.8] if train else [3.2,3.6])),
            float(rng.uniform(3.4,4.7)),float(rng.uniform(2.8,3.6)),
            float(rng.uniform(-.08,.08)),
            float(rng.choice([0.,.3,.6] if train else [.15,.45])),
            float(rng.choice([0.,.3,.6] if train else [.15,.45])),
            float(rng.uniform(-.12,.12)),float(rng.uniform(-.12,.12))))
    return result


def rectangle(x,y,yaw,length=CAR_LENGTH,width=CAR_WIDTH):
    local=np.array([[1,1],[1,-1],[-1,-1],[-1,1]],float)*[length/2,width/2]
    c,s=math.cos(yaw),math.sin(yaw)
    return local@np.array([[c,s],[-s,c]])+[x,y]


def body_center(state):
    x,y,yaw=state[:3]
    return np.array([x+REAR_TO_CENTER*math.cos(yaw),y+REAR_TO_CENTER*math.sin(yaw)])


def overlap(a,b):
    # Separating-axis test, including contact as collision.
    for poly in [a,b]:
        for edge in [poly[1]-poly[0],poly[2]-poly[1]]:
            axis=np.array([-edge[1],edge[0]])
            pa,pb=a@axis,b@axis
            if pa.max()<pb.min() or pb.max()<pa.min():return False
    return True


def collision(state,case):
    car=rectangle(*body_center(state),state[2])
    if car[:,1].min() < -case.width/2:return True
    return any(overlap(car,rectangle(x,y,0,l,w)) for x,y,l,w in case.obstacles)


def pose_metrics(state,case):
    center=body_center(state)
    yaw=abs(math.atan2(math.sin(state[2]),math.cos(state[2])))
    corners=rectangle(*center,state[2])
    inside=bool(np.all(np.abs(corners[:,0])<=case.length/2) and
                np.all(np.abs(corners[:,1])<=case.width/2))
    return {'position_error_m':float(np.linalg.norm(center)),
            'yaw_error_deg':math.degrees(yaw),'inside_bay':inside,
            'pose_passed':inside and np.linalg.norm(center)<=.3 and yaw<=math.radians(10)}


OBSERVATION_FIELDS=['rear_x','rear_y','yaw','signed_speed','measured_selector',
                    'bay_length','bay_width','front_x','front_y','rear_obstacle_x','rear_obstacle_y']


def observation(state,case,selector):
    front,rear=case.obstacles
    return np.array([*state[:4],selector,case.length,case.width,
                     front[0],front[1],rear[0],rear[1]],dtype=np.float32)


def encode(observations):
    a=np.atleast_2d(np.asarray(observations,dtype=np.float32))
    if a.shape[1]!=len(OBSERVATION_FIELDS) or not np.isfinite(a).all():
        raise ValueError('Invalid relative parking geometry')
    x=(a[:,0]+REAR_TO_CENTER)/6; y=a[:,1]/4; yaw=a[:,2]
    raw=np.column_stack([np.ones(len(a)),x,y,np.sin(yaw),np.cos(yaw),
        a[:,3]/1.5,a[:,4],a[:,5]/10,a[:,6]/4,a[:,7]/8,a[:,8],a[:,9]/8,a[:,10]])
    grid=np.stack(np.meshgrid(np.linspace(-1,1.3,9),np.linspace(-.25,1.2,7),
                             np.linspace(-1.2,1.2,9),indexing='ij'),axis=-1).reshape(-1,3)
    delta=(np.stack([x,y,yaw],axis=1)[:,None]-grid[None])/[.26,.24,.30]
    place=np.exp(-.5*np.square(delta).sum(axis=2))
    features=np.concatenate([raw,place,place*a[:,3,None]/1.5,place*a[:,4,None]],axis=1)
    return features.astype(np.float32)


def motor_requests(wheel_request,signed_speed,actual_speed,measured_gear):
    """Fixed low-level motor adapter, with no access to geometry or manoeuvre.

    The learned signed speed chooses both direction and speed. This regulator
    translates it to pedal/selector targets; CARLA receives only measured travel.
    """
    speed=float(np.clip(signed_speed,-1.2,1.2))
    direction=1 if speed>.10 else -1 if speed<-.10 else 0
    changing=direction!=measured_gear
    stopping=direction==0 or changing or actual_speed*direction<-.05
    error=abs(speed)-abs(actual_speed)
    throttle=0. if stopping else float(np.clip(.22+.45*error,0,.55))
    brake=float(np.clip(.7 if stopping else -.5*error,0,.9))
    # Selection is a physical control target. Keep it neutral while braking
    # from a direction change, then let the fly move the selector into gear.
    selector=0 if changing and abs(actual_speed)>.15 else direction
    return np.array([np.clip(wheel_request,-.5,.5),throttle,brake,selector])
