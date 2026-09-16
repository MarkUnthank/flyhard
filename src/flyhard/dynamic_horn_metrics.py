"""Measured episode receipts; assertions describe actual motion and horn use."""
import numpy as np


def capture_score(kind,frames):
    times=np.array([r['camera_time'] for r in frames]);press=np.array([r['horn_pressed'] for r in frames])
    onset=np.flatnonzero(press & ~np.r_[False,press[:-1]])
    ends=np.flatnonzero(press & ~np.r_[press[1:],False])
    longest=float(max((b-a+1)/60 for a,b in zip(onset,ends))) if len(onset) else 0.
    speed=np.array([r['speed_m_s'] for r in frames]);green=np.array([r['light_green'] for r in frames])
    lead=np.array([r['lead_present'] for r in frames]);brake=np.array([r['brake'] for r in frames])
    positions=np.array([np.array(r['vehicle_matrix'])[:3,3] for r in frames])
    distance=float(np.linalg.norm(np.diff(positions,axis=0),axis=1).sum())
    stopped=np.flatnonzero((speed<.25)&~green)
    green_time=float(times[np.flatnonzero(green)[0]]) if green.any() else None
    moving_after_green=bool(green.any() and np.any((speed>2.) & (times>green_time+1.)))
    result={'kind':kind,'beep_count':int(len(onset)),'beep_onsets_seconds':times[onset].tolist(),
            'pressed_seconds':float(press.sum()/60),'distance_m':distance,'peak_speed_m_s':float(speed.max()),
            'longest_hold_seconds':longest,
            'red_stop_frames':int(len(stopped)),'green_time':green_time,
            'moving_after_green':moving_after_green,'collision_free_claim':False}
    if kind in {'empty','arrive_green'}:
        passed=not press.any() and distance>15 and moving_after_green
        if kind=='empty':passed &= len(stopped)>=15
    elif kind=='wait_green':
        reaction=float(times[onset[0]]-green_time) if len(onset) and green_time is not None else None
        result['reaction_seconds']=reaction
        passed=len(onset)==1 and reaction is not None and 0<=reaction<=.8 and len(stopped)>=15 and moving_after_green
    elif kind.startswith('cut_in'):
        entered=np.flatnonzero(lead & ~np.r_[lead[0],lead[:-1]])
        result['lead_entry_seconds']=times[entered].tolist()
        result['maximum_brake']=float(brake.max())
        passed=len(entered)>0 and len(onset)>0 and times[onset[0]]>=times[entered[0]]-.1 and longest>=1.2 and brake.max()==0 and distance>15
    elif kind=='road_rage':
        ids=sorted({v for r in frames for v in r['nearby_ids']})
        encounters=[{'car_id':v,'honked_while_near':any(r['horn_pressed'] and v in r['nearby_ids'] for r in frames)} for v in ids]
        result['encounters']=encounters
        result['wheel_angle_range']=float(np.ptp([r['wheel_angle'] for r in frames]))
        passed=len(ids)>=3 and all(r['honked_while_near'] for r in encounters) and distance>90 and len(onset)>=3
    else:
        raise ValueError(kind)
    result['passed']=bool(passed)
    return result
