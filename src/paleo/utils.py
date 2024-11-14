from typing import Optional, Union

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from requests.exceptions import HTTPError
from tqdm.auto import tqdm
from tqdm_joblib import tqdm_joblib

from caveclient import CAVEclient

from .constants import TIMESTAMP_DELTA
from .replay import resolve_edit
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


def get_node_aliases(
    supervoxel_id, client, stop_layer=2, return_as="list"
) -> Union[list, pd.DataFrame]:
    """For a given supervoxel, get the node that it was part of at `stop_layer` for
    each timestamp.
    """
    current_ts = client.timestamp

    node_id = client.chunkedgraph.get_roots(
        supervoxel_id, stop_layer=stop_layer, timestamp=current_ts
    )[0]
    oldest_ts = client.chunkedgraph.get_oldest_timestamp()

    node_info = []
    while current_ts > oldest_ts:
        created_ts = client.chunkedgraph.get_root_timestamps(node_id)[0]
        node_info.append(
            {
                "node_id": node_id,
                "start_valid_ts": created_ts,
                "end_valid_ts": current_ts,
            }
        )
        current_ts = created_ts - TIMESTAMP_DELTA
        node_id = client.chunkedgraph.get_roots(
            supervoxel_id, stop_layer=stop_layer, timestamp=current_ts
        )[0]

    node_info = pd.DataFrame(node_info).set_index("node_id")
    if return_as == "list":
        return node_info.index.to_list()
    elif return_as == "df":
        return node_info


# a version of the above that used the already computed edits to do the tracking

# current_timestamp = client.timestamp
# supervoxel_id = nuc_supervoxel_id

# level2_id = client.chunkedgraph.get_roots(supervoxel_id, stop_layer=2)[0]

# operation_id_added = None

# level2_id_info = []

# for operation_id, delta in tqdm(list(networkdeltas.items())[::-1], disable=True):
#     if level2_id in delta.added_nodes:
#         operation_id_added = operation_id
#         operation_added_ts = client.chunkedgraph.get_operation_details(
#             [operation_id_added]
#         )[str(operation_id_added)]["timestamp"]
#         operation_added_ts = datetime.fromisoformat(operation_added_ts)

#         level2_id_info.append(
#             {
#                 "level2_id": level2_id,
#                 "operation_id_added": operation_id_added,
#                 "start_valid_ts": operation_added_ts,
#                 "end_valid_ts": current_timestamp,
#             }
#         )

#         # get the new ID and continue to search backwards
#         pre_operation_added_ts = operation_added_ts - TIMESTAMP_DELTA
#         level2_id = client.chunkedgraph.get_roots(
#             nuc_supervoxel_id, stop_layer=2, timestamp=pre_operation_added_ts
#         )[0]
#         current_timestamp = pre_operation_added_ts


# level2_id_info.append(
#     {
#         "level2_id": level2_id,
#         "operation_id_added": None,
#         "start_valid_ts": None,
#         "end_valid_ts": current_timestamp,
#     }
# )
# pd.DataFrame(level2_id_info)


def get_component_masks(components: list[set]):
    """From a list of components, get a node by component boolean DataFrame of masks."""
    used_l2_nodes = np.unique(np.concatenate([list(c) for c in components]))
    l2_masks = pd.DataFrame(
        index=used_l2_nodes,
        data=np.zeros((len(used_l2_nodes), len(components)), dtype=bool),
    )
    for i, component in enumerate(components):
        l2_masks.loc[list(component), i] = True

    return l2_masks


def get_nucleus_supervoxel(root_id, client):
    """Get the supervoxel corresponding to the nucleus of a neuron by looking it up
    in the soma table."""
    nuc_table = client.info.get_datastack_info()["soma_table"]
    nuc_info = client.materialize.query_table(
        nuc_table, filter_equal_dict=dict(pt_root_id=root_id)
    )
    if len(nuc_info) == 0:
        raise ValueError(f"No nucleus found for root_id: {root_id}")
    elif len(nuc_info) > 1:
        raise ValueError(f"Multiple nuclei found for root_id: {root_id}")
    else:
        nuc_supervoxel_id = nuc_info["pt_supervoxel_id"].values[0]
    return nuc_supervoxel_id


