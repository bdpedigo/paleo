import warnings
from datetime import datetime
from typing import Collection, Optional, Union

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.sparse import csr_array
from scipy.sparse.csgraph import connected_components
from tqdm import TqdmExperimentalWarning

warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)

from tqdm.auto import tqdm
from tqdm_joblib import tqdm_joblib

from caveclient import CAVEclient

from .constants import TIMESTAMP_DELTA
from .networkdelta import NetworkDelta, combine_deltas
from .types import Graph, Integer, Number
from .utils import _get_level2_nodes_edges, _sort_edgelist


def _get_changed_edges(
    before_edges: np.ndarray, after_edges: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    before_edges = _sort_edgelist(before_edges)
    after_edges = _sort_edgelist(after_edges)

    before_edges = np.concatenate(
        (before_edges, np.zeros((before_edges.shape[0], 1), dtype=int)), axis=1
    )
    after_edges = np.concatenate(
        (after_edges, np.ones((after_edges.shape[0], 1), dtype=int)), axis=1
    )

    all_edges = np.concatenate((before_edges, after_edges), axis=0, dtype=int)
    unique_edges, index, edge_counts = np.unique(
        all_edges[:, :2], axis=0, return_counts=True, return_index=True
    )

    single_inverse = index[edge_counts == 1]
    single_edges = all_edges[single_inverse]

    removed_edges = single_edges[single_edges[:, 2] == 0][:, :2]
    added_edges = single_edges[single_edges[:, 2] == 1][:, :2]

    return removed_edges, added_edges


def _make_bbox(
    bbox_radius: Number, point_in_seg: np.ndarray, seg_resolution: np.ndarray
) -> np.ndarray:
    point_in_nm = point_in_seg * seg_resolution
    x_center, y_center, z_center = point_in_nm

    x_start = x_center - bbox_radius
    x_stop = x_center + bbox_radius
    y_start = y_center - bbox_radius
    y_stop = y_center + bbox_radius
    z_start = z_center - bbox_radius
    z_stop = z_center + bbox_radius

    start_point_cg = np.array([x_start, y_start, z_start]) / seg_resolution
    stop_point_cg = np.array([x_stop, y_stop, z_stop]) / seg_resolution

    bbox_cg = np.array([start_point_cg, stop_point_cg], dtype=int)
    return bbox_cg


def _get_all_nodes_edges(
    root_ids: Number, client: CAVEclient, bounds: Optional[np.ndarray] = None
) -> tuple[np.ndarray, np.ndarray]:
    all_nodes = []
    all_edges = []
    for root_id in root_ids:
        nodes, edges = _get_level2_nodes_edges(root_id, client, bounds=bounds)
        all_nodes.append(nodes)
        all_edges.append(edges)
    all_nodes = np.concatenate(all_nodes, dtype=int)
    all_edges = np.concatenate(all_edges, dtype=int)
    return all_nodes, all_edges


def get_detailed_change_log(
    root_id: int, client: CAVEclient, filtered: bool = True
) -> pd.DataFrame:
    """Get a detailed change log for a root ID.

    Parameters
    ----------
    root_id :
        The root ID to get the change log for.
    client :
        The CAVEclient instance to use.
    filtered :
        Whether to filter the change log to only include changes which affect the
        final state of the root ID.

    Returns
    -------
    :
        A detailed change log for the root ID.
    """
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


def _get_nodes_edges_from_graph(graph):
    if isinstance(graph, tuple):
        nodes, edges = graph
    else:
        nodes = np.unique(graph.flatten())
        edges = graph
    return nodes, edges


def compare_graphs(
    graph_before: Graph, graph_after: Graph, metadata=False
) -> NetworkDelta:
    """Compare two graphs and return the differences.

    Parameters
    ----------
    graph_before :
        The graph before the operation. Can either be a tuple of (nodes, edges) stored
        as `np.ndarrays`, or just the edges as an `np.ndarray`.
    graph_after :
        The graph after the operation. Can either be a tuple of (nodes, edges) stored
        as `np.ndarrays`, or just the edges as an `np.ndarray`.

    Returns
    -------
    :
        The differences between the two graphs.
    """

    nodes_before, edges_before = _get_nodes_edges_from_graph(graph_before)
    nodes_after, edges_after = _get_nodes_edges_from_graph(graph_after)

    removed_nodes = np.setdiff1d(nodes_before, nodes_after)
    added_nodes = np.setdiff1d(nodes_after, nodes_before)

    removed_edges, added_edges = _get_changed_edges(edges_before, edges_after)

    # keep track of what changed
    if metadata:
        metadata_dict = {
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


def get_operation_level2_edit(
    operation_id: int,
    client: CAVEclient,
    before_root_ids: Optional[Collection[int]] = None,
    after_root_ids: Optional[Collection[int]] = None,
    timestamp: Optional[datetime] = None,
    point: Optional[np.ndarray] = None,
    radius: Number = 20_000,
    metadata: bool = False,
) -> NetworkDelta:
    """Extract changes to the level2 graph for a specific operation.

    Parameters
    ----------
    operation_id :
        The operation ID to extract changes for.
    client :
        The CAVEclient instance to use.
    before_root_ids :
        The root ID(s) that were involved in the operation prior to it happening. If
        None, these will be looked up.
    after_root_ids :
        The root ID(s) that were created by the operation. If None, these will be
        looked up.
    timestamp :
        The timestamp of the operation. Only used if `before_root_ids` is not provided.
        If None, this will be looked up.
    point :
        The point to center the bounding box on. If None, will compare the entire
        level2 graphs of the objects before and after the operation.
    radius :
        The radius of the bounding box to use.
    metadata :
        Whether to include metadata about the changes in the output.

    Returns
    -------
    :
        The changes to the level2 graph from this operation.
    """
    if before_root_ids is None and timestamp is not None:
        maps = client.chunkedgraph.get_past_ids(
            after_root_ids, timestamp_past=timestamp - TIMESTAMP_DELTA
        )
        before_root_ids = []
        for root in after_root_ids:
            before_root_ids.extend(maps["past_id_map"][root])

    # if the point to center on is not provided, or if there is no list of ids that
    # came before this edit, then we need to look them up
    if (
        (point is None and radius is not None)
        or (after_root_ids is None)
        or (before_root_ids is None)  # implies timestamp is None because of the above
    ):
        details = client.chunkedgraph.get_operation_details([operation_id])[
            str(operation_id)
        ]
        if point is None:
            point = np.array(details["sink_coords"][0])
        if after_root_ids is None:
            after_root_ids = details["roots"]
        if before_root_ids is None:
            timestamp = datetime.fromisoformat(details["timestamp"])
            pre_timestamp = timestamp - TIMESTAMP_DELTA
            maps = client.chunkedgraph.get_past_ids(
                after_root_ids, timestamp_past=pre_timestamp
            )
            before_root_ids = []
            for root in after_root_ids:
                before_root_ids.extend(maps["past_id_map"][root])

    if radius is None:
        bbox_cg = None
    else:
        bbox_cg = _make_bbox(radius, point, client.chunkedgraph.base_resolution).T

    # grabbing the union of before/after nodes/edges
    # NOTE: this is where all the compute time comes from
    all_before_nodes, all_before_edges = _get_all_nodes_edges(
        before_root_ids, client, bounds=bbox_cg
    )
    all_after_nodes, all_after_edges = _get_all_nodes_edges(
        after_root_ids, client, bounds=bbox_cg
    )

    networkdelta = compare_graphs(
        (all_before_nodes, all_before_edges), (all_after_nodes, all_after_edges)
    )
    if metadata:
        networkdelta.metadata["operation_id"] = operation_id

    return networkdelta


def get_operations_level2_edits(
    operation_ids: Union[Collection[Integer], Integer],
    client: CAVEclient,
    radius: Number = 20_000,
    metadata: bool = False,
    n_jobs: int = -1,
    verbose: bool = True,
) -> dict[Integer, NetworkDelta]:
    """Extract changes to the level2 graph for a list of operations.


    Parameters
    ----------
    operation_ids :
        The operation ID(s) to extract changes for.
    client :
        The CAVEclient instance to use.
    radius :
        The radius of the bounding box to use.
    metadata :
        Whether to include metadata about the changes in the output.
    n_jobs :
        The number of jobs to run in parallel. If -1, will use all available cores.
    verbose :
        Whether to display a progress bar.

    Returns
    -------
    :
        The changes to the level2 graph from these operations
    """
    if isinstance(operation_ids, (int, np.integer)):
        operation_ids = [operation_ids]
    if not isinstance(operation_ids, list):
        try:
            operation_ids = list(operation_ids)
        except TypeError:
            raise TypeError(
                f"`operation_ids` could not be coerced to a list: {operation_ids}"
            )

    details_by_operation = client.chunkedgraph.get_operation_details(operation_ids)
    new_roots_by_operation = {
        int(operation_id): details["roots"]
        for operation_id, details in details_by_operation.items()
    }
    timestamps_by_operation = {
        int(operation_id): datetime.fromisoformat(details["timestamp"])
        for operation_id, details in details_by_operation.items()
    }

    inputs_by_operation = []
    for operation_id in operation_ids:
        inputs_by_operation.append(
            {
                "operation_id": operation_id,
                "client": client,
                "before_root_ids": None,
                "after_root_ids": new_roots_by_operation[operation_id],
                "timestamp": timestamps_by_operation[operation_id],
                "radius": radius,
                "metadata": metadata,
            }
        )
    if n_jobs != 1:
        with tqdm_joblib(
            total=len(inputs_by_operation),
            disable=not verbose,
            desc="Extracting level2 edits",
        ):
            networkdeltas = Parallel(n_jobs=-1)(
                delayed(get_operation_level2_edit)(**inputs)
                for inputs in inputs_by_operation
            )
    else:
        networkdeltas = []
        for inputs in tqdm(
            inputs_by_operation,
            disable=not verbose,
            desc="Extracting level2 edits",
        ):
            networkdeltas.append(get_operation_level2_edit(**inputs))

    networkdeltas = dict(zip(operation_ids, networkdeltas))
    return networkdeltas


def get_root_level2_edits(
    root_id: Integer,
    client: CAVEclient,
    radius: Number = 20_000,
    metadata: bool = False,
    filtered: bool = False,
    n_jobs: int = -1,
    verbose: bool = True,
) -> dict[Integer, NetworkDelta]:
    """Extract changes to the level2 graph for all operations on a root.

    Parameters
    ----------
    root_id :
        The root ID to extract changes for.
    client :
        The CAVEclient instance to use.
    radius :
        The radius of the bounding box to use.
    metadata :
        Whether to include metadata about the changes in the output.
    filtered :
        Whether to filter the change log to only include changes which affect the
        final state of the root ID.
    n_jobs :
        The number of jobs to run in parallel. If -1, will use all available cores.
    verbose :
        Whether to display a progress bar.

    Returns
    -------
    :
        The changes to the level2 graph from each operation
    """
    change_log = get_detailed_change_log(root_id, client, filtered=filtered)

    inputs_by_operation = []
    for operation_id, row in change_log.iterrows():
        inputs_by_operation.append(
            {
                "operation_id": operation_id,
                "client": client,
                "before_root_ids": row["before_root_ids"],
                "after_root_ids": row["roots"],
                "timestamp": None,  # not needed since we know roots before/after
                "radius": radius,
                "metadata": metadata,
            }
        )

    if n_jobs != 1:
        with tqdm_joblib(
            total=len(inputs_by_operation),
            disable=not verbose,
            desc="Extracting level2 edits",
        ):
            networkdeltas_by_operation = Parallel(n_jobs=-1)(
                delayed(get_operation_level2_edit)(**inputs)
                for inputs in inputs_by_operation
            )
    else:
        networkdeltas_by_operation = []
        for inputs in tqdm(
            inputs_by_operation,
            disable=not verbose,
            desc="Extracting level2 edits",
        ):
            networkdeltas_by_operation.append(get_operation_level2_edit(**inputs))

    networkdeltas_by_operation = dict(zip(change_log.index, networkdeltas_by_operation))

    return networkdeltas_by_operation


def get_metaedits(
    networkdeltas: dict[Integer, NetworkDelta],
) -> tuple[dict[Integer, NetworkDelta], dict[Integer, list[Integer]]]:
    """Combine edits into meta-edits based on shared nodes.

    Meta-edits are groups of one or more edits which affected a local region in the
    chunkedgraph. More specifically, they are defined as groups of edits which are
    connected components in a graph where nodes are edits and edges are shared nodes
    between edits.

    Parameters
    ----------
    networkdeltas :
        The changes to the level2 graph from each operation.

    Returns
    -------
    :
        The changes to the level2 graph from each meta-operation.
    :
        A mapping of meta-operation IDs to the operation IDs that make them up.

    """
    # find the nodes that are modified in any way by each operation
    mod_sets = {}
    for edit_id, delta in networkdeltas.items():
        mod_set = []
        mod_set += delta.added_nodes.tolist()
        mod_set += delta.removed_nodes.tolist()
        mod_set += delta.added_edges[:, 0].tolist()
        mod_set += delta.added_edges[:, 1].tolist()
        mod_set += delta.removed_edges[:, 0].tolist()
        mod_set += delta.removed_edges[:, 1].tolist()
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

    # meta-operations are connected components in the above graph
    _, labels = connected_components(product, directed=False)

    meta_operation_map = {}
    operation_map = {}
    for label in np.unique(labels):
        edits = node_edit_indicators.columns[labels == label].tolist()
        meta_operation_map[label] = edits
        for edit in edits:
            operation_map[edit] = label

    # for each meta-operation, combine the deltas of the operations that make it up
    networkdeltas_by_meta_operation = {}
    for meta_operation_id, operation_ids in meta_operation_map.items():
        meta_operation_id = int(meta_operation_id)
        deltas = [networkdeltas[operation_id] for operation_id in operation_ids]
        meta_networkdelta = combine_deltas(deltas)
        networkdeltas_by_meta_operation[meta_operation_id] = meta_networkdelta

    return networkdeltas_by_meta_operation, operation_map


def get_metadata_table(operation_ids=None, root_ids=None, client=None):
    """Retrieve metadata for a list of operations or root IDs.

    NOTE: aspirational, not yet implemented. To make this efficient, would probably need
    a server-side implementation

    Parameters
    ----------
    operation_ids : list of int, optional
        The operation IDs to retrieve metadata for.
    root_ids : list of int, optional
        The root IDs to retrieve metadata for.
    client : CAVEclient, optional
        The CAVEclient instance to use.

    Returns
    -------
    pd.DataFrame
        The metadata for the operations or root IDs. Metadata includes:

        - `operation_id`: The operation ID.
        - `timestamp`: The timestamp of the operation.
        - `location`: The approximate [x,y,z] centroid of the operation in nanometers.
        - `volume_added`: The volume added by the operation in cubic nanometers.
        - `volume_removed`: The volume removed by the operation in cubic nanometers.
        - `n_added_nodes`: The number of level2 nodes added by the operation.
        - `n_removed_nodes`: The number of level2 nodes removed by the operation.
        - `n_modified_nodes`: The number of level2 nodes modified by the operation.
        - `n_added_edges`: The number of level2 edges added by the operation.
        - `n_removed_edges`: The number of level2 edges removed by the operation.
        - `n_modified_edges`: The number of level2 edges modified by the operation.

    """
    raise NotImplementedError("This function is not yet implemented.")
