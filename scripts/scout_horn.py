#!/usr/bin/env python3
"""Check native scene framing and live sponsor placement before policy capture."""
import argparse,json,queue
from pathlib import Path
import carla
import numpy as np
from PIL import Image
from flyhard.horn_world import HornWorld
from flyhard.live_livery import verify_live_livery
from flyhard.shot_cameras import look_at
from flyhard.sponsor_view import SponsorView
from capture_horn import next_image


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--asset',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    manifest=verify_live_livery(args.asset,out);env=HornWorld();sponsor=None
    try:
        env.start('wait_then_green',7.2);pose=look_at([-7.8,-6.,4.2],[5.5,0.,1.5]);sensors=[];queues=[]
        for kind in ['rgb','depth']:
            bp=env.world.get_blueprint_library().find('sensor.camera.'+kind)
            for k,v in {'image_size_x':'1248','image_size_y':'960','fov':'65','sensor_tick':'0','lens_k':'0','lens_kcube':'0'}.items():bp.set_attribute(k,v)
            if kind=='rgb':
                bp.set_attribute('motion_blur_intensity','0');bp.set_attribute('exposure_compensation','-0.6')
            sensor=env.world.spawn_actor(bp,pose,attach_to=env.ego);q=queue.Queue();sensor.listen(q.put)
            env.actors.append(sensor);sensors.append(sensor);queues.append(q)
        bp=env.world.get_blueprint_library().find('sensor.camera.rgb')
        for k,v in {'image_size_x':'320','image_size_y':'240','fov':'35','sensor_tick':'0','exposure_compensation':'-0.6'}.items():bp.set_attribute(k,v)
        lamp=env.world.spawn_actor(bp,env.lamp_camera());q=queue.Queue();lamp.listen(q.put)
        env.actors.append(lamp);sensors.append(lamp);queues.append(q)
        for _ in range(40):
            frame=env.world.tick();images=[next_image(q,frame) for q in queues]
        arrays=[np.frombuffer(im.raw_data,np.uint8).reshape(im.height,im.width,4)[:,:,:3][:,:,::-1].copy() for im in images]
        raw,encoded,light_image=arrays;encoded=encoded.astype(float);depth=(encoded[:,:,0]+256*encoded[:,:,1]+65536*encoded[:,:,2])*(1000/16777215)
        box=env.ego.bounding_box.location;sponsor=SponsorView(args.asset,manifest,[box.x,box.y,box.z])
        relative=np.linalg.inv(env.ego.get_transform().get_matrix())@np.asarray(sensors[0].get_transform().get_matrix())
        image,count=sponsor.render(relative,65,raw,depth)
        Image.fromarray(raw).save(out/'native.png');Image.fromarray(image).save(out/'sponsored.png')
        Image.fromarray(light_image).save(out/'traffic-light.png')
        result={'status':'scene_scout_only','learned_policy_used':False,'scene':env.metadata(),
                'observation':env.observe().tolist(),'hero_attributes':env.ego.attributes,'sponsor_pixels':count}
        (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    finally:
        if sponsor:sponsor.close()
        env.close()


if __name__=='__main__':main()
