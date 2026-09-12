"""Unreal 4.26 Python commandlet: import a verified native livery export.

Set FLYHARD_NATIVE_EXPORT to the directory made by export_native_livery.py.
This checks imported geometry before creating a receipt for the cook stage.
"""
import hashlib
import json
import os
from pathlib import Path
import re

import unreal


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector(v):
    return [v.x, v.y, v.z]


def save_checked(asset):
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('Unreal could not save asset: ' + asset.get_path_name())


def imported_mesh(file, destination, name, import_materials):
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', False)
    options.set_editor_property('import_materials', import_materials)
    options.set_editor_property('import_textures', import_materials)
    options.set_editor_property('automated_import_should_detect_type', False)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
    data = options.get_editor_property('static_mesh_import_data')
    for key, value in {'combine_meshes': True, 'auto_generate_collision': False,
                       'convert_scene': True, 'convert_scene_unit': True,
                       # UE4's default FBX convention preserves Blender world axes;
                       # forcing front X rotates these exports by 90 degrees.
                       'force_front_x_axis': False, 'generate_lightmap_u_vs': True,
                       'transform_vertex_to_absolute': True}.items():
        data.set_editor_property(key, value)
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(file), 'destination_path': destination,
                       'destination_name': name, 'automated': True,
                       'replace_existing': False, 'save': True, 'options': options}.items():
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = unreal.EditorAssetLibrary.load_asset(destination + '/' + name)
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError('FBX did not produce the expected StaticMesh: ' + name)
    unreal.EditorStaticMeshLibrary.remove_collisions(mesh)
    return mesh


def artwork_material(file, destination, name):
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(file), 'destination_path': destination,
                       'destination_name': 'T_' + name, 'automated': True,
                       'replace_existing': False, 'save': True}.items():
        task.set_editor_property(key, value)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    tools.import_asset_tasks([task])
    texture = unreal.EditorAssetLibrary.load_asset(destination + '/T_' + name)
    if not isinstance(texture, unreal.Texture2D):
        raise RuntimeError('Artwork texture import failed: ' + name)
    texture.set_editor_property('srgb', True)
    texture.set_editor_property('compression_no_alpha', False)
    material = tools.create_asset('M_' + name, destination, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('translucency_lighting_mode', unreal.TranslucencyLightingMode.TLM_SURFACE)
    material.set_editor_property('two_sided', False)
    editing = unreal.MaterialEditingLibrary
    sample = editing.create_material_expression(material, unreal.MaterialExpressionTextureSample, -400, 0)
    sample.set_editor_property('texture', texture)
    editing.connect_material_property(sample, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    editing.connect_material_property(sample, 'A', unreal.MaterialProperty.MP_OPACITY)
    roughness = editing.create_material_expression(material, unreal.MaterialExpressionConstant, -200, 200)
    roughness.set_editor_property('r', 0.65)
    editing.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS)
    editing.recompile_material(material)
    save_checked(texture)
    save_checked(material)
    return material


def main():
    source = Path(os.environ['FLYHARD_NATIVE_EXPORT'])
    receipt = json.loads((source / 'export-receipt.json').read_text())
    suffix = receipt['source_model_sha256'][:12]
    attempt = os.environ.get('FLYHARD_NATIVE_IMPORT_ATTEMPT', '')
    if attempt:
        if not re.fullmatch(r'[A-Za-z0-9_]+', attempt):
            raise RuntimeError('Import attempt label must contain only letters, numbers and underscores')
        suffix += '_' + attempt
    destination = '/Game/Flyhard/Livery/r{}_layout{}_{}'.format(receipt['revision'], receipt['layout'], suffix)
    if unreal.EditorAssetLibrary.does_directory_exist(destination):
        raise RuntimeError('Asset destination already exists; preserve it and inspect the previous import')
    result = []
    for entry in receipt['exports']:
        file = source / entry['file']
        if digest(file) != entry['sha256']:
            raise RuntimeError('FBX checksum mismatch: ' + file.name)
        mesh = imported_mesh(file, destination, entry['name'], not bool(entry['texture']))
        b = mesh.get_bounds()
        center, extent = vector(b.origin), vector(b.box_extent)
        observed = [[center[i] - extent[i] for i in range(3)],
                    [center[i] + extent[i] for i in range(3)]]
        original = entry['bounds_metres']
        expected = [[100 * original[0][0], -100 * original[1][1], 100 * original[0][2]],
                    [100 * original[1][0], -100 * original[0][1], 100 * original[1][2]]]
        error = max(abs(observed[j][i] - expected[j][i]) for j in range(2) for i in range(3))
        if error > 0.1:
            raise RuntimeError('Coordinate conversion mismatch for {}: observed {}, expected {}'.format(
                entry['name'], observed, expected))
        if entry['texture']:
            texture = source / entry['texture']
            if digest(texture) != entry['texture_sha256']:
                raise RuntimeError('Artwork checksum mismatch: ' + texture.name)
            material = artwork_material(texture, destination, entry['slot_id'].replace('-', ''))
            for index in range(len(mesh.get_editor_property('static_materials'))):
                mesh.set_material(index, material)
        save_checked(mesh)
        result.append({'mesh_path': mesh.get_path_name(), 'slot_id': entry['slot_id'],
                       'bounds_cm': observed, 'bounds_error_cm': error,
                       'source_fbx_sha256': entry['sha256'], 'source_texture_sha256': entry['texture_sha256']})
    output = {**receipt, 'status': 'Unreal import verified; cooking and CARLA verification pending',
              'native_asset_directory': destination, 'native_meshes': result,
              'engine_version': unreal.SystemLibrary.get_engine_version()}
    (source / 'unreal-import-receipt.json').write_text(json.dumps(output, indent=2) + '\n')
    unreal.log('FLYHARD_NATIVE_IMPORT_VERIFIED ' + destination)


main()
