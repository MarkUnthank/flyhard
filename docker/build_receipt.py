"""Record the packaged runtime without requiring a GPU on the build runner."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

root = Path('/opt/flyhard')
packages = ['torch','numpy','carla','flygym','mujoco','pyvista','vtk','cloud-volume','trimesh']
receipt = {'source_revision':os.environ['FLYHARD_SOURCE_REVISION'],
    'packages':{p:importlib.metadata.version(p) for p in packages},
    'carla_archive_sha256':'09e3ebb28df17962f0c997e66f4b914ad5ea6f1d6a6dbbf13c9f87eb38346d57',
    'base_image':os.environ.get('FLYHARD_BASE_IMAGE','runpod/pytorch@sha256:4d1721e62b56d345c83b4fd6090664be6daf9312caab5b2e76f23d8231941851'),
    'runtime_layout':os.environ.get('FLYHARD_RUNTIME_LAYOUT','packaged'),
    'environment_sha256':hashlib.sha256((root/'environment.lock.txt').read_bytes()).hexdigest(),
    'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ['src','scripts','docker'] for p in sorted((root/folder).rglob('*'))
        if p.is_file() and p.suffix in ['.py','.sh']}}
(root/'build-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'packaged_versions':receipt['packages'],'source_revision':receipt['source_revision']}))
