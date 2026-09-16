"""Guard the bundled USD startup script when its optional exporter is disabled."""
import hashlib
import json
from pathlib import Path

root = Path('/workspace/flyhard-build')
path = root / 'UnrealEngine_4.26/Engine/Plugins/Importers/USDImporter/Content/Python/init_unreal.py'
source = path.read_text()
original = 'and unreal.StaticMeshExporterUsd.is_usd_available()'
patched = 'and hasattr(unreal, "StaticMeshExporterUsd") ' + original
if patched not in source:
    if source.count(original) != 1:
        raise RuntimeError('Unexpected pinned USD startup script; inspect before patching')
    result = source.replace(original, patched)
    path.write_text(result)
    receipt = {'path': str(path), 'reason': 'Python startup runs even when USDImporter is disabled',
               'original_sha256': hashlib.sha256(source.encode()).hexdigest(),
               'patched_sha256': hashlib.sha256(result.encode()).hexdigest()}
    (root / 'editor-python-patch.json').write_text(json.dumps(receipt, indent=2) + '\n')