def get_nodes_aliases(
    supervoxel_ids, client, stop_layer=2, verbose=True, return_as="list"
):
    """For a list of supervoxels, get all of the nodes at `stop_layer` that they were
    part of across time."""

    if not isinstance(supervoxel_ids, list):
        supervoxel_ids = list(supervoxel_ids)

    # for all supervoxels, look up their level2 node now
    current_ts = client.timestamp
    chunk_size = 50_000
    supervoxel_id_chunks = np.array_split(
        supervoxel_ids, len(supervoxel_ids) // chunk_size
    )
    node_ids_by_chunk = []
    for supervoxel_id_chunk in supervoxel_id_chunks:
        node_ids = client.chunkedgraph.get_roots(
            supervoxel_id_chunk, stop_layer=stop_layer, timestamp=current_ts
        )
        node_ids_by_chunk.append(node_ids)
    node_ids = np.concatenate(node_ids_by_chunk)
    node_to_supervoxel = pd.Series(index=node_ids, data=supervoxel_ids)
    node_to_supervoxel.index.name = "node_id"
    node_to_supervoxel.name = "supervoxel_id"

    # find out when they were made
    timestamps = client.chunkedgraph.get_root_timestamps(node_ids)
    node_timestamps = pd.Series(data=timestamps, index=node_ids)
    node_timestamps.index.name = "node_id"
    node_timestamps.name = "timestamp"

    # anything that was created at before oldest_ts we can ignore
    oldest_ts = client.chunkedgraph.get_oldest_timestamp()

    # everything else, we need to look up its history
    new_nodes = node_timestamps[node_timestamps > oldest_ts].index
    supervoxels_to_lookup = node_to_supervoxel.loc[new_nodes]

    # TODO this could be a bit faster if we wrote a smarter implementation since
    # some nodes may end up in the same history, don't think would be a huge speedup,
    # though
    with tqdm_joblib(total=len(supervoxels_to_lookup), disable=not verbose):
        historical_l2_ids = Parallel(n_jobs=-1)(
            delayed(lambda sv: get_node_aliases(sv, client))(sv)
            for sv in supervoxels_to_lookup
        )

    supervoxel_historical_l2_ids = {
        sv: l2s for sv, l2s in zip(supervoxels_to_lookup, historical_l2_ids)
    }
    # backfill the ones that we didnt have to go back in time for
    old_nodes = node_timestamps[node_timestamps <= oldest_ts].index
    old_supervoxels_to_nodes = (
        node_to_supervoxel.loc[old_nodes]
        .reset_index()
        .set_index("supervoxel_id")["node_id"]
    )
    old_supervoxels_to_nodes = old_supervoxels_to_nodes.apply(lambda x: [x])
    supervoxel_historical_l2_ids.update(old_supervoxels_to_nodes.to_dict())

    return supervoxel_historical_l2_ids


# TODO: I think this is another path to the above where you only have to check n_edits
# timepoints. Seemed like it could be faster but only by ~1/2
# stop_layer = 2
# # for all supervoxels, look up their level2 node now
# current_ts = client.timestamp
# node_ids = client.chunkedgraph.get_roots(
#     supervoxel_ids, stop_layer=stop_layer, timestamp=current_ts
# )
# node_to_supervoxel = pd.Series(index=node_ids, data=supervoxel_ids)
# node_to_supervoxel.index.name = "node_id"
# node_to_supervoxel.name = "supervoxel_id"

# # find out when they were made
# timestamps = client.chunkedgraph.get_root_timestamps(node_ids)
# node_timestamps = pd.Series(data=timestamps, index=node_ids)
# node_timestamps.index.name = "node_id"
# node_timestamps.name = "timestamp"

# # anything that was created at before oldest_ts we can ignore
# oldest_ts = client.chunkedgraph.get_oldest_timestamp()

# # everything else, we need to look up its history
# new_nodes = node_timestamps[node_timestamps > oldest_ts].index
# supervoxels_to_lookup = node_to_supervoxel.loc[new_nodes]

# from datetime import datetime
# from datetime import timedelta

# TIMESTAMP_DELTA = timedelta(microseconds=1)

# possible_timestamps = change_log["timestamp"]
# possible_timestamps = [datetime.fromisoformat(ts) for ts in possible_timestamps.values]

# # outs = []
# # for ts in tqdm(possible_timestamps[:10]):
# #     out = client.chunkedgraph.get_roots(
# #         supervoxels_to_lookup, stop_layer=2, timestamp=ts - TIMESTAMP_DELTA
# #     )
# #     outs.append(out)

# from joblib import Parallel, delayed
# from tqdm_joblib import tqdm_joblib

# with tqdm_joblib(total=len(possible_timestamps)):
#     outs = Parallel(n_jobs=-1)(
#         delayed(client.chunkedgraph.get_roots)(
#             supervoxels_to_lookup, stop_layer=2, timestamp=ts - TIMESTAMP_DELTA
#         )
#         for ts in possible_timestamps
#     )

