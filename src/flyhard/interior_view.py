"""Camera registration between the supported fly rig and a CARLA cabin.

This is a visual placement only. The physical rig remains in millimetres.
CARLA uses X forward, Y right, Z up; the fly uses X forward, Y left, Z up.
"""
import numpy as np
import mujoco as mj


class InteriorFlyView:
    def __init__(self, rig, width, height, camera_matrix, wheel_anchor,
                 metres_per_rig_unit=0.20, horizontal_fov=90):
        self.rig = rig
        self.scale = float(metres_per_rig_unit)
        self.anchor = np.asarray(wheel_anchor,float)
        self.mirror = np.diag([1.,-1.,1.])
        self.width,self.height = width,height
        self.camera_matrix = np.asarray(camera_matrix,float)
        self.fov = horizontal_fov
        rig.model.vis.global_.offwidth = width
        rig.model.vis.global_.offheight = height
        # The CARLA seat and dashboard provide the environment. Hide the
        # standalone support platform only in the display model.
        rig.model.geom_group[rig.model.geom_bodyid == 0] = 5
        self.option = mj.MjvOption()
        self.option.geomgroup[5] = 0
        self.near = 0.01/self.scale
        self.far = 1000/self.scale
        rig.model.vis.map.znear = self.near/rig.model.stat.extent
        rig.model.vis.map.zfar = self.far/rig.model.stat.extent
        self.renderer = mj.Renderer(rig.model,height=height,width=width)

    def rig_to_car(self, points):
        return (np.asarray(points)-self.rig.center)@self.mirror.T*self.scale+self.anchor

    def update(self, data):
        self.renderer.update_scene(data,scene_option=self.option)
        scene = self.renderer.scene
        scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
        pose = self.camera_matrix
        position = self.rig.center+self.mirror@(pose[:3,3]-self.anchor)/self.scale
        forward = self.mirror@pose[:3,0]
        up = self.mirror@pose[:3,2]
        half_width = self.near*np.tan(np.deg2rad(self.fov)/2)
        half_height = half_width*self.height/self.width
        for camera in scene.camera:
            camera.pos[:] = position
            camera.forward[:] = forward
            camera.up[:] = up
            camera.orthographic = 0
            camera.frustum_near = self.near
            camera.frustum_far = self.far
            camera.frustum_center = 0
            camera.frustum_width = 2*half_width
            camera.frustum_top = half_height
            camera.frustum_bottom = -half_height

    def render(self, data, carla_rgb, carla_depth):
        self.update(data)
        rgb = self.renderer.render().copy()
        self.renderer.enable_depth_rendering()
        depth = self.renderer.render().copy()*self.scale
        self.renderer.disable_depth_rendering()
        self.renderer.enable_segmentation_rendering()
        segmentation = self.renderer.render().copy()
        self.renderer.disable_segmentation_rendering()
        mask = (segmentation[:,:,0] >= 0) & (depth < carla_depth)
        result = carla_rgb.copy()
        result[mask] = rgb[mask]
        return result,mask,depth

    def close(self):
        self.renderer.close()
