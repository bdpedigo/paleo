from typing import Optional, Union

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from requests import HTTPError
from scipy.sparse import csr_array
from scipy.sparse.csgraph import connected_components
from tqdm_joblib import tqdm_joblib

from caveclient import CAVEclient

from .networkdelta import NetworkDelta, combine_deltas

Number = Union[int, float, np.number]
Integer = Union[int, np.integer]


def get_detailed_change_log(
    root_id: int, client: CAVEclient, filtered: bool = True
) -> pd.DataFrame:
    cg = client.chunkedgraph
    change_log = cg.get_tabular_change_log(root_id, filtered=filtered)[root_id]

    change_log.set_index("operation_id", inplace=True)
    change_log.sort_values("timestamp", inplace=True)
    change_log.drop(columns=["timestamp"], inplace=True)

    chunk_size = 500  # not sure exactly what the limit is here
    details = {}
    for i in range(0, len(change_log), chunk_size):
        sub_details = cg.get_operation_details(
            change_log.index[i : i + chunk_size].to_list()
        )
        details.update(sub_details)
    assert len(details) == len(change_log)

    details = pd.DataFrame(details).T
    details.index.name = "operation_id"
    details.index = details.index.astype(int)

    change_log = change_log.join(details)

    return change_log


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
    bbox_halfwidth: Number, point_in_nm: np.ndarray, seg_resolution: np.ndarray
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
    root_ids: Number, client: CAVEclient, bounds: Optional[np.ndarray] = None
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
    root_id: Integer,
    client: CAVEclient,
    verbose: bool = True,
    bounds_halfwidth: Number = 20_000,
    metadata: bool = True,
) -> dict[Integer, NetworkDelta]:
    # TODO refactor this into CAVEclient
    change_log = get_detailed_change_log(root_id, client, filtered=False)
    filtered_change_log = get_detailed_change_log(root_id, client, filtered=True)
    change_log["is_filtered"] = False
    change_log.loc[filtered_change_log.index, "is_filtered"] = True

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

    with tqdm_joblib(
        total=len(change_log.index),
        disable=not verbose,
        desc="Extracting level2 edits",
    ):
        networkdeltas_by_operation = Parallel(n_jobs=-1)(
            delayed(_get_info_for_operation)(operation_id)
            for operation_id in change_log.index
        )

    networkdeltas_by_operation = dict(zip(change_log.index, networkdeltas_by_operation))

    return networkdeltas_by_operation


def get_metaedits(
    networkdeltas: dict[Integer, NetworkDelta],
) -> dict[Integer, NetworkDelta]:
    # find the nodes that are modified in any way by each operation
    mod_sets = {}
    for edit_id, delta in networkdeltas.items():
        mod_set = []
        mod_set += delta.added_nodes.index.tolist()
        mod_set += delta.removed_nodes.index.tolist()
        mod_set += delta.added_edges["source"].tolist()
        mod_set += delta.added_edges["target"].tolist()
        mod_set += delta.removed_edges["source"].tolist()
        mod_set += delta.removed_edges["target"].tolist()
        mod_set = np.unique(mod_set)
        mod_sets[edit_id] = mod_set

    # make an incidence matrix of which nodes are modified by which operations
    index = np.unique(np.concatenate(list(mod_sets.values())))
    node_edit_indicators = pd.DataFrame(
        index=index, columns=networkdeltas.keys(), data=False
    )
    for edit_id, mod_set in mod_sets.items():
        node_edit_indicators.loc[mod_set, edit_id] = True

    # this inner product matrix tells us which operations are connected with at least
    # one overlapping node in common
    X = csr_array(node_edit_indicators.values.astype(int))
    product = X.T @ X

    # meta-operations are connected components according to the above graph
    _, labels = connected_components(product, directed=False)

    meta_operation_map = {}
    for label in np.unique(labels):
        meta_operation_map[label] = node_edit_indicators.columns[
            labels == label
        ].tolist()

    # for each meta-operation, combine the deltas of the operations that make it up
    networkdeltas_by_meta_operation = {}
    for meta_operation_id, operation_ids in meta_operation_map.items():
        meta_operation_id = int(meta_operation_id)
        deltas = [networkdeltas[operation_id] for operation_id in operation_ids]
        meta_networkdelta = combine_deltas(deltas)
        networkdeltas_by_meta_operation[meta_operation_id] = meta_networkdelta

    return networkdeltas_by_meta_operation, meta_operation_map
