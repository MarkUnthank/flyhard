#!/usr/bin/env python3
"""E01 graph audit. Retain every status=Traced neuron, with no edge threshold."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def reachability(matrix, inputs, outputs):
    active = np.zeros(matrix.shape[0], dtype=bool)
    active[inputs] = True
    first_output_step = None
    for step in range(1, 129):
        nxt = active | (matrix @ active.astype(np.float32) > 0)
        if first_output_step is None and np.any(nxt[outputs]):
            first_output_step = step
        if np.array_equal(nxt, active):
            break
        active = nxt
    return {'input_neurons': len(inputs), 'output_neurons': len(outputs),
            'reachable_neurons': int(active.sum()), 'reachable_outputs': int(active[outputs].sum()),
            'first_output_step': first_output_step, 'iterations': step}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='data/malecns-v1')
    parser.add_argument('--out', default='data/graph-traced-v1')
    args = parser.parse_args()
    folder, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    sources = json.loads((folder / 'sources.json').read_text())
    annotations = feather.read_table(folder / sources['files']['annotations']['filename'])
    mask = pc.fill_null(pc.equal(annotations['status'], 'Traced'), False)
    nodes = annotations.filter(mask).sort_by([('bodyId', 'ascending')])
    ids = nodes['bodyId'].to_numpy()
    assert len(ids) == len(np.unique(ids)) and len(ids) > 100_000
    feather.write_feather(nodes, out / 'nodes.feather')
    np.save(out / 'excluded_annotation_ids.npy', annotations.filter(pc.invert(mask))['bodyId'].to_numpy())
    predeclared = {'dataset': sources['dataset'], 'selection': "annotations.status == 'Traced'",
                  'reason': 'All traced neurons; exclude glia, incomplete fragments, anchors and unclassified segments.',
                  'edge_threshold': None, 'neuron_count': len(ids),
                  'published_headline_neuron_count': 166691,
                  'scope_note': 'This explicit annotation filter differs from the published headline census; not claimed to include every biological neuron.'}
    (out / 'selection.json').write_text(json.dumps(predeclared, indent=2))
    weights_path = folder / sources['files']['weights']['filename']
    assert sha(weights_path) == sources['files']['weights']['sha256']
    rows, cols, values, excluded_endpoints = [], [], [], []
    total_edges = total_synapses = 0
    with pa.memory_map(str(weights_path), 'r') as source:
        reader = pa.ipc.open_file(source)
        for batch_index in range(reader.num_record_batches):
            batch = reader.get_batch(batch_index)
            pre = batch['body_pre'].to_numpy()
            post = batch['body_post'].to_numpy()
            w = batch['weight'].to_numpy()
            assert np.all(w > 0)
            total_edges += len(w)
            total_synapses += int(w.sum())
            i = np.searchsorted(ids, pre)
            j = np.searchsorted(ids, post)
            pre_ok = (i < len(ids)) & (ids[np.minimum(i, len(ids)-1)] == pre)
            post_ok = (j < len(ids)) & (ids[np.minimum(j, len(ids)-1)] == post)
            keep = pre_ok & post_ok
            cols.append(i[keep].astype(np.int32))
            rows.append(j[keep].astype(np.int32))
            values.append(w[keep].astype(np.int64))
            excluded_endpoints.append(np.unique(np.concatenate([pre[~pre_ok], post[~post_ok]])))
            if batch_index % 300 == 0:
                print(json.dumps({'batch': batch_index, 'batches': reader.num_record_batches,
                                  'raw_edges_seen': total_edges}), flush=True)
    row = np.concatenate(rows)
    col = np.concatenate(cols)
    counts = np.concatenate(values)
    retained_before_sum = len(counts)
    graph = sp.coo_matrix((counts, (row, col)), shape=(len(ids), len(ids))).tocsr()
    graph.sum_duplicates()
    graph.sort_indices()
    assert graph.has_canonical_format and graph.nnz > 0
    assert int(graph.data.sum()) == int(counts.sum())
    excluded_ids = np.unique(np.concatenate(excluded_endpoints))
    np.save(out / 'excluded_connectivity_endpoint_ids.npy', excluded_ids)
    np.savez(out / 'graph.npz', crow=graph.indptr.astype(np.int64), col=graph.indices.astype(np.int64),
             counts=graph.data.astype(np.float32), body_ids=ids)
    classes = np.asarray(nodes['superclass'].fill_null('').to_pylist())
    motor = np.flatnonzero(classes == 'vnc_motor')
    components, labels = connected_components(graph, directed=True, connection='weak')
    in_degree = np.diff(graph.indptr)
    out_degree = np.bincount(graph.indices, minlength=len(ids))
    metrics = {**predeclared, 'annotation_rows': len(annotations), 'excluded_annotation_rows': len(annotations)-len(ids),
               'excluded_annotation_status_counts': dict(Counter(annotations.filter(pc.invert(mask))['status'].to_pylist())),
               'raw_segment_pair_rows': total_edges, 'raw_synapse_sum': total_synapses,
               'retained_pair_rows_before_aggregation': retained_before_sum, 'edges': graph.nnz,
               'retained_synapse_sum': int(graph.data.sum()), 'excluded_connectivity_endpoint_ids': len(excluded_ids),
               'weak_components': int(components), 'largest_weak_component': int(np.bincount(labels).max()),
               'isolated_neurons': int(((in_degree == 0) & (out_degree == 0)).sum()),
               'direction': 'CSR row=body_post, column=body_pre; incoming matrix times presynaptic state',
               'sensory_to_motor': {name: reachability(graph, np.flatnonzero(classes == name), motor)
                                   for name in ['ol_sensory', 'vnc_sensory']},
               'graph_sha256': sha(out / 'graph.npz'), 'sources': sources,
               'seconds': time.perf_counter()-start}
    (out / 'manifest.json').write_text(json.dumps(metrics, indent=2) + '\n')
    print(json.dumps({k:v for k,v in metrics.items() if k != 'sources'}, indent=2))


if __name__ == '__main__':
    main()
