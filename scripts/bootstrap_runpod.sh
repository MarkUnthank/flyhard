#!/usr/bin/env bash
# Run inside the pinned Runpod Pod, from the Flyhard checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(id -u)" = 0
python3 -c 'import sys,torch; assert sys.version_info[:2] == (3,12); assert torch.__version__ == "2.8.0+cu128"; assert torch.cuda.is_available()'
apt-get update
apt-get install -y libegl1 libgl1 libopengl0 libgles2 libvulkan1 vulkan-tools mesa-utils xvfb rsync
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -c requirements/runpod-pilot.txt -e '.[body,dev]' carla==0.9.16
mkdir -p work
.venv/bin/pip freeze > work/environment.lock.txt
MUJOCO_GL=egl PYOPENGL_PLATFORM=egl .venv/bin/python -c 'import mujoco,torch; print(mujoco.__version__, torch.cuda.get_device_name(0))'
