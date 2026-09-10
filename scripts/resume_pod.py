#!/usr/bin/env python3
"""Resume an existing stopped workspace with a new budget/deadline guard."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
import runpod_control as control


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pod_id');p.add_argument('--seconds',type=int,default=3600)
    p.add_argument('--reserve',type=float,default=4.);p.add_argument('--spend-cap',type=float,default=2.)
    args=p.parse_args()
    if not 120<=args.seconds<=3600 or args.reserve<4 or not 0<args.spend_cap<=6:
        p.error('Use 120–3600 seconds, at least $4 reserve, and a spend cap up to $6')
    if control.STATE.exists() and not json.loads(control.STATE.read_text()).get('closed'):
        raise RuntimeError('Use a new isolated session or reconcile its existing state first')
    pod=control.request('GET','/v2/pods/'+args.pod_id)
    if pod['status']!='EXITED' or 'start' not in pod.get('actions',[]):
        raise RuntimeError('Expected a stopped Pod that supports start')
    if control.durable_workspace(pod):raise RuntimeError('This helper resumes ordinary retained workspaces only')
    current=control.balance()
    hourly=control.compute_hourly({'gpu':{'id':pod['gpu']['id'],'count':pod['gpu']['count']},'cloud':pod['cloud']})
    # Include all currently charged retained storage, plus the resumed container.
    estimated=hourly+max(float(current['currentSpendPerHr']),.10)
    required=estimated*args.seconds/3600+.25
    if hourly>.90 or required>args.spend_cap or current['clientBalance']-required<args.reserve:
        raise RuntimeError('Existing credit, spending cap or hourly limit cannot cover this bounded resume')
    now=time.time();state={'name':pod['name'],'pod_id':pod['id'],'requested_epoch':now,
        'deadline_epoch':now+args.seconds,'initial_balance_usd':current['clientBalance'],
        'reserve_usd':args.reserve,'spend_cap_usd':args.spend_cap,'estimated_hourly_usd':estimated,
        'created':control.safe_pod(pod),'closed':False,'action':'resume','expected_image':pod['image']}
    control.save_state(state)
    with (control.STATE.parent/'runpod-guard.log').open('a') as log:
        child=subprocess.Popen([sys.executable,str(Path(control.__file__)),'watch'],stdout=log,
            stderr=log,stdin=subprocess.DEVNULL,start_new_session=True,env=os.environ.copy())
    state['guard_pid']=child.pid;control.save_state(state)
    try:
        result=control.request('POST','/v2/pods/'+pod['id']+'/action',{'action':'start'})
    except Exception:
        latest=control.request('GET','/v2/pods/'+pod['id'])
        if latest['status']=='EXITED':state['closed']=True;control.save_state(state)
        raise
    print(json.dumps({'pod_id':pod['id'],'action':'start_requested','deadline_epoch':state['deadline_epoch'],
                      'initial_balance':current['clientBalance'],'reserve_usd':args.reserve,
                      'spend_cap_usd':args.spend_cap,'estimated_hourly_usd':estimated,'result':control.safe_pod(result)},indent=2))


if __name__=='__main__':main()
