from typing import Literal, Optional

import networkx as nx
import numpy as np
import pandas as pd
from caveclient import CAVEclient
from joblib import Parallel, delayed
from tqdm.auto import tqdm
from tqdm_joblib import tqdm_joblib

from .graph_edits import compare_graphs
from .networkdelta import NetworkDelta
from .utils import get_nucleus_location


def skeletonize_sequence(
    graphs_by_state: dict,
    client: Optional[CAVEclient] = None,
    root_id: Optional[int] = None,
    root_point: Optional[np.ndarray] = None,
    level2_data: Optional[pd.DataFrame] = None,
    remove_unchanged: bool = False,
    return_as: Literal["meshparty", "arrays", "networkx"] = "meshparty",
    n_jobs: int = -1,
    verbose: bool = True,
):
    """Generate skeletons for a sequence of graphs.

    Parameters
    ----------
    graphs_by_state :
        A dictionary mapping state IDs to NetworkX graphs.
    client :
        A CAVEclient instance.
    root_id :
        The ID of the root node, used to determine the root point for skeletonization if
        `root_point` is not provided.
    root_point :
        The root point for skeletonization. If not provided, it will be determined
        using the `root_id` and `client`.
    level2_data :
        The level 2 data table, containing the node coordinates in columns
        "rep_coord_nm_x", "rep_coord_nm_y", "rep_coord_nm_z".
    remove_unchanged :
        Whether to remove states with no changes from the previous state from the
        sequence.
    return_as :
        The format to return the skeletons in. Options are "meshparty", "arrays", and
        "networkx".
    n_jobs :
        The number of jobs to run in parallel. See joblib.Parallel for more details.
    verbose :
        Whether to display progress bars.
    """

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

    def _skeletonize_state(graph):
        node_ids = pd.Index(list(graph.nodes()))
        vertices = level2_data.loc[
            node_ids, ["rep_coord_nm_x", "rep_coord_nm_y", "rep_coord_nm_z"]
        ].values
        edges = nx.to_pandas_edgelist(graph).values
        edges = np.vectorize(node_ids.get_loc)(edges)

        skeleton = pcg_skeleton_direct(
            vertices, edges, root_point=root_point, collapse_soma=True
        )

        mapping = dict(zip(node_ids, skeleton.mesh_to_skel_map.tolist()))
        return skeleton, mapping

    if n_jobs != 1:
        with tqdm_joblib(
            desc="Skeletonizing states", disable=not verbose, total=len(graphs_by_state)
        ):
            results = Parallel(n_jobs=n_jobs)(
                delayed(_skeletonize_state)(graph) for graph in graphs_by_state.values()
            )
    else:
        results = [
            _skeletonize_state(graph)
            for graph in tqdm(
                graphs_by_state.values(),
                desc="Skeletonizing states",
                disable=not verbose,
                total=len(graphs_by_state),
            )
        ]

    if remove_unchanged:
        keep_state = check_skeleton_changes(
            {
                state_id: result[0]
                for state_id, result in zip(graphs_by_state.keys(), results)
            }
        )

    skeletons_by_state = {}
    mappings_by_state = {}
    for state_id, (skeleton, mapping) in zip(graphs_by_state.keys(), results):
        if remove_unchanged and not keep_state[state_id]:
            continue
        if return_as == "meshparty":
            pass
        elif return_as == "arrays":
            skeleton = (skeleton.vertices, skeleton.edges)
        elif return_as == "networkx":
            if len(skeleton.edges) > 0:
                new_skeleton = nx.from_edgelist(skeleton.edges.tolist())
            else:
                new_skeleton = nx.Graph()
                new_skeleton.add_nodes_from(list(range(len(skeleton.vertices))))
            positions = {}
            for i in range(len(skeleton.vertices)):
                positions[i] = {}
                positions[i]["x"] = skeleton.vertices[i][0].item()
                positions[i]["y"] = skeleton.vertices[i][1].item()
                positions[i]["z"] = skeleton.vertices[i][2].item()
            nx.set_node_attributes(new_skeleton, positions)
            skeleton = new_skeleton
        skeletons_by_state[state_id] = skeleton
        mappings_by_state[state_id] = mapping
    return skeletons_by_state, mappings_by_state


def compare_skeletons(
    skeleton1, skeleton2, return_as_spatial=False
) -> tuple[NetworkDelta, np.ndarray]:
    """Compare two skeletons, finding the network changes between them.

    Parameters
    ----------
    skeleton1 :
        The first skeleton to compare.
    skeleton2 :
        The second skeleton to compare.
    return_as_spatial : bool, optional
        Whether to return the changes in the original spatial coordinates, by default
        False.

    Returns
    -------
    :
        The changes between the two skeletons.
    :
        Array of the positions of all nodes referenced between the two skeletons. Note
        that the deltas are references to the positions in this array, unless they were
        already replaced if `return_as_spatial=True`.
    """
    # get positions of all of the nodes referenced between the two skeletons
    vertices1 = skeleton1.vertices
    index1 = pd.MultiIndex.from_arrays(vertices1.T)
    vertices2 = skeleton2.vertices
    index2 = pd.MultiIndex.from_arrays(vertices2.T)
    union_index: pd.MultiIndex = index1.union(index2)

    # reindex edges to be in this common reference frame
    vertices1_to_ids = union_index.get_indexer_for(index1)
    vertices2_to_ids = union_index.get_indexer_for(index2)
    edges1 = skeleton1.edges
    remapped_edges1 = np.vectorize(vertices1_to_ids.__getitem__, otypes=["int"])(edges1)
    edges2 = skeleton2.edges
    remapped_edges2 = np.vectorize(vertices2_to_ids.__getitem__, otypes=["int"])(edges2)

    # now can use the vanilla comparison function
    delta = compare_graphs(remapped_edges1, remapped_edges2)

    union_positions = union_index.to_frame().values

    # optionally, put things back in the original spatial coordinates
    # otherwise, the user can use union_index_array to do this themselves
    if return_as_spatial:
        delta.removed_nodes = union_positions[delta.removed_nodes]
        delta.added_nodes = union_positions[delta.added_nodes]
        delta.removed_edges = union_positions[delta.removed_edges]
        delta.added_edges = union_positions[delta.added_edges]

    return delta, union_positions


def check_skeleton_changes(skeletons_by_state: dict) -> dict:
    """Check if each skeleton in a sequence is different,
    compared to the one before it.

    Parameters
    ----------
    skeletons_by_state : dict
        A dictionary mapping state IDs to skeletons.

    Returns
    -------
    :
        A dictionary mapping state IDs to whether the skeleton is different from the
        previous one.
    """
    states = list(skeletons_by_state.keys())
    states_is_new = {states[0]: True}
    deltas = []
    for state1, state2 in zip(states, states[1:]):
        skeleton1 = skeletons_by_state[state1]
        skeleton2 = skeletons_by_state[state2]
        delta, _ = compare_skeletons(skeleton1, skeleton2)
        if not delta.is_empty:
            deltas.append(delta)
            states_is_new[state2] = True
        else:
            states_is_new[state2] = False
    return states_is_new
