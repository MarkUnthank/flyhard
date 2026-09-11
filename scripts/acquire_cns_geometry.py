#!/usr/bin/env python3
"""Fetch actual MaleCNS neuron skeletons and neuropil surfaces for the video."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

from cloudvolume import Mesh, Skeleton
import numpy as np
import pyarrow.feather as feather

BASE = 'https://storage.googleapis.com/flyem-male-cns'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', default='data/cns-geometry-v1')
    p.add_argument('--selection-trace', default='runs/carla-cockpit-v1/neural-trace.npz')
    p.add_argument('--selection-strength', help='Precomputed maximum absolute states plus original trace SHA; avoids transferring the full trace')
    p.add_argument('--selection-indices', help='Restore the exact previously exported neuron selection')
    p.add_argument('--selection-trace-sha', help='Original selection trace SHA for restored selections')
    args = p.parse_args()
    out = Path(args.out)
    cache = out/'raw'
    cache.mkdir(parents=True, exist_ok=True)
    sources = {}

    def fetch(url):
        key = hashlib.sha256(url.encode()).hexdigest()
        file = cache/key
        if not file.exists():
            request = urllib.request.Request(url, headers={'User-Agent':'Flyhard/0.1'})
            raw = urllib.request.urlopen(request, timeout=60).read()
            file.write_bytes(raw)
        raw = file.read_bytes()
        sources[url] = {'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)}
        return raw

    nodes = feather.read_table('data/graph-traced-v1/nodes.feather')
    body_ids = np.asarray(nodes['bodyId'])
    classes = np.asarray(nodes['superclass'].fill_null('').to_pylist())
    if args.selection_indices:
        assert args.selection_trace_sha and len(args.selection_trace_sha) == 64
        strength = np.zeros(len(body_ids))
        selection_sha = args.selection_trace_sha
    elif args.selection_strength:
        selection = np.load(args.selection_strength)
        strength = selection['max_abs_state']
        selection_sha = str(selection['trace_sha256'])
    else:
        previous_activity = np.load(args.selection_trace)['activity']
        strength = np.max(np.abs(previous_activity),axis=0)
        selection_sha = hashlib.sha256(Path(args.selection_trace).read_bytes()).hexdigest()
    rng = np.random.default_rng(40909)
    allocations = {'ol_intrinsic':112, 'cb_intrinsic':112, 'vnc_intrinsic':80,
        'vnc_sensory':48, 'vnc_motor':48, 'ascending_neuron':32,
        'descending_neuron':32, 'visual_projection':32, 'cb_sensory':16}
    selected = []
    for name,count in allocations.items():
        population = np.flatnonzero(classes == name)
        ranked = population[np.argsort(-strength[population],kind='stable')]
        top = ranked[:count//2]
        remainder = np.setdiff1d(population,top)
        chosen = np.r_[top,rng.choice(remainder,count-len(top),replace=False)]
        selected.extend(chosen.tolist())
    selected = np.asarray(sorted(set(selected)),dtype=np.int64)
    if args.selection_indices:
        selected = np.load(args.selection_indices)
        assert selected.ndim == 1 and len(selected) == 512
        assert np.all(np.diff(selected) > 0) and selected.min() >= 0 and selected.max() < len(body_ids)
    skel_root = BASE+'/v1.0/segmentation/skeletons-malecns/skeletons-precomputed/'
    info = json.loads(fetch(skel_root+'info'))

    def get_neuron(index):
        body_id = int(body_ids[index])
        # The source specifies physical nanometres and omits an optional
        # identity transform. Decode the published buffer directly.
        skeleton = Skeleton.from_precomputed(fetch(skel_root+str(body_id)),
            vertex_attributes=info.get('vertex_attributes',[])).downsample(4)
        return index,skeleton

    vertices,edges,point_neuron,edge_neuron = [],[],[],[]
    vertex_count = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for n,(index,skeleton) in enumerate(pool.map(get_neuron,selected)):
            vertices.append(skeleton.vertices.astype(np.float32)/1000)
            edges.append(skeleton.edges.astype(np.int64)+vertex_count)
            point_neuron.append(np.full(len(skeleton.vertices),index,dtype=np.int32))
            edge_neuron.append(np.full(len(skeleton.edges),index,dtype=np.int32))
            vertex_count += len(skeleton.vertices)
            if n % 64 == 0: print(json.dumps({'neurons_downloaded':n+1}),flush=True)

    roi_jobs = []
    for part,folder in [('brain','fullbrain-roi-v4'),('vnc','malecns-vnc-neuropil-roi-v0')]:
        root = BASE+'/rois/'+folder
        props = json.loads(fetch(root+'/segment_properties/info'))['inline']
        names = props['properties'][0]['values']
        for label,name in zip(props['ids'],names):
            roi_jobs.append((part,name,root+'/mesh/',label))

    def get_roi(job):
        part,name,root,label = job
        fragments = json.loads(fetch(root+label+':0'))['fragments']
        meshes = [Mesh.from_precomputed(fetch(root+urllib.parse.quote(fragment,safe=''))) for fragment in fragments]
        return part,name,Mesh.concatenate(*meshes)

    roi_vertices,roi_faces,roi_part = [],[],[]
    vertex_count = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for n,(part,name,mesh) in enumerate(pool.map(get_roi,roi_jobs)):
            roi_vertices.append(mesh.vertices.astype(np.float32)/1000)
            roi_faces.append(mesh.faces.astype(np.int64)+vertex_count)
            roi_part.append(np.full(len(mesh.faces),0 if part=='brain' else 1,dtype=np.uint8))
            vertex_count += len(mesh.vertices)
            if n % 24 == 0: print(json.dumps({'regions_downloaded':n+1}),flush=True)
    geometry = out/'geometry.npz'
    np.savez_compressed(geometry,neurite_vertices=np.concatenate(vertices),
        neurite_edges=np.concatenate(edges),point_neuron=np.concatenate(point_neuron),
        edge_neuron=np.concatenate(edge_neuron),selected_indices=selected,
        selected_body_ids=body_ids[selected],roi_vertices=np.concatenate(roi_vertices),
        roi_faces=np.concatenate(roi_faces),roi_part=np.concatenate(roi_part))
    manifest = {'dataset':'MaleCNS v1.0','source':'https://male-cns.janelia.org/download/',
        'license':'CC BY 4.0','coordinate_units':'micrometres; public physical nanometres divided by 1000',
        'neuron_selection':'Fixed class-stratified subset; half strongest states from prior calm run, half seeded random per class. Full model remains unchanged.',
        'selection_trace':args.selection_trace,
        'selection_trace_sha256':selection_sha,
        'allocations':allocations,'neuron_count':len(selected),'region_count':len(roi_jobs),
        'skeleton_downsampling':'Stride 4 using CloudVolume; branch endpoints preserved.',
        'geometry_sha256':hashlib.sha256(geometry.read_bytes()).hexdigest(),
        'sources':sources}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='sources'},indent=2),flush=True)


if __name__ == '__main__':
    main()
