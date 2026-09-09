#!/usr/bin/env python3
"""Calibrate fly display placement against native CARLA RGB and depth."""
import argparse
import hashlib
import json
from pathlib import Path

import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from flyhard.cockpit import WheelRig
from flyhard.interior_view import InteriorFlyView


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--survey', default='runs/interior-camera-survey-v1')
    parser.add_argument('--source', default='runs/carla-calm-v2')
    parser.add_argument('--anchor', type=float, nargs=3, default=[0.27,-0.41,1.03])
    parser.add_argument('--scale', type=float, default=0.20)
    parser.add_argument('--out', default='runs/interior-placement-v1')
    args = parser.parse_args()
    source, survey, out = Path(args.source), Path(args.survey), Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    metadata = json.loads((survey/'camera-survey.json').read_text())
    records = json.loads((source/'frames.json').read_text())
    record = records[100]
    with np.load(source/'body-trace.npz') as archive:
        body = {key:archive[key] for key in archive.files}
    rig = WheelRig(support_hand=True)
    data = mj.MjData(rig.model)
    bi = record['body_index']
    data.qpos[:] = body['qpos'][bi]
    data.qvel[:] = body['qvel'][bi]
    data.ctrl[:] = body['ctrl'][bi]
    data.time = body['time'][bi]
    mj.mj_forward(rig.model,data)
    font = ImageFont.truetype('assets/fonts/Geist.ttf',18)
    results = {}
    for name,view in metadata['views'].items():
        pose = np.linalg.inv(view['vehicle_world_matrix'])@view['camera_world_matrix']
        rgb = np.asarray(Image.open(survey/f'{name}.png'))
        native_depth = np.load(survey/f'{name}-depth.npy')
        renderer = InteriorFlyView(rig,metadata['width'],metadata['height'],pose,args.anchor,
            metres_per_rig_unit=args.scale,horizontal_fov=metadata['fov_horizontal'])
        result,mask,depth = renderer.render(data,rgb,native_depth)
        rendered = Image.fromarray(result)
        draw = ImageDraw.Draw(rendered)
        draw.rectangle((16,16,408,50),fill='#080808')
        draw.text((26,22),'Cabin camera + fly composite preview',font=font,fill='#eeeeee')
        rendered.save(out/f'{name}.png')
        Image.fromarray((mask*255).astype(np.uint8)).save(out/f'{name}-mask.png')
        renderer.close()
        results[name] = {'visible_fly_and_wheel_pixels':int(mask.sum()),
            'camera_car_matrix':pose.tolist(),'min_fly_depth_m':float(depth.min())}
        print(json.dumps({'view':name,**results[name]}),flush=True)
    report = {'native_fly':False,'purpose':'Static framing and depth-compositing calibration; cabin is a separate stationary survey.',
        'wheel_anchor_car_m':args.anchor,'metres_per_rig_unit':args.scale,
        'physical_wheel_radius_rig_units':rig.radius,'wheel_center_rig':rig.center.tolist(),
        'thorax_car_m':renderer.rig_to_car(data.body('nmf/c_thorax').xpos).tolist(),
        'source_body_time':float(data.time),'source_body_index':bi,'source_frame':record['frame'],
        'body_trace_sha256':hashlib.sha256((source/'body-trace.npz').read_bytes()).hexdigest(),
        'views':results}
    (out/'placement.json').write_text(json.dumps(report,indent=2))


if __name__ == '__main__':main()
