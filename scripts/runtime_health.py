#!/usr/bin/env python3
"""Check the packaged GPU and CARLA, recording startup timing."""
import argparse
import json
from pathlib import Path
import time

import carla
import torch


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='work/runtime/ready.json')
    parser.add_argument('--started-epoch',type=float,required=True)
    args=parser.parse_args()
    assert torch.__version__=='2.8.0+cu128' and torch.cuda.is_available()
    matrix=torch.arange(16,dtype=torch.float32,device='cuda').reshape(4,4)
    assert torch.equal((matrix@matrix).cpu(),matrix.cpu()@matrix.cpu())
    torch.cuda.synchronize()
    client=carla.Client('127.0.0.1',2000);client.set_timeout(2)
    deadline=time.monotonic()+180
    while True:
        try:
            world=client.get_world();version=client.get_server_version()
            assert version=='0.9.16'
            assert world.get_blueprint_library().find('vehicle.mini.cooper_s_2021')
            break
        except RuntimeError:
            if time.monotonic()>=deadline:raise
            time.sleep(1)
    now=time.time()
    result={'status':'ready','container_started_epoch':args.started_epoch,'ready_epoch':now,
        'container_to_ready_seconds':now-args.started_epoch,'gpu':torch.cuda.get_device_name(0),
        'torch':torch.__version__,'carla':version,'map':world.get_map().name,
        'cuda_kernel_check':'passed','installation_at_startup':False}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.tmp');temporary.write_text(json.dumps(result,indent=2));temporary.replace(output)


if __name__=='__main__':main()
