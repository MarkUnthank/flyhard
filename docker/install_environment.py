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
