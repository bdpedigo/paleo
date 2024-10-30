from typing import Optional

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from requests.exceptions import HTTPError
from tqdm_joblib import tqdm_joblib

from caveclient import CAVEclient

from .constants import TIMESTAMP_DELTA
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


def get_node_aliases(supervoxel_id, client, stop_layer=2) -> pd.DataFrame:
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
    nuc_table = client.info.get_datastack_info()["soma_table"]
    nuc_info = client.materialize.query_table(
        nuc_table, filter_equal_dict=dict(pt_root_id=root_id)
    )
    nuc_supervoxel_id = nuc_info["pt_supervoxel_id"].values[0]
    return nuc_supervoxel_id


def get_nodes_aliases(supervoxel_ids, client, stop_layer=2):
    if not isinstance(supervoxel_ids, list):
        supervoxel_ids = list(supervoxel_ids)

    # for all supervoxels, look up their level2 node now
    current_ts = client.timestamp
    node_ids = client.chunkedgraph.get_roots(
        supervoxel_ids, stop_layer=stop_layer, timestamp=current_ts
    )
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
    with tqdm_joblib(total=len(supervoxels_to_lookup)):
        historical_l2_ids = Parallel(n_jobs=-1)(
            delayed(lambda sv: get_node_aliases(sv, client).index.to_list())(sv)
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
