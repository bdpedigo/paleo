from typing import Optional

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from requests.exceptions import HTTPError
from tqdm_joblib import tqdm_joblib

from caveclient import CAVEclient

from .types import Integer


def _sort_edgelist(edgelist: np.ndarray) -> np.ndarray:
    return np.unique(np.sort(edgelist, axis=1), axis=0)


def _get_level2_nodes_edges(
    root_id: Integer, client: CAVEclient, bounds: Optional[np.ndarray] = None
) -> tuple[np.ndarray, np.ndarray]:
    try:
        edgelist = client.chunkedgraph.level2_chunk_graph(root_id, bounds=bounds)
        nodelist = set()
        for edge in edgelist:
            for node in edge:
                nodelist.add(node)
        nodelist = list(nodelist)
    except HTTPError:
        # REF: https://github.com/seung-lab/PyChunkedGraph/issues/404
        nodelist = client.chunkedgraph.get_leaves(root_id, stop_layer=2)
        if len(nodelist) != 1:
            raise HTTPError(
                f"HTTPError: level 2 chunk graph not found for root_id: {root_id}"
            )
        else:
            edgelist = np.empty((0, 2), dtype=int)

    if len(edgelist) == 0:
        edgelist = np.empty((0, 2), dtype=int)
    else:
        edgelist = np.array(edgelist, dtype=int)

    edgelist = _sort_edgelist(edgelist)

    nodelist = np.array(nodelist, dtype=int)
    nodelist = np.unique(nodelist)

    return nodelist, edgelist


def get_initial_node_ids(root_id, client):
    lineage_g = client.chunkedgraph.get_lineage_graph(root_id, as_nx_graph=True)
    node_in_degree = pd.Series(dict(lineage_g.in_degree()))
    original_node_ids = node_in_degree[node_in_degree == 0].index
    return original_node_ids


def get_initial_network(root_id, client, positions=False, verbose=True):
    original_node_ids = get_initial_node_ids(root_id, client)

    def _get_info_for_node(leaf_id):
        nodes, edges = _get_level2_nodes_edges(leaf_id, client)
        return nodes, edges

    with tqdm_joblib(total=len(original_node_ids), disable=not verbose):
        outs = Parallel(n_jobs=-1)(
            delayed(_get_info_for_node)(leaf_id) for leaf_id in original_node_ids
        )
    all_nodes = []
    all_edges = []
    for out in outs:
        nodes, edges = out
        all_nodes.append(nodes)
        all_edges.append(edges)

    all_nodes = np.concatenate(all_nodes, axis=0)
    all_edges = np.concatenate(all_edges, axis=0)

    all_nodes = np.unique(all_nodes)
    all_edges = _sort_edgelist(all_edges)

    return all_nodes, all_edges