# TODO: I think this is another alternative path but still have to lookup supervoxels
# def get_level2_lineage_components(networkdeltas_by_operation):
#     graph = nx.DiGraph()

#     for operation_id, delta in networkdeltas_by_operation.items():
#         for node1 in delta.removed_nodes:
#             for node2 in delta.added_nodes:
#                 graph.add_edge(node1, node2, operation_id=operation_id)

#     level2_lineage_components = list(nx.weakly_connected_components(graph))

#     level2_lineage_component_map = {}
#     for i, component in enumerate(level2_lineage_components):
#         for node in component:
#             level2_lineage_component_map[node] = i

#     level2_lineage_component_map = pd.Series(level2_lineage_component_map)

#     return level2_lineage_component_map


# level2_id_components = get_level2_lineage_components(networkdeltas)
# level2_id_components


def get_used_node_ids(initial_graph, edits, anchor_nodes):
    """Starting from an initial graph and a series of edits, get the nodes that are
    used in at least one state of the graph throughout its history.

    Parameters
    ----------
    initial_graph : nx.Graph
        The initial graph to start from.
    edits : dict
        A dictionary of edits where the key is the `operation_id` and the value is a
        `NetworkDelta` object.
    anchor_nodes : list
        A list of nodes that are on the object of interest, used to pick the connected
        component to consider at each point in the history.

    Returns
    -------
    :
        Nodes that are ever used in the history of the graph.
    """
    graph = initial_graph.copy()

    components = []
    subgraphs = []

    # remember to include the initial state
    edits = {-1: None, **edits}

    # after each edit, apply it and store the connected component for the nucleus node
    for edit_id, delta in edits.items():
        component = resolve_edit(graph, delta, anchor_nodes)
        components.append(component)

        subgraph = graph.subgraph(component).copy()
        subgraphs.append(subgraph)

    return np.unique(np.concatenate([list(c) for c in components]))


def get_changed_nodes(edits):
    """From a set of edits, get the nodes that have changed (added or removed)."""
    changed_nodes = []
    for _, edit in edits.items():
        if edit is not None:
            changed_nodes.extend(edit.added_nodes)
            changed_nodes.extend(edit.removed_nodes)
    return np.unique(changed_nodes)


def get_supervoxel_mappings(supervoxel_ids, edits, client, n_jobs=-1):
    """For a set of supervoxels and edits, get a mapping between the supervoxels and
    any level2 nodes they could have been part of across time."""
    # from our set of edits, get and level2 nodes that might have changed
    changed_nodes = get_changed_nodes(edits)

    # now, for all of those, look up supervoxels and see if they have any of the
    # supervoxels of interest
    def check_leaves(node):
        supervoxels = client.chunkedgraph.get_leaves(node)
        mask = np.isin(supervoxels, supervoxel_ids)
        return supervoxels[mask]

    with tqdm_joblib(desc="Getting leaves", total=len(changed_nodes)):
        leaves_by_l2 = Parallel(n_jobs=n_jobs)(
            delayed(check_leaves)(node) for node in changed_nodes
        )

    # store the mapping of supervoxels to level2 nodes that we got from looking at what
    # changed
    supervoxel_mappings = pd.Series(
        data=[[] for _ in range(len(supervoxel_ids))],
        index=supervoxel_ids,
        dtype=object,
    )
    for level2_id, leaf_supervoxel_ids in zip(changed_nodes, leaves_by_l2):
        for supervoxel_id in leaf_supervoxel_ids:
            supervoxel_mappings[supervoxel_id].append(level2_id)

    # anything without a mapping must not have changed
    unchanged_supervoxels = supervoxel_mappings[
        supervoxel_mappings.apply(len) == 0
    ].index

    # for those, simply look up their level2 nodes now
    chunk_size = 10000
    supervoxel_chunks = np.array_split(
        unchanged_supervoxels, len(unchanged_supervoxels) // chunk_size
    )
    for supervoxel_chunk in tqdm(supervoxel_chunks, desc="Getting remaining level2s"):
        level2_ids = client.chunkedgraph.get_roots(supervoxel_chunk, stop_layer=2)
        for supervoxel_id, level2_id in zip(supervoxel_chunk, level2_ids):
            supervoxel_mappings[supervoxel_id].append(level2_id)

    return supervoxel_mappings


def get_nucleus_location(root_id, client):
    nuc_table = client.info.get_datastack_info()["soma_table"]
    nuc_info = client.materialize.query_table(
        nuc_table, filter_equal_dict=dict(pt_root_id=root_id)
    )
    nuc_loc = nuc_info["pt_position"].values[0]
    return nuc_loc
