#!/usr/bin/env python3
"""Independent on-Pod stop timer using Runpod's own injected Pod API key.

No account key is uploaded. The ordinary volume remains for recovery after stop.
The local budget guard separately polls credit and enforces the spending cap.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def pod_environment():
    return {k.decode(): v.decode() for entry in Path('/proc/1/environ').read_bytes().split(b'\0')
            if b'=' in entry for k, v in [entry.split(b'=', 1)]}


def request(method, path, payload=None):
    env = pod_environment()
    req = urllib.request.Request('https://api.runpod.io' + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + env['RUNPOD_API_KEY'],
                 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0 Flyhard/0.1'})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deadline', type=float, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    pod_id = pod_environment()['RUNPOD_POD_ID']
    p = request('GET', '/v2/pods/' + pod_id)
    assert p['id'] == pod_id
    print(json.dumps({'pod_id': pod_id, 'status': p['status'], 'deadline_epoch': args.deadline,
                      'credential': 'provider-injected pod key'}), flush=True)
    if args.check:
        return
    while time.time() < args.deadline:
        time.sleep(min(30, max(0, args.deadline - time.time())))
    while True:
        try:
            request('POST', '/v2/pods/' + pod_id + '/action', {'action': 'stop'})
            print('Deadline reached; stop requested', flush=True)
        except Exception as e:
            print('Stop request retry: ' + type(e).__name__, flush=True)
        time.sleep(15)


if __name__ == '__main__':
    main()
