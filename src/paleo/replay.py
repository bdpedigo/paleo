from typing import Optional, Union

import networkx as nx
import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from .networkdelta import NetworkDelta


def apply_edit(graph: nx.Graph, networkdelta: NetworkDelta):
    """Apply the edit described by the networkdelta to the graph."""
    removed_edges = networkdelta.removed_edges
    removed_nodes = networkdelta.removed_nodes

    added_edges = networkdelta.added_edges
    added_nodes = networkdelta.added_nodes

    graph.add_nodes_from(added_nodes)
    graph.add_edges_from(added_edges)

    # NOTE: these do not error if the nodes or edges are not in the graph
    # may want to revisit that
    graph.remove_nodes_from(removed_nodes)
    graph.remove_edges_from(removed_edges)


def find_anchor_node(graph, anchor_nodes):
    """Find the first anchor node that is in the graph."""
    for anchor_node in anchor_nodes:
        if graph.has_node(anchor_node):
            return anchor_node
    return None


def resolve_edit(
    graph: nx.Graph,
    networkdelta: Optional[NetworkDelta],
    anchor_nodes: list,
):
    """Apply the edit described by the networkdelta and return the connected component
    containing the anchor node."""
    if networkdelta is not None:
        apply_edit(graph, networkdelta)
    anchor_node = find_anchor_node(graph, anchor_nodes)
    component = nx.node_connected_component(graph, anchor_node)
    return component


def apply_edit_sequence(
    graph: nx.Graph,
    edits: dict,
    anchor_nodes: Union[list, pd.Index, np.ndarray, pd.Series],
    return_graphs: bool = False,
    include_initial: bool = True,
    verbose: bool = True,
) -> Union[dict, tuple[dict, dict]]:
    """Apply a sequence of edits to the graph in order, storing information about
    intermediate states."""
    graph = graph.copy()
    if include_initial and -1 not in edits:
        edits = {-1: None, **edits}

    out = {}
    for edit_id, edit in tqdm(edits.items(), disable=not verbose):
        component = resolve_edit(graph, edit, anchor_nodes)
        if return_graphs:
            out[edit_id] = graph.subgraph(component).copy()
        else:
            out[edit_id] = component

    return out
