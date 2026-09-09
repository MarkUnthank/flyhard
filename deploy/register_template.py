#!/usr/bin/env python3
"""Promote a GPU-validated image digest into the user's private Runpod template."""
import argparse
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from runpod_control import api_key, request as runpod_request

NAME='Flyhard / CARLA 0.9.16'


def request(method,path,payload=None):
    key=api_key()
    req=urllib.request.Request('https://rest.runpod.io/v1'+path,method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'Flyhard/0.1'})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read();return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Runpod HTTP {exc.code}: '+exc.read().decode().replace(key,'[REDACTED]')) from None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--validation',required=True)
    args=parser.parse_args();validation=json.loads(Path(args.validation).read_text())
    image=validation['image']
    if not re.fullmatch(r'ghcr\.io/markunthank/flyhard@sha256:[0-9a-f]{64}',image):
        raise ValueError('Expected an immutable Flyhard image digest')
    if validation['status']!='passed' or set(validation['checks'])!={'cuda','mujoco','vtk','carla'}:
        raise ValueError('All GPU runtime checks are required')
    if not all(value=='passed' for value in validation['checks'].values()):
        raise ValueError('GPU runtime validation did not pass')
    if validation['exports']['status']!='verified':
        raise ValueError('Verified local exports are required before promotion')
    payload={'name':NAME,'imageName':image,'category':'NVIDIA','containerDiskInGb':100,
        'isPublic':False,'isServerless':False,'ports':['22/tcp'],'volumeInGb':40,
        'volumeMountPath':'/workspace','env':{'FLYHARD_MAX_RUNTIME_SECONDS':'3600'},
        'readme':'Preinstalled CARLA, CUDA, NeuroMechFly and rendering stack. SSH key supplied at deployment. '+
            'Read /workspace/flyhard/work/runtime/ready.json for measured readiness. '+
            'Auto-stops after one hour; export results and terminate to release storage. '+
            'https://github.com/MarkUnthank/flyhard/blob/main/docs/runtime-image.md'}
    matches=[t for t in request('GET','/templates') if t['name']==NAME]
    if len(matches)>1:raise RuntimeError('Duplicate Flyhard templates require reconciliation')
    if matches:
        # Runpod only accepts category and worker type when creating a template.
        updates={key:value for key,value in payload.items() if key not in {'category','isServerless'}}
        template=request('PATCH','/templates/'+matches[0]['id'],updates)
    else:
        template=request('POST','/templates',payload)
    verified=request('GET','/templates/'+template['id'])
    for key in ['name','imageName','category','containerDiskInGb','ports','volumeInGb','volumeMountPath','env']:
        if verified.get(key)!=payload[key]:
            raise RuntimeError('Runpod template readback differs for '+key)
    # The current REST response omits privacy and worker-type flags. Read the
    # actual stored values through the documented GraphQL account template list.
    visibility=runpod_request('POST','/graphql',{'query':
        'query { myself { podTemplates { id imageName isPublic isServerless } } }'})
    if visibility.get('errors'):
        raise RuntimeError(str(visibility['errors']))
    records=[v for v in visibility['data']['myself']['podTemplates'] if v['id']==template['id']]
    if len(records)!=1 or records[0]['imageName']!=image or records[0]['isPublic'] is not False or records[0]['isServerless'] is not False:
        raise RuntimeError('Runpod did not confirm a private Pod template for the tested image')
    verified.update(isPublic=records[0]['isPublic'],isServerless=records[0]['isServerless'])
    local_template={key:verified.get(key) for key in ['id','name','imageName','isPublic','ports']}
    (ROOT/'work').mkdir(exist_ok=True)
    (ROOT/'work/runpod-template.json').write_text(json.dumps(local_template,indent=2)+'\n')
    config={'image':image,'template_name':NAME,
        'source_revision':validation['source_revision'],'validated':True,
        'validation_report':str(Path(args.validation).relative_to(ROOT)) if Path(args.validation).is_absolute() else args.validation,
        'default_gpu':'NVIDIA A40','container_disk_gb':100,'workspace_gb':40,
        'runtime_seconds':3600}
    (ROOT/'deploy/runtime.json').write_text(json.dumps(config,indent=2)+'\n')
    print(json.dumps({'release':config,'template':local_template},indent=2))


if __name__=='__main__':main()
