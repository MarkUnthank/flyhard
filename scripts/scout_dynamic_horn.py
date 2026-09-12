#!/usr/bin/env python3
"""Native scene/framing diagnostic using BasicAgent steering, not a learned run."""
import argparse
import json
from pathlib import Path
import queue

import carla
import numpy as np
from PIL import Image

from flyhard.dynamic_horn_world import DynamicHornWorld
from flyhard.live_livery import verify_live_livery
from flyhard.shot_cameras import look_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seconds', type=float, default=12.)
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=False)
    verify_live_livery(args.asset, out)
    env = DynamicHornWorld()
    try:
        env.start(args.kind)
        bp = env.world.get_blueprint_library().find('sensor.camera.rgb')
        for k, v in {'image_size_x':'936','image_size_y':'720','fov':'65',
                     'motion_blur_intensity':'0','exposure_compensation':'-0.6'}.items():
            bp.set_attribute(k, v)
        side = 1 if args.kind == 'cut_in_cross' else -1
        camera = env.world.spawn_actor(bp, look_at([-9.,side*6.5,4.8],[7.,0.,1.2]), attach_to=env.ego)
        env.actors.append(camera); inbox = queue.Queue(); camera.listen(inbox.put)
        env.release(); rows=[]
        for i in range(round(args.seconds*60)):
            t=i/60
            # A disclosed diagnostic cue releases the lead; this scout has no fly.
            request=env.step_traffic(t,4.8,env.green_released and t>5.4)
            env.apply_measured(request*1.7)
            frame=env.world.tick()
            while True:
                im=inbox.get(timeout=30)
                if im.frame>=frame:break
            observed=env.observed(request)
            row={'t':t,'observed':observed.tolist(),
                 'ego':[env.ego.get_location().x,env.ego.get_location().y],
                 'traffic':[[v['actor'].get_location().x,v['actor'].get_location().y,v['actor'].get_velocity().length()] for v in env.traffic],
                 'brake':env.last_control.brake,'steer':env.last_control.steer}
            rows.append(row)
            if i%60==0:
                pixels=np.frombuffer(im.raw_data,np.uint8).reshape(im.height,im.width,4)[:,:,:3][:,:,::-1]
                Image.fromarray(pixels).save(out/f'frame-{i:04d}.jpg')
            if i%120==0:print(json.dumps(row),flush=True)
        (out/'scene.json').write_text(json.dumps({'diagnostic':'BasicAgent steering; no learned fly controls',
                'metadata':env.metadata(),'frames':rows,'collisions':env.collision_events},indent=2)+'\n')
    finally:
        env.close()


if __name__=='__main__':main()
