"""Refresh packaged code while preserving every displaced workspace file.

Durable datasets, checkpoints, recordings, and sponsor assets are not touched.
The previous runtime's tracked files are backed up before a new image replaces
them. A receipt identifies both the image and the code actually in the workspace.
"""
import hashlib
import json
from pathlib import Path
import shutil
import time

SOURCE_PATHS = ['src', 'scripts', 'tests', 'requirements', 'docker', 'deploy', 'configs', 'assets/fonts',
                'pyproject.toml', 'README.md', 'LICENSE', 'THIRD_PARTY.md', 'AGENTS.md',
                'apps/website/scripts/export-livery.mjs', 'apps/website/scripts/apply-livery.py',
                'apps/website/src/lib/artwork-bounds.mjs', 'apps/website/LIVERY-EXPORT.md',
                'apps/mini-livery/README.md', 'apps/mini-livery/BarlowCondensed-OFL.txt']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(root):
    return {str(p.relative_to(root)): digest(p)
            for name in SOURCE_PATHS
            for p in ([root/name] if (root/name).is_file() else (root/name).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def sync_workspace(bundled, project, revision):
    runtime = project/'work/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    receipt_path = runtime/'workspace-source.json'
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    # During a restart of the same image, retain intentional iteration edits.
    refresh = previous.get('image_source_revision') != revision
    backup = project/'work/source-backups'/str(time.time_ns())
    packaged = source_hashes(bundled)
    replaced = []
    for name, expected in packaged.items():
        target = project/name
        if not refresh:
            continue
        if target.exists():
            if digest(target) == expected:
                continue
            saved = backup/name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            replaced.append(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled/name, target)
    # Retire files removed by a newer image, retaining their contents in backup.
    if refresh:
        for name in previous.get('packaged_sha256', {}).keys()-packaged.keys():
            target = project/name
            if target.is_file():
                saved = backup/name
                saved.parent.mkdir(parents=True, exist_ok=True)
                target.rename(saved)
                replaced.append(name)
    actual = source_hashes(project)
    receipt = {'image_source_revision': revision, 'packaged_sha256': packaged,
               'workspace_sha256': actual,
               'locally_modified': sorted(n for n in actual.keys() | packaged.keys() if actual.get(n) != packaged.get(n)),
               'added': sorted(actual.keys()-packaged.keys()),
               'missing': sorted(packaged.keys()-actual.keys()),
               'backup': str(backup) if replaced else None, 'backed_up_files': replaced,
               'observed_epoch': time.time()}
    receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt
