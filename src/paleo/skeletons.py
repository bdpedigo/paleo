from typing import Optional

import networkx as nx
import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from caveclient import CAVEclient

from .utils import get_nucleus_location


def skeletonize_sequence(
    graphs_by_state: dict,
    client: Optional[CAVEclient] = None,
    root_id: Optional[int] = None,
    root_point: Optional[np.ndarray] = None,
    level2_data: Optional[pd.DataFrame] = None,
):
    """Generate skeletons for a sequence of graphs."""
    try:
        from pcg_skel import pcg_skeleton_direct
    except (ImportError, ModuleNotFoundError):
        msg = (
            "Please install the `pcg_skel` package to use skeletonization features. "
            "This can be done by running `pip install pcg-skel` "
            "or `pip install paleo[skeleton]`."
        )
        raise ModuleNotFoundError(msg)

    if level2_data is None:
        used_nodes = set()
        for graph in graphs_by_state.values():
            used_nodes.update(graph.nodes())
        # TODO add code for getting it using existing tools
        used_nodes = np.array(list(used_nodes))
        level2_data = client.l2cache.get_l2data_table(used_nodes)

    if root_point is None:
        root_point = get_nucleus_location(root_id, client)

    skeletons_by_state = {}
    for state_id, graph in tqdm(graphs_by_state.items()):
        node_ids = pd.Index(list(graph.nodes()))
        vertices = level2_data.loc[
            node_ids, ["rep_coord_nm_x", "rep_coord_nm_y", "rep_coord_nm_z"]
        ].values
        edges = nx.to_pandas_edgelist(graph).values
        edges = np.vectorize(node_ids.get_loc)(edges)

        skeleton = pcg_skeleton_direct(vertices, edges, root_point=root_point)
        skeletons_by_state[state_id] = skeleton

    return skeletons_by_state
