"""Resolve the project's declared extras once, at image build time."""
from pathlib import Path
import subprocess
import sys
import tomllib

root = Path('/opt/flyhard')
project = tomllib.loads((root/'pyproject.toml').read_text())['project']
requirements = list(project['dependencies'])
for extra in ['body','video','assets','simulator','dev']:
    requirements.extend(project['optional-dependencies'][extra])
subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir',
    '-c',str(root/'requirements/runpod-pilot.txt'),*requirements],check=True)
subprocess.run([sys.executable,'-m','pip','check'],check=True)
subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir','--no-deps',
    '-r',str(root/'requirements/video-rasterizer.txt')],check=True)
# Pyrender's stale exact PyOpenGL pin is intentionally overridden by the tested
# project-wide 3.1.10 constraint. Reject every other unresolved requirement.
check = subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True)
allowed = 'pyrender 0.1.45 has requirement pyopengl==3.1.0, but you have pyopengl 3.1.10.'
unexpected = [line for line in check.stdout.splitlines()
              if line.lower() != allowed and line != 'No broken requirements found.']
if unexpected or (check.returncode and not check.stdout.strip()) or check.stderr.strip():
    raise RuntimeError('Unexpected dependency check failure: '+check.stdout+check.stderr)
subprocess.run([sys.executable,'-c',
    "import pyglet; pyglet.options['shadow_window']=False; import pyrender, OpenGL; "
    "assert OpenGL.__version__ == '3.1.10'"],check=True)
