#!/usr/bin/env python3
"""Combine predetermined disjoint parking shards without selecting outcomes."""
import argparse,json,shutil
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();plan=json.loads(Path(args.plan).read_text());out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    allocations=[plan[name] for name in ['primary','parallel','third']]
    indices=[i for a in allocations for i in a['indices']];assert len(indices)==50 and set(indices)==set(range(50))
    roots=[Path(a['path']) for a in allocations];specs=[json.loads((r/'evaluation-spec.json').read_text()) for r in roots]
    for name in ['checkpoint_sha256','cases_sha256','seconds','mask_selector','reset_core','camera','record','split','count']:
        assert all(spec[name]==specs[0][name] for spec in specs),name
    assert not specs[0]['reset_core'] and specs[0]['split']=='heldout' and specs[0]['count']==50
    sources=[];results=[]
    for root,allocation in zip(roots,allocations):
        all_trials=json.loads((root/'trials.json').read_text());by_seed={r['seed']:r for r in all_trials};assert len(by_seed)==len(all_trials)
        for index in allocation['indices']:
            seed=34000+index;result=by_seed[seed];results.append(result)
            trial=root/str(seed);assert (trial/'frames.json').is_file() and (trial/'camera.mp4').stat().st_size>1000
            assert json.loads((trial/'config.json').read_text())['trial_number']==index+1
            (out/str(seed)).symlink_to(trial.resolve(),target_is_directory=True)
            sources.append({'seed':seed,'source':str(trial.resolve())})
    results.sort(key=lambda r:r['seed']);assert len(results)==50
    summary={'checkpoint_sha256':specs[0]['checkpoint_sha256'],'cases_sha256':specs[0]['cases_sha256'],
             'core_reset':False,'trials':50,'selector_sensory_masked':specs[0]['mask_selector'],'policy_hz':4,'measured_control_hz':20,
             'success_rate':float(np.mean([r['success'] for r in results])),
             'collision_rate':float(np.mean([r['collision'] for r in results])),
             'full_gate_passed':sum(r['success'] for r in results)>=40,'status':'complete',
             'wall_seconds':sum(r['wall_seconds'] for r in results),'claim':'Scoped parallel parking from structured geometry'}
    for dest,field in [('mean_position_error_m','position_error_m'),('mean_yaw_error_deg','yaw_error_deg'),('mean_time_seconds','time_seconds'),('mean_direction_changes','direction_changes')]:
        summary[dest]=float(np.mean([r[field] for r in results]))
    (out/'trials.json').write_text(json.dumps(results,indent=2)+'\n');(out/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'evaluation-spec.json').write_text(json.dumps({**specs[0],'fixed_partitions':allocations},indent=2)+'\n')
    for name in ['livery-manifest.json','livery-preflight.json']:shutil.copy2(roots[0]/name,out/name)
    (out/'source-shards.json').write_text(json.dumps(sources,indent=2)+'\n');print(json.dumps(summary))


if __name__=='__main__':main()
