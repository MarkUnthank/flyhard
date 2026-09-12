#!/usr/bin/env python3
"""Prepare, verify and promote pinned CARLA runtimes on a private volume.

Preparation records a candidate; it never declares simulator readiness. Promotion
rehashes the complete immutable tree and requires proof bound to that candidate.
Normal boots check the selected manifest digest and a bounded set of key files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import tarfile
import time

SCHEMA = 1
OFFICIAL_SHA256 = '09e3ebb28df17962f0c997e66f4b914ad5ea6f1d6a6dbbf13c9f87eb38346d57'
MANIFEST = 'runtime-manifest.json'
PROOF = 'runtime-proof.json'
LAUNCHER = 'CarlaUE4.sh'
EXECUTABLE = 'CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping'
IMPORT = 'flyhard-native-import.json'
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_BOOT_BYTES = 1024 * 1024 * 1024
MAX_BOOT_FILES = 256
IGNORED_FILES = {MANIFEST, PROOF, 'asset-receipt.json'}
MUTABLE = 'CarlaUE4/Saved'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid runtime-relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or value == '.' or '..' in path.parts or str(path) != value:
        raise ValueError('Runtime paths must be normalized and relative: ' + value)
    return value


def excluded(name):
    return name in IGNORED_FILES or name == MUTABLE or name.startswith(MUTABLE + '/')


def inside(root, name):
    path = root / relative_path(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Runtime path escapes its directory: ' + name)
    return path


def file_entry(root, path):
    name = path.relative_to(root).as_posix()
    inside(root, name)
    if path.is_symlink():
        target = os.readlink(path)
        if os.path.isabs(target) or not path.resolve().is_file():
            raise ValueError('Only internal file symlinks are supported: ' + name)
        return {'type': 'symlink', 'target': target}
    if not path.is_file():
        raise ValueError('Unsupported runtime entry: ' + name)
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Runtime changed during verification: ' + name)
    return {'type': 'file', 'bytes': before.st_size, 'sha256': digest,
            'executable': bool(before.st_mode & 0o111)}


def inventory(root):
    root = Path(root).resolve()
    files = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in list(dirs):
            path = parent / name
            rel = path.relative_to(root).as_posix()
            if excluded(rel):
                dirs.remove(name)
            elif path.is_symlink():
                files[rel] = file_entry(root, path)
                dirs.remove(name)
        for name in names:
            path = parent / name
            rel = path.relative_to(root).as_posix()
            if not excluded(rel):
                files[rel] = file_entry(root, path)
    return dict(sorted(files.items()))


def package_id(manifest):
    fields = {k: v for k, v in manifest.items()
              if k not in {'package_id', 'status', 'prepared_epoch', 'validation'}}
    return hashlib.sha256(json_bytes(fields)).hexdigest()


def validate_manifest(value):
    if value.get('schema_version') != SCHEMA or value.get('kind') not in {'official', 'native'}:
        raise ValueError('Unsupported runtime manifest')
    if value.get('status') not in {'candidate', 'verified'}:
        raise ValueError('Invalid runtime status')
    if not is_digest(value.get('package_id')) or value['package_id'] != package_id(value):
        raise ValueError('Runtime package identity mismatch')
    if value.get('launcher') != LAUNCHER or value.get('executable') != EXECUTABLE:
        raise ValueError('Unexpected CARLA entry point')
    if not isinstance(value.get('server_version'), str) or not value['server_version']:
        raise ValueError('Missing exact server version')
    if value.get('client_version') != '0.9.16':
        raise ValueError('Unverified CARLA client protocol')
    if not isinstance(value.get('default_map'), str) or not value['default_map']:
        raise ValueError('Missing default map')
    files = value.get('files')
    if not isinstance(files, dict) or not 2 <= len(files) <= 200000:
        raise ValueError('Invalid immutable file inventory')
    for name, entry in files.items():
        relative_path(name)
        if excluded(name):
            raise ValueError('Mutable/receipt file included in immutable inventory')
        if entry.get('type') == 'file':
            if (type(entry.get('bytes')) is not int or entry['bytes'] < 0
                    or not is_digest(entry.get('sha256')) or type(entry.get('executable')) is not bool):
                raise ValueError('Invalid file inventory entry: ' + name)
        elif entry.get('type') == 'symlink':
            if not isinstance(entry.get('target'), str) or os.path.isabs(entry['target']):
                raise ValueError('Invalid runtime symlink')
        else:
            raise ValueError('Invalid file type')
    boot = value.get('boot_files')
    required = {LAUNCHER, EXECUTABLE}
    if value['kind'] == 'native':
        required.add(IMPORT)
        native = value.get('native', {})
        if (value['default_map'] != 'Town03' or not is_digest(native.get('source_model_glb_sha256'))
                or not is_digest(native.get('import_receipt_sha256'))
                or type(native.get('actor_count')) is not int or native['actor_count'] < 1):
            raise ValueError('Incomplete native runtime identity')
    elif value.get('archive_sha256') != OFFICIAL_SHA256 or value['server_version'] != '0.9.16':
        raise ValueError('Official runtime does not match the pinned archive')
    if (not isinstance(boot, list) or len(boot) != len(set(boot))
            or not required.issubset(boot) or not 2 <= len(boot) <= MAX_BOOT_FILES):
        raise ValueError('Invalid bounded boot checks')
    if any(name not in files or files[name]['type'] != 'file' for name in boot):
        raise ValueError('Boot checks must refer to inventoried regular files')
    if sum(files[name]['bytes'] for name in boot) > MAX_BOOT_BYTES:
        raise ValueError('Boot checks exceed the one-GiB verification bound')
    if not files[LAUNCHER]['executable'] or not files[EXECUTABLE]['executable']:
        raise ValueError('CARLA entry points are not executable')
    if value['status'] == 'verified' and not is_digest(value.get('validation', {}).get('proof_sha256')):
        raise ValueError('Verified runtime is missing its bound proof')
    return value


def read_manifest(path, expected_sha256):
    path = Path(path)
    if not is_digest(expected_sha256) or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('Missing digest or oversized runtime manifest')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Selected runtime manifest digest mismatch')
    return validate_manifest(json.loads(raw))


def resolve(path, expected_sha256, *, allow_candidate=False, full=False):
    path = Path(path).resolve()
    value = read_manifest(path, expected_sha256)
    if value['status'] != 'verified' and not allow_candidate:
        raise RuntimeError('Candidate runtime requires explicit validation mode')
    root = path.parent
    if full:
        if inventory(root) != value['files']:
            raise RuntimeError('Immutable runtime tree differs from its manifest')
    else:
        for name in value['boot_files']:
            if file_entry(root, inside(root, name)) != value['files'][name]:
                raise RuntimeError('Runtime boot file differs from its manifest: ' + name)
    if value['status'] == 'verified':
        if sha256(inside(root, PROOF)) != value['validation']['proof_sha256']:
            raise RuntimeError('Runtime proof differs from its manifest')
    return {'manifest': str(path), 'manifest_sha256': expected_sha256,
            'package_id': value['package_id'], 'root': str(root),
            'kind': value['kind'], 'status': value['status'],
            'server_version': value['server_version'], 'client_version': value['client_version'],
            'default_map': value['default_map'], 'native': value.get('native')}


def write_candidate(root, value):
    root = Path(root).resolve()
    if (root / MANIFEST).exists():
        raise FileExistsError('Runtime already has a manifest; never overwrite a selected candidate')
    value.update(schema_version=SCHEMA, status='candidate', prepared_epoch=time.time(),
                 launcher=LAUNCHER, executable=EXECUTABLE, files=inventory(root))
    value['package_id'] = package_id(value)
    validate_manifest(value)
    raw = json_bytes(value)
    with (root / MANIFEST).open('xb') as stream:
        stream.write(raw)
    return resolve(root / MANIFEST, hashlib.sha256(raw).hexdigest(), allow_candidate=True)


def prepare_native(root, receipt_path):
    root = Path(root).resolve()
    receipt = json.loads(Path(receipt_path).read_text())
    if Path(receipt['runtime']).resolve() != root:
        raise ValueError('Package receipt identifies another runtime directory')
    if receipt.get('status') != 'cooked; packaged-runtime simulator verification pending':
        raise ValueError('Native package has not completed cooking')
    imported = json.loads((root / IMPORT).read_text())
    import_sha = sha256(root / IMPORT)
    if receipt.get('import_receipt_sha256') != import_sha:
        raise ValueError('Native import receipt hash differs from package receipt')
    for key in ['revision', 'layout', 'source_model_glb_sha256']:
        if receipt.get(key) != imported.get(key):
            raise ValueError('Native package/import identity mismatch: ' + key)
    native_files = receipt['native_files']
    asset_dir = imported['native_asset_directory'].removeprefix('/Game/')
    cooked_dir = 'CarlaUE4/Content/' + relative_path(asset_dir)
    for mesh in imported['native_meshes']:
        mesh_path = mesh['mesh_path']
        if not mesh_path.startswith(imported['native_asset_directory'] + '/'):
            raise ValueError('Native mesh lies outside its import namespace')
        name = mesh_path.rsplit('/', 1)[-1].split('.', 1)[0]
        if cooked_dir + '/' + name + '.uasset' not in native_files:
            raise ValueError('Native package receipt is missing an imported mesh')
    for name, expected in native_files.items():
        if (not name.startswith(cooked_dir + '/') or not is_digest(expected)
                or sha256(inside(root, name)) != expected):
            raise ValueError('Cooked native file differs from package receipt: ' + name)
    if sha256(root / EXECUTABLE) != receipt['shipping_executable_sha256']:
        raise ValueError('Shipping executable differs from package receipt')
    maps = receipt['maps']
    if '/Game/Carla/Maps/Town03' not in maps:
        raise ValueError('Native runtime must cook Town03')
    return write_candidate(root, {
        'kind': 'native', 'server_version': receipt['expected_server_version'],
        'client_version': receipt['client_version'], 'default_map': 'Town03', 'maps': maps,
        'package_receipt_sha256': sha256(receipt_path),
        'source': {key: receipt[key] for key in
                   ['carla_source', 'engine_source', 'patch_sha256', 'engine_lifecycle_patch_sha256']},
        'native': {'revision': imported['revision'], 'layout': imported['layout'],
                   'source_model_glb_sha256': imported['source_model_glb_sha256'],
                   'import_receipt_sha256': import_sha, 'actor_count': len(imported['native_meshes'])},
        'boot_files': sorted({LAUNCHER, EXECUTABLE, IMPORT, *native_files}),
    })


def official_archive_inventory(archive):
    if sha256(archive) != OFFICIAL_SHA256:
        raise ValueError('Official archive SHA-256 mismatch')
    files = {}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            name = member.name
            while name.startswith('./'):
                name = name[2:]
            if name in {'', '.'} or member.isdir():
                continue
            relative_path(name)
            if excluded(name):
                continue
            if name in files:
                raise ValueError('Duplicate archive entry: ' + name)
            if member.isfile() or member.islnk():
                digest = hashlib.sha256()
                stream = tar.extractfile(member)
                size = 0
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
                    size += len(chunk)
                files[name] = {'type': 'file', 'bytes': size,
                               'sha256': digest.hexdigest(), 'executable': bool(member.mode & 0o111)}
            elif member.issym():
                files[name] = {'type': 'symlink', 'target': member.linkname}
            else:
                raise ValueError('Unsupported official archive entry: ' + name)
    return dict(sorted(files.items()))


def prepare_official(root, archive):
    expected = official_archive_inventory(archive)
    if inventory(root) != expected:
        raise ValueError('Extracted official runtime differs from the pinned archive')
    return write_candidate(root, {'kind': 'official', 'archive_sha256': OFFICIAL_SHA256,
                                  'server_version': '0.9.16', 'client_version': '0.9.16',
                                  'default_map': 'Town10HD_Opt',
                                  'boot_files': [LAUNCHER, EXECUTABLE]})


def finite_number(value):
    return type(value) in {int, float} and math.isfinite(value)


def accept_proof(manifest, candidate_sha, proof, visual, proof_sha):
    expected = {'status': 'automated_checks_passed', 'runtime_mode': 'shipping',
                'runtime_manifest_sha256': candidate_sha,
                'carla_server_version': manifest['server_version'],
                'carla_client_version': manifest['client_version']}
    if any(proof.get(k) != v for k, v in expected.items()):
        raise ValueError('Simulator proof does not match this Shipping candidate')
    if proof.get('map', '').rsplit('/', 1)[-1] != manifest['default_map']:
        raise ValueError('Simulator proof used another map')
    if manifest['kind'] == 'official':
        if type(proof.get('rgb_frames_received')) is not int or proof['rgb_frames_received'] < 1:
            raise ValueError('Official runtime proof must receive a native RGB frame')
        return
    native = manifest['native']
    expected_native = {'revision': native['revision'], 'layout': native['layout'],
                       'native_actor_count': native['actor_count'],
                       'import_receipt_sha256': native['import_receipt_sha256'],
                       'physics_configuration_unchanged': True}
    if any(proof.get(k) != v for k, v in expected_native.items()):
        raise ValueError('Native simulator proof does not match the cooked livery')
    for key, low, high in [('peak_speed_m_s', 1, float('inf')),
                           ('max_attachment_position_error_m', 0, 0.002),
                           ('max_attachment_rotation_error', 0, 0.0002)]:
        value = proof.get(key)
        if not finite_number(value) or not low <= value <= high:
            raise ValueError('Native motion/attachment check failed: ' + key)
    comparisons = proof.get('camera_comparisons', [])
    required = {(view, sensor) for view in ['left-door', 'right-billboard', 'rear', 'front-roof']
                for sensor in ['rgb', 'depth']}
    if (len(comparisons) != len(required)
            or {(x.get('view'), x.get('sensor')) for x in comparisons} != required
            or any(not finite_number(x.get('changed_pixel_fraction'))
                   or not 0 < x['changed_pixel_fraction'] <= 1 for x in comparisons)):
        raise ValueError('Native RGB/depth comparisons are incomplete')
    if (not isinstance(visual, dict) or visual.get('status') != 'passed'
            or visual.get('runtime_manifest_sha256') != candidate_sha
            or visual.get('proof_sha256') != proof_sha):
        raise ValueError('Explicit visual review of this packaged proof is required')


def promote(path, expected_sha, proof_path, releases, visual_path=None):
    path = Path(path).resolve()
    manifest = read_manifest(path, expected_sha)
    if manifest['status'] != 'candidate':
        raise ValueError('Only a candidate can be promoted')
    proof_raw = Path(proof_path).read_bytes()
    proof_sha = hashlib.sha256(proof_raw).hexdigest()
    proof = json.loads(proof_raw)
    visual = json.loads(Path(visual_path).read_text()) if visual_path else None
    accept_proof(manifest, expected_sha, proof, visual, proof_sha)
    resolve(path, expected_sha, allow_candidate=True, full=True)
    releases = Path(releases).resolve()
    if releases.is_relative_to(path.parent):
        raise ValueError('Release directory must be outside the candidate tree')
    releases.mkdir(parents=True, exist_ok=True)
    destination = releases / manifest['package_id']
    if destination.exists():
        raise FileExistsError('Never overwrite a promoted runtime')
    # Rename on the same volume avoids a second multi-GB copy and ensures future
    # packaging cannot delete this release via its mutable Dist/ output path.
    root = path.parent
    root.rename(destination)
    try:
        proof_receipt = {'candidate_manifest_sha256': expected_sha, 'automated': proof,
                         'automated_sha256': proof_sha, 'visual_review': visual,
                         'verified_epoch': time.time(), 'full_tree_check': 'passed'}
        (destination / PROOF).write_bytes(json_bytes(proof_receipt))
        manifest['status'] = 'verified'
        manifest['validation'] = {'proof_sha256': sha256(destination / PROOF)}
        raw = json_bytes(manifest)
        temporary = destination / (MANIFEST + '.tmp')
        temporary.write_bytes(raw)
        temporary.replace(destination / MANIFEST)
    except BaseException:
        (destination / PROOF).unlink(missing_ok=True)
        (destination / (MANIFEST + '.tmp')).unlink(missing_ok=True)
        destination.rename(root)
        raise
    return resolve(destination / MANIFEST, hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    native = commands.add_parser('prepare-native')
    native.add_argument('--runtime', required=True, type=Path)
    native.add_argument('--package-receipt', required=True, type=Path)
    official = commands.add_parser('prepare-official')
    official.add_argument('--runtime', required=True, type=Path)
    official.add_argument('--archive', required=True, type=Path)
    for command in ['resolve', 'promote']:
        sub = commands.add_parser(command)
        sub.add_argument('--manifest', required=True, type=Path)
        sub.add_argument('--sha256', required=True)
        if command == 'resolve':
            sub.add_argument('--allow-candidate', action='store_true')
            sub.add_argument('--full', action='store_true')
        else:
            sub.add_argument('--proof', required=True, type=Path)
            sub.add_argument('--visual-review', type=Path)
            sub.add_argument('--releases', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'prepare-native':
        result = prepare_native(args.runtime, args.package_receipt)
    elif args.command == 'prepare-official':
        result = prepare_official(args.runtime, args.archive)
    elif args.command == 'resolve':
        result = resolve(args.manifest, args.sha256, allow_candidate=args.allow_candidate, full=args.full)
    else:
        result = promote(args.manifest, args.sha256, args.proof, args.releases, args.visual_review)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
