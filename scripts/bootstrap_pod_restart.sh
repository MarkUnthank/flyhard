#!/usr/bin/env bash
# Put back everything a pod restart wipes. The worktree lives on the pod's volume and
# survives; anything installed into the container image does not, so this has to be
# re-run after every restart before recording.
set -u
cd /workspace/flyhard

# The sponsor rasteriser needs a headless GL stack. pyrender 0.1.45 rather than 0.1.18,
# which pins networkx 2.2 and will not import on Python 3.12.
apt-get install -y -qq libglu1-mesa 2>&1 | tail -1 || \
  (apt-get update -qq && apt-get install -y -qq libglu1-mesa 2>&1 | tail -1)
/opt/flyhard-env/bin/pip install -q "pyrender==0.1.45" "pyglet==2.1.16" "trimesh==5.1.0" \
  "networkx==3.3" 2>&1 | grep -v "dependency resolver" | tail -2
# pyrender pins PyOpenGL 3.1.0, which is incompatible with numpy 2; 3.1.7 is not.
/opt/flyhard-env/bin/pip install -q "PyOpenGL==3.1.7" 2>&1 | grep -v "dependency resolver" | tail -1

./run.sh -c "
import pyglet; pyglet.options['shadow_window'] = False
import pyrender
r = pyrender.OffscreenRenderer(64, 64); print('pyrender offscreen ok'); r.delete()
"
# CARLA is started by the image's own entrypoint; check rather than assume.
pgrep -f CarlaUE4-Linux-Shipping > /dev/null && echo "carla running" || echo "CARLA NOT RUNNING"
