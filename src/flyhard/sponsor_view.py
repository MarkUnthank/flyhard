"""Rasterize the actual curved sponsor meshes and composite using CARLA depth.

The panels are rendered unlit so the delivered artwork reaches the screen as the
advertiser drew it. Two corrections make that true rather than nominal: pyrender
returns linear colour, which has to be encoded back to sRGB, and its ambient term
scales the result, which AMBIENT compensates for. EXPOSURE is checked against the
texture itself by scripts/check_sponsor_exposure.py, not guessed.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image
import pyglet
pyglet.options['shadow_window'] = False
import pyrender
import trimesh


AMBIENT = 2.4        # Compensates pyrender's ambient scaling of an unlit material.
EXPOSURE = 2.51      # Measured: cancels pyrender's residual scaling so the panel
                     # reproduces the delivered artwork's own values, no brighter.


class SponsorView:
    def __init__(self, asset, manifest, native_center, width=1248, height=960,
                 exposure=EXPOSURE):
        self.width, self.height = width, height
        self.exposure = float(exposure)
        self.scene = pyrender.Scene(bg_color=[0, 0, 0, 0],
                                    ambient_light=[AMBIENT, AMBIENT, AMBIENT])
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
        # sRGB re-encode as a lookup rather than a pow per pixel. pyrender hands back
        # 8-bit colour, so 256 entries cover every value it can produce and the table is
        # exact, not an approximation.
        levels = np.clip(np.arange(256, dtype=np.float32)/255*self.exposure, 0., 1.)
        self.encoded = 255*np.power(levels, 1/2.2)

    def render(self, relative, fov, rgb, native_depth):
        """Composite the panels onto one frame. Returns (frame, pixels covered).

        Two things keep this off the critical path of a recording. The sRGB encode is a
        table lookup rather than a pow per pixel, which is exact because the rasteriser's
        output is already 8 bit; and the blend runs only over the rectangle the panels
        actually cover, which is a few thousand pixels of a 1.2 megapixel frame. Together
        they took this from 94 ms a frame to single figures, and the result is identical
        to the full-frame float path it replaces.
        """
        relative = np.asarray(relative)
        reflect = np.diag([1, -1, 1])
        rotation = reflect @ relative[:3, :3]
        pose = np.eye(4)
        pose[:3, :3] = np.column_stack([rotation[:, 1], rotation[:, 2], -rotation[:, 0]])
        pose[:3, 3] = reflect @ relative[:3, 3]
        self.scene.set_pose(self.node, pose)
        self.camera.yfov = 2 * math.atan(math.tan(math.radians(fov) / 2) * self.height / self.width)
        rgba, depth = self.renderer.render(self.scene, flags=pyrender.RenderFlags.RGBA | pyrender.RenderFlags.FLAT)
        result = np.asarray(rgb).clip(0, 255).astype(np.uint8)
        drawn = np.nonzero(rgba[:, :, 3].any(axis=1))[0], np.nonzero(rgba[:, :, 3].any(axis=0))[0]
        if not len(drawn[0]):
            return result, 0
        box = (slice(drawn[0][0], drawn[0][-1]+1), slice(drawn[1][0], drawn[1][-1]+1))
        patch, near = rgba[box], depth[box]
        alpha = patch[:, :, 3].astype(np.float32) / 255
        alpha *= (near > 0) & (np.asarray(native_depth)[box] + .03 >= near)
        panels = self.encoded[patch[:, :, :3]]
        blended = (np.asarray(rgb)[box] * (1 - alpha[:, :, None])
                   + panels * alpha[:, :, None])
        result[box] = blended.clip(0, 255).astype(np.uint8)
        return result, int(np.count_nonzero(alpha > .01))

    def close(self):
        self.renderer.delete()
