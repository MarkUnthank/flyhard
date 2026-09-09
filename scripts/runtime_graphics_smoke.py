#!/usr/bin/env python3
"""Validate MuJoCo and VTK on the packaged NVIDIA stack in separate processes."""
import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('engine',choices=['mujoco','vtk'])
    parser.add_argument('--out',default='runs/runtime-smoke')
    args=parser.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    import numpy as np
    if args.engine=='mujoco':
        import mujoco as mj
        from OpenGL import GL
        from PIL import Image
        from flyhard.cockpit import WheelRig
        rig=WheelRig(support_hand=True)
        for _ in range(100):rig.step(rig.neutral_actions)
        renderer=mj.Renderer(rig.model,width=640,height=480)
        camera=mj.MjvCamera();camera.lookat[:]=[.2,0,1.1]
        camera.distance=5.;camera.azimuth=155;camera.elevation=-20
        renderer.update_scene(rig.data,camera=camera)
        renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX]=False
        pixels=renderer.render().copy()
        device=GL.glGetString(GL.GL_RENDERER).decode()
        assert 'NVIDIA' in device and pixels.std()>1
        assert np.isfinite(rig.data.qpos).all()
        Image.fromarray(pixels).save(out/'mujoco.png');renderer.close()
        result={'engine':'mujoco','version':mj.__version__,'gpu_renderer':device,
            'body_count':rig.model.nbody,'simulated_body_seconds':rig.data.time}
    else:
        import pyvista as pv
        import vtk
        plotter=pv.Plotter(off_screen=True,window_size=(640,480))
        plotter.set_background('black');plotter.add_mesh(pv.Sphere(),color='orange')
        pixels=plotter.screenshot(out/'vtk.png',return_img=True)
        capabilities=plotter.render_window.ReportCapabilities()
        assert 'NVIDIA' in capabilities and pixels.std()>1
        assert plotter.render_window.GetClassName()=='vtkEGLRenderWindow'
        result={'engine':'vtk','version':vtk.vtkVersion.GetVTKVersion(),
            'window':plotter.render_window.GetClassName(),'gpu_capabilities':capabilities}
        plotter.close()
    result.update(status='passed',wall_seconds=time.perf_counter()-started,
        screenshot_sha256=hashlib.sha256((out/f'{args.engine}.png').read_bytes()).hexdigest())
    (out/f'{args.engine}.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':main()
