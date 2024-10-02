# %%
import datetime
from collections import namedtuple
from typing import Optional

import numpy as np
import pandas as pd
import pytz
from requests import HTTPError

from caveclient import CAVEclient
from paleo import get_level2_edits

client = CAVEclient("minnie65_phase3_v1")

root_id = 864691135639556411

change_log = client.chunkedgraph.get_tabular_change_log(root_id)[root_id]

change_log = pd.DataFrame(change_log).set_index("operation_id")

merge_id = change_log.index[0]
split_id = change_log.index[1]

# %%
details = client.chunkedgraph.get_operation_details([merge_id, split_id])

merge_details = details[str(merge_id)]
added_edges = details[str(merge_id)]["added_edges"]
nodes_affected = np.unique(np.concatenate([list(edge) for edge in added_edges]))
merge_row = change_log.loc[merge_id]
ts = merge_row["timestamp"]

timestamp = datetime.datetime.fromtimestamp(ts / 1000, pytz.UTC)
delta = datetime.timedelta(microseconds=1)

pre_l2_ids = client.chunkedgraph.get_roots(
    nodes_affected, stop_layer=2, timestamp=timestamp - delta
)
post_l2_ids = client.chunkedgraph.get_roots(
    nodes_affected, stop_layer=2, timestamp=timestamp + delta
)

# %%


NetworkDelta = namedtuple(
    "NetworkDelta",
    [
        "removed_nodes",
        "added_nodes",
        "removed_edges",
        "added_edges",
        "metadata",
    ],
)


def _get_changed_edges(
    before_edges: pd.DataFrame, after_edges: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    before_edges.drop_duplicates()
    before_edges["is_before"] = True
    after_edges.drop_duplicates()
    after_edges["is_before"] = False
    delta_edges = pd.concat([before_edges, after_edges]).drop_duplicates(
        ["source", "target"], keep=False
    )
    removed_edges = delta_edges.query("is_before").drop(columns=["is_before"])
    added_edges = delta_edges.query("~is_before").drop(columns=["is_before"])
    return removed_edges, added_edges


def _make_bbox(
    bbox_halfwidth: int, point_in_nm: np.ndarray, seg_resolution: np.ndarray
) -> np.ndarray:
    x_center, y_center, z_center = point_in_nm

    x_start = x_center - bbox_halfwidth
    x_stop = x_center + bbox_halfwidth
    y_start = y_center - bbox_halfwidth
    y_stop = y_center + bbox_halfwidth
    z_start = z_center - bbox_halfwidth
    z_stop = z_center + bbox_halfwidth

    start_point_cg = np.array([x_start, y_start, z_start]) / seg_resolution
    stop_point_cg = np.array([x_stop, y_stop, z_stop]) / seg_resolution

    bbox_cg = np.array([start_point_cg, stop_point_cg], dtype=int)
    return bbox_cg


def _get_level2_nodes_edges(
    root_id: int, client: CAVEclient, bounds: Optional[np.ndarray] = None
):
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

    nodes = pd.DataFrame(index=nodelist)

    if len(edgelist) == 0:
        edges = pd.DataFrame(columns=["source", "target"])
    else:
        edges = pd.DataFrame(edgelist, columns=["source", "target"])

    edges = edges.drop_duplicates(keep="first")

    return nodes, edges


def _get_all_nodes_edges(
    root_ids: list[int], client: CAVEclient, bounds: Optional[np.ndarray] = None
):
    all_nodes = []
    all_edges = []
    for root_id in root_ids:
        nodes, edges = _get_level2_nodes_edges(root_id, client, bounds=bounds)
        all_nodes.append(nodes)
        all_edges.append(edges)
    all_nodes = pd.concat(all_nodes, axis=0)
    all_edges = pd.concat(all_edges, axis=0, ignore_index=True)
    return all_nodes, all_edges


def get_level2_edits(
    operataion_ids: list[int],
    client: CAVEclient,
    verbose: bool = True,
    bounds_halfwidth: int = 20_000,
    metadata: bool = True,
) -> dict[int, NetworkDelta]:
    seg_resolution = client.chunkedgraph.base_resolution

    def _get_info_for_operation(operation_id):
        row = change_log.loc[operation_id]

        before_root_ids = row["before_root_ids"]
        after_root_ids = row["roots"]

        point_in_cg = np.array(row["sink_coords"][0])

        point_in_nm = point_in_cg * seg_resolution

        if bounds_halfwidth is None:
            bbox_cg = None
        else:
            bbox_cg = _make_bbox(bounds_halfwidth, point_in_nm, seg_resolution).T

        # grabbing the union of before/after nodes/edges
        # NOTE: this is where all the compute time comes from
        all_before_nodes, all_before_edges = _get_all_nodes_edges(
            before_root_ids, client, bounds=bbox_cg
        )
        all_after_nodes, all_after_edges = _get_all_nodes_edges(
            after_root_ids, client, bounds=bbox_cg
        )

        # finding the nodes that were added or removed, simple set logic
        added_nodes_index = all_after_nodes.index.difference(all_before_nodes.index)
        added_nodes = all_after_nodes.loc[added_nodes_index]
        removed_nodes_index = all_before_nodes.index.difference(all_after_nodes.index)
        removed_nodes = all_before_nodes.loc[removed_nodes_index]

        # finding the edges that were added or removed, simple set logic again
        removed_edges, added_edges = _get_changed_edges(
            all_before_edges, all_after_edges
        )

        # keep track of what changed
        if metadata:
            metadata_dict = {
                **row.to_dict(),
                "operation_id": operation_id,
                "root_id": root_id,
                "n_added_nodes": len(added_nodes),
                "n_removed_nodes": len(removed_nodes),
                "n_modified_nodes": len(added_nodes) + len(removed_nodes),
                "n_added_edges": len(added_edges),
                "n_removed_edges": len(removed_edges),
                "n_modified_edges": len(added_edges) + len(removed_edges),
            }
        else:
            metadata_dict = {}

        return NetworkDelta(
            removed_nodes,
            added_nodes,
            removed_edges,
            added_edges,
            metadata=metadata_dict,
        )

    networkdeltas_by_operation = {}
    for operation_id in operataion_ids:
        networkdeltas_by_operation[operation_id] = _get_info_for_operation(operation_id)

    return networkdeltas_by_operation


# %%

networkdeltas = get_level2_edits(root_id, client)

# %%
networkdeltas[merge_id].added_edges

# %%

split_details = details[str(split_id)]
removed_edges = split_details["removed_edges"]
split_row = change_log.loc[split_id]
x = split_row["timestamp"]

timestamp = datetime.datetime.fromtimestamp(x / 1000, pytz.UTC)
delta = datetime.timedelta(microseconds=1)

nodes_removed = np.unique(np.concatenate([list(edge) for edge in removed_edges]))

pre_l2_ids = client.chunkedgraph.get_roots(
    nodes_removed, stop_layer=2, timestamp=timestamp - delta
)
post_l2_ids = client.chunkedgraph.get_roots(
    nodes_removed, stop_layer=2, timestamp=timestamp + delta
)

# %%
pre_map = dict(zip(nodes_removed, pre_l2_ids))

# %%

removed_edges = np.array(removed_edges)
removed_l2_edges = np.vectorize(lambda x: pre_map[x])(removed_edges)


# %%
networkdeltas[split_id].removed_edges
