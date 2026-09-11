"""Rasterize the actual curved sponsor meshes and composite using CARLA depth."""
import math
from pathlib import Path

import numpy as np
from PIL import Image
import pyglet
pyglet.options['shadow_window'] = False
import pyrender
import trimesh


class SponsorView:
    def __init__(self, asset, manifest, native_center, width=1248, height=960):
        self.width, self.height = width, height
        self.scene = pyrender.Scene(bg_color=[0, 0, 0, 0], ambient_light=[.9, .9, .9])
        self.renderer = pyrender.OffscreenRenderer(width, height)
        with np.load(Path(asset) / 'render-panels.npz') as archive:
            offset = np.asarray(native_center) * [1, -1, 1] - archive['car_bounds'].mean(axis=0)
            if len(archive['structure_vertices']):
                vertices = archive['structure_vertices'] + offset
                structural = trimesh.Trimesh(vertices=vertices,
                    faces=np.arange(len(vertices)).reshape(-1, 3),
                    vertex_colors=(archive['structure_colors'] * 255).clip(0, 255).astype(np.uint8),
                    process=False)
                self.scene.add(pyrender.Mesh.from_trimesh(structural, smooth=False))
            for sponsor in manifest['sponsors']:
                key = sponsor['slotId']
                vertices = archive[key + '_vertices'] + offset
                uv = archive[key + '_uv']
                artwork = Image.open(Path(asset) / sponsor['texture']).convert('RGBA')
                visual = trimesh.visual.TextureVisuals(uv=uv, image=artwork)
                mesh = trimesh.Trimesh(vertices=vertices, faces=np.arange(len(vertices)).reshape(-1, 3), visual=visual, process=False)
                rendered = pyrender.Mesh.from_trimesh(mesh, smooth=False)
                for primitive in rendered.primitives:
                    primitive.material.alphaMode = 'BLEND'
                    primitive.material.doubleSided = True
                    primitive.material.metallicFactor = 0.
                    primitive.material.roughnessFactor = 1.
                self.scene.add(rendered)
        self.camera = pyrender.PerspectiveCamera(yfov=math.radians(60), znear=.05, zfar=1000.)
        self.node = self.scene.add(self.camera)

    def render(self, relative, fov, rgb, native_depth):
        relative = np.asarray(relative)
        reflect = np.diag([1, -1, 1])
        rotation = reflect @ relative[:3, :3]
        pose = np.eye(4)
        pose[:3, :3] = np.column_stack([rotation[:, 1], rotation[:, 2], -rotation[:, 0]])
        pose[:3, 3] = reflect @ relative[:3, 3]
        self.scene.set_pose(self.node, pose)
        self.camera.yfov = 2 * math.atan(math.tan(math.radians(fov) / 2) * self.height / self.width)
        rgba, depth = self.renderer.render(self.scene, flags=pyrender.RenderFlags.RGBA | pyrender.RenderFlags.FLAT)
        alpha = rgba[:, :, 3].astype(np.float32) / 255
        alpha *= (depth > 0) & (native_depth + .03 >= depth)
        result = (rgb * (1 - alpha[:, :, None]) + rgba[:, :, :3] * alpha[:, :, None]).clip(0, 255).astype(np.uint8)
        return result, int(np.count_nonzero(alpha > .01))

    def close(self):
        self.renderer.delete()
