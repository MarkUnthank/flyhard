#!/usr/bin/env python3
"""Training-only Reeds-Shepp demonstrations; freeze all cases before labels."""
import argparse,json,time
from pathlib import Path
import numpy as np
# rsplan 1.0.10's enumerator is needed to reject paths outside the road. Its
# public shortest-path selector cannot enforce our curb and F/R/F constraints.
from rsplan.planner import _solve_path
from flyhard.three_point import cases,observation,metrics,wrap
from flyhard.parking import WHEELBASE,MAX_ROAD_WHEEL_ANGLE,WHEEL_TO_CARLA


def plan(case):
    valid=[]
    for radius in [3.5,4.,4.5,5.]:
        for path in _solve_path(tuple(case.start[:3]),tuple(case.goal),radius,.12):
            pts=path.waypoints();dirs=[pts[0].driving_direction]
            for p in pts:
                if p.driving_direction!=dirs[-1]:dirs.append(p.driving_direction)
            if dirs!=[1,-1,1]:continue
            if any(metrics([p.x,p.y,p.yaw,0],case)['boundary_clearance_m']<.18 for p in pts):continue
            valid.append(path)
    return min(valid,key=lambda p:p.total_length) if valid else None


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--curvature-scale',type=float,default=.7930453466373627);p.add_argument('--max-wheel',type=float,default=.46);a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    splits={s:cases(s,n) for s,n in [('train',64),('validation',8),('heldout',8)]}
    (out/'cases.json').write_text(json.dumps({s:[c.record() for c in v] for s,v in splits.items()},indent=2)+'\n')
    start=time.monotonic();receipt={'heldout_labels_generated':False,'teacher':'rsplan 1.0.10; training only','splits':{},'curvature_scale':a.curvature_scale,'max_wheel':a.max_wheel}
    for split in ['train','validation']:
        obs=[];target=[];seeds=[];missing=[]
        for case in splits[split]:
            path=plan(case)
            if path is None:missing.append(case.seed);continue
            rng=np.random.default_rng(case.seed);pts=path.waypoints()
            (out/f'teacher-{case.seed}.json').write_text(json.dumps([[p.x,p.y,p.yaw,p.driving_direction,p.curvature] for p in pts]))
            distance=np.r_[0,np.cumsum([np.hypot(b.x-a.x,b.y-a.y) for a,b in zip(pts,pts[1:])])]
            for i,p in enumerate(pts):
                end=i+1
                while end<len(pts) and pts[end].driving_direction==p.driving_direction:end+=1
                remaining=distance[min(end,len(pts)-1)]-distance[i]
                next_index=min(i+2,len(pts)-1)
                # Near a cusp, request the outgoing direction. The measured
                # low-level interlock handles braking and selector travel.
                pick=pts[end] if remaining<.24 and end<len(pts) else pts[next_index]
                direction=pick.driving_direction
                speed=min(.9,max(.22,np.sqrt(max(remaining,.04)*.9)))
                if i>=len(pts)-3:speed=0.
                for j in range(5):
                    state=np.array([p.x,p.y,p.yaw,p.driving_direction*rng.uniform(0,.95)])
                    state[:3]+=rng.normal(0,[.20,.20,.07]) if j else 0
                    if metrics(state,case)['collision']:continue
                    dx,dy=state[0]-p.x,state[1]-p.y
                    cross=-np.sin(p.yaw)*dx+np.cos(p.yaw)*dy
                    heading=float(wrap(pick.yaw-state[2]))
                    curvature=pick.curvature+direction*.9*heading-.35*cross
                    wheel=np.arctan(WHEELBASE*curvature/a.curvature_scale)/MAX_ROAD_WHEEL_ANGLE/WHEEL_TO_CARLA
                    selector=float(rng.choice([p.driving_direction,0]))
                    obs.append(observation(state,case,selector,rng.uniform(-a.max_wheel,a.max_wheel)));target.append([np.clip(wheel,-a.max_wheel,a.max_wheel),speed*direction]);seeds.append(case.seed)
            for _ in range(30):
                state=np.r_[case.goal+rng.normal(0,[.08,.08,.02]),rng.uniform(-.5,.5)]
                obs.append(observation(state,case,rng.choice([-1,0,1]),rng.uniform(-.3,.3)));target.append([0.,0.]);seeds.append(case.seed)
        np.savez_compressed(out/(split+'.npz'),observations=np.asarray(obs,np.float32),targets=np.asarray(target,np.float32),case_seeds=seeds)
        receipt['splits'][split]={'rows':len(target),'no_feasible_teacher':missing}
        print(json.dumps({split:receipt['splits'][split],'seconds':time.monotonic()-start}),flush=True)
    receipt['seconds']=time.monotonic()-start
    (out/'data-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':main()
