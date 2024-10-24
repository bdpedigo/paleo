import warnings

import networkx as nx
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from tqdm import TqdmExperimentalWarning

warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)

from tqdm_joblib import tqdm_joblib

from .networkdelta import NetworkDelta
from .utils import _get_level2_nodes_edges, _sort_edgelist


def get_initial_node_ids(root_id, client):
    lineage_g = client.chunkedgraph.get_lineage_graph(root_id, as_nx_graph=True)
    node_in_degree = pd.Series(dict(lineage_g.in_degree()))
    original_node_ids = node_in_degree[node_in_degree == 0].index
    return original_node_ids


def get_initial_graph(root_id, client, verbose=True, return_as="networkx"):
    if return_as not in ["networkx", "arrays"]:
        ValueError(f"`return_as` must be 'networkx' or 'arrays', got {return_as}")

    original_node_ids = get_initial_node_ids(root_id, client)

    def _get_info_for_node(leaf_id):
        nodes, edges = _get_level2_nodes_edges(leaf_id, client)
        return nodes, edges

    with tqdm_joblib(
        total=len(original_node_ids), disable=not verbose, desc="Getting initial graph"
    ):
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

    if return_as == "networkx":
        graph = nx.Graph()
        graph.add_nodes_from(all_nodes)
        graph.add_edges_from(all_edges)
        return graph
    else:  # return_as == 'arrays'
        return all_nodes, all_edges


def apply_edit(graph: nx.Graph, networkdelta: NetworkDelta):
    removed_edges = networkdelta.removed_edges
    removed_nodes = networkdelta.removed_nodes

    added_edges = networkdelta.added_edges
    added_nodes = networkdelta.added_nodes

    # NOTE: these do not error if the nodes or edges are not in the graph
    # may want to revisit that
    graph.remove_nodes_from(removed_nodes)
    graph.remove_edges_from(removed_edges)

    graph.add_nodes_from(added_nodes)
    graph.add_edges_from(added_edges)
