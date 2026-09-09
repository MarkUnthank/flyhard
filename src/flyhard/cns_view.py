"""GPU rendering of measured MaleCNS anatomy with recorded model states."""
import hashlib
from pathlib import Path
import numpy as np
import pyvista as pv


class CNSView:
    def __init__(self, geometry_path, activity, width=600, height=440):
        data = np.load(geometry_path)
        self.point_neuron = data['point_neuron']
        self.indices = data['selected_indices']
        sample = np.abs(activity[::4, self.indices])
        # Use one fixed range per neuron for the entire episode. A single
        # shared range hides the weaker brain responses behind the VNC's
        # much larger engineered input values; zero states remain unlit.
        peaks = np.maximum(np.quantile(sample,0.95,axis=0),1e-5)
        all_scales = np.full(activity.shape[1],1e-5)
        all_scales[self.indices] = peaks
        self.point_scale = all_scales[self.point_neuron]
        self.scale = {'method':'Fixed per-neuron 95th percentile absolute state over the episode',
                      'floor':1e-5,'minimum':float(peaks.min()),'maximum':float(peaks.max()),
                      'comparable_between_neurons':False}
        self.plotter = pv.Plotter(off_screen=True, window_size=(width,height), lighting='three lights')
        self.plotter.set_background('#000000')
        self.plotter.enable_anti_aliasing('ssaa')
        geometry = Path(geometry_path)
        digest = hashlib.sha256(geometry.read_bytes()).hexdigest()
        display_path = geometry.with_name(f'roi-display-{digest[:16]}-90.vtp')
        if display_path.exists():
            surface = pv.read(display_path)
        else:
            faces = np.c_[np.full(len(data['roi_faces']),3),data['roi_faces']].ravel()
            surface = pv.PolyData(data['roi_vertices'],faces)
            surface = surface.decimate_pro(0.90,preserve_topology=True)
            surface.save(display_path)
        self.surface_sha256 = hashlib.sha256(display_path.read_bytes()).hexdigest()
        self.plotter.add_mesh(surface,color='#777777',opacity=0.025,
            smooth_shading=True,specular=0.1,ambient=0.3)
        edges = data['neurite_edges']
        self.cables = pv.PolyData(data['neurite_vertices'])
        self.cables.lines = np.c_[np.full(len(edges),2),edges].ravel()
        self.cables.point_data['state_rgb'] = np.full((len(self.point_neuron),3),74,dtype=np.uint8)
        self.plotter.add_mesh(self.cables,scalars='state_rgb',rgb=True,
            line_width=1.5,render_lines_as_tubes=False,lighting=False,show_scalar_bar=False)
        center = np.asarray(surface.center)
        self.plotter.camera_position = [center+[120,-1500,-30],center,[-0.75,0,-0.66]]
        self.plotter.camera.parallel_projection = True
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.15)
        self.plotter.show(auto_close=False,interactive=False)
        self.renderer_name = self.plotter.render_window.GetClassName()
        capabilities = self.plotter.render_window.ReportCapabilities()
        self.gpu_capabilities = '\n'.join(line for line in capabilities.splitlines()
            if 'OpenGL vendor' in line or 'OpenGL renderer' in line or 'OpenGL version' in line)
        assert 'NVIDIA' in self.gpu_capabilities, self.gpu_capabilities

    def render(self, state):
        rates = state[self.point_neuron]
        signed = (np.arcsinh(rates/(self.point_scale*0.05))/np.arcsinh(20)).clip(-1,1)
        destinations = np.where(signed[:,None] >= 0,[255,165,75],[76,176,255])
        colors = (np.array([74,74,74])+np.abs(signed[:,None])*(destinations-[74,74,74])).astype(np.uint8)
        self.cables.point_data['state_rgb'] = colors
        self.plotter.render()
        return self.plotter.screenshot(return_img=True)

    def close(self):
        self.plotter.close()
