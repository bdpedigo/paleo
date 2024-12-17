import warnings

import networkx as nx
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from tqdm import TqdmExperimentalWarning

warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)
from typing import Optional

from caveclient import CAVEclient
from tqdm.auto import tqdm
from tqdm_joblib import tqdm_joblib

from .utils import _get_level2_nodes_edges, _sort_edgelist


def get_initial_node_ids(root_id, client):
    lineage_g = client.chunkedgraph.get_lineage_graph(root_id, as_nx_graph=True)
    node_in_degree = pd.Series(dict(lineage_g.in_degree()))
    original_node_ids = node_in_degree[node_in_degree == 0].index
    return original_node_ids


def get_initial_graph(root_id, client, verbose=True, return_as="networkx", n_jobs=-1):
    """Get the initial graph for a given `root_id`, including objects that could become
    part of the neuron in the future."""
    if return_as not in ["networkx", "arrays"]:
        ValueError(f"`return_as` must be 'networkx' or 'arrays', got {return_as}")

    original_node_ids = get_initial_node_ids(root_id, client)

    def _get_info_for_node(leaf_id):
        nodes, edges = _get_level2_nodes_edges(leaf_id, client)
        return nodes, edges

    if n_jobs != 1:
        with tqdm_joblib(
            total=len(original_node_ids),
            disable=not verbose,
            desc="Getting initial graph",
        ):
            outs = Parallel(n_jobs=n_jobs)(
                delayed(_get_info_for_node)(leaf_id) for leaf_id in original_node_ids
            )
    else:
        outs = []
        for leaf_id in tqdm(original_node_ids):
            outs.append(_get_info_for_node(leaf_id))

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


def get_level2_data(graphs_by_state: dict, client: CAVEclient):
    used_nodes = set()
    for graph in graphs_by_state.values():
        used_nodes.update(graph.nodes())
    used_nodes = np.array(list(used_nodes))
    level2_data = client.l2cache.get_l2data_table(used_nodes)
    return level2_data


def get_level2_spatial_graphs(
    graphs_by_state: dict,
    client: Optional[CAVEclient] = None,
    level2_data=None,
    index_on=None,
):
    if level2_data is None and client is not None:
        level2_data = get_level2_data(graphs_by_state, client)
    elif level2_data is None:
        raise ValueError("Must provide either `level2_data` or `client`")
    
    if index_on is None:
        index_on = [
            "rep_coord_nm_x",
            "rep_coord_nm_y",
            "rep_coord_nm_z",
            "size_nm3",
            "area_nm2",
        ]
    keys = level2_data[index_on]
    keys = list(zip(*keys.values.T))
    key_mapping = dict(zip(level2_data.index, keys))

    spatial_graphs_by_state = {}
    for state_id, graph in graphs_by_state.items():
        spatial_graph = graph.copy()
        spatial_graph = nx.relabel_nodes(spatial_graph, key_mapping)
        spatial_graphs_by_state[state_id] = spatial_graph

    return spatial_graphs_by_state
