#!/usr/bin/env python3
"""Check the packaged GPU and CARLA, recording startup timing."""
import argparse
import json
from pathlib import Path
import time

def wait_for_carla(make_client, timeout=180, *, server_version='0.9.16', default_map=None, native=False):
    deadline=time.monotonic()+timeout
    while True:
        try:
            # A client created before the server listens can retain a failed
            # connection. Recreate it instead of retrying that same client.
            client=make_client('127.0.0.1',2000);client.set_timeout(10)
            world=client.get_world();version=client.get_server_version()
            if version != server_version:
                raise ValueError(f'Expected CARLA server {server_version}, received {version}')
            assert world.get_blueprint_library().find('vehicle.mini.cooper_s_2021')
            if default_map and world.get_map().name.rsplit('/', 1)[-1] != default_map:
                raise ValueError('CARLA started in a different map from its runtime manifest')
            if native and not world.get_blueprint_library().find('static.prop.mesh').has_attribute('movable'):
                raise ValueError('CARLA server is missing the native movable-accessory patch')
            return client,world,version
        except RuntimeError as exc:
            if time.monotonic()>=deadline:raise
            print('Waiting for CARLA: '+str(exc),flush=True)
            time.sleep(1)


def main():
    import carla
    import torch
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='work/runtime/ready.json')
    parser.add_argument('--started-epoch',type=float,required=True)
    parser.add_argument('--runtime-selection', type=Path,
                        help='Manifest selection written by the verified container startup')
    args=parser.parse_args()
    assert torch.__version__=='2.8.0+cu128' and torch.cuda.is_available()
    matrix=torch.arange(16,dtype=torch.float32,device='cuda').reshape(4,4)
    assert torch.equal((matrix@matrix).cpu(),matrix.cpu()@matrix.cpu())
    torch.cuda.synchronize()
    print('CUDA calculation passed; connecting to CARLA.',flush=True)
    selected = json.loads(args.runtime_selection.read_text()) if args.runtime_selection else None
    client,world,version=wait_for_carla(carla.Client,
        **({'server_version': selected['server_version'], 'default_map': selected['default_map'],
            'native': selected['kind'] == 'native'} if selected else {}))
    client_version = client.get_client_version()
    if client_version != (selected['client_version'] if selected else '0.9.16'):
        raise ValueError('CARLA client differs from the verified protocol version')
    now=time.time()
    result={'status':'ready','container_started_epoch':args.started_epoch,'ready_epoch':now,
        'container_to_ready_seconds':now-args.started_epoch,'gpu':torch.cuda.get_device_name(0),
        'torch':torch.__version__,'carla':version,'map':world.get_map().name,
        'cuda_kernel_check':'passed','installation_at_startup':False,
        'carla_client':client_version, 'runtime_asset':selected}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.tmp');temporary.write_text(json.dumps(result,indent=2));temporary.replace(output)


if __name__=='__main__':main()
