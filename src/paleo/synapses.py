import time

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from .utils import get_supervoxel_mappings


def get_mutable_synapses(
    root_id,
    edits,
    client,
    sides="both",
    synapse_table=None,
    remove_self=True,
    verbose=False,
    n_jobs=-1,
):
    """Get all synapses that could have been part of this `root_id` across all states."""
    # TODO is it worth parallelizing this function?

    # TODO could also be sped up by taking the union of L2 IDS that get used, then
    # doing a current get_roots on those, feeding that into synapse query

    if synapse_table is None:
        synapse_table = client.info.get_datastack_info()["synapse_table"]

    if sides == "both":
        sides = ["pre", "post"]
    elif sides == "pre":
        sides = ["pre"]
    elif sides == "post":
        sides = ["post"]

    # find all of the original objects that at some point were part of this neuron
    t = time.time()
    original_roots = client.chunkedgraph.get_original_roots(root_id)
    if verbose:
        print(f"Getting original roots took {time.time() - t:.2f} seconds")

    # now get all of the latest versions of those objects
    # this will likely be a larger set of objects than we started with since those
    # objects could have seen further editing, etc.
    t = time.time()
    latest_roots = client.chunkedgraph.get_latest_roots(original_roots)
    if verbose:
        print(f"Getting latest roots took {time.time() - t:.2f} seconds")

    tables = []
    for side in sides:
        if verbose:
            print(f"Querying synapse table for {side}-synapses...")

        # get the pre/post-synapses that correspond to those objects
        t = time.time()
        syn_df: pd.DataFrame = client.materialize.query_table(
            synapse_table,
            filter_in_dict={f"{side}_pt_root_id": latest_roots},
        )
        syn_df.set_index("id", inplace=True)
        if verbose:
            print(f"Querying synapse table took {time.time() - t:.2f} seconds")

        if remove_self:
            syn_df.query("pre_pt_root_id != post_pt_root_id", inplace=True)

        tables.append(syn_df)

    all_supervoxel_ids = []
    for i, side in enumerate(sides):
        table = tables[i]
        all_supervoxel_ids.append(table[f"{side}_pt_supervoxel_id"].unique())
    supervoxel_ids = np.unique(np.concatenate(all_supervoxel_ids))
    supervoxel_mappings = get_supervoxel_mappings(
        supervoxel_ids, edits, client, n_jobs=n_jobs
    )

    exploded_tables = []
    for i, side in enumerate(sides):
        table = tables[i]
        table[f"{side}_pt_level2_id"] = table[f"{side}_pt_supervoxel_id"].map(
            supervoxel_mappings
        )
        exploded_tables.append(table.explode(f"{side}_pt_level2_id"))

    if len(exploded_tables) == 1:
        return exploded_tables[0]
    else:
        return exploded_tables[0], exploded_tables[1]


def map_synapses_to_sequence(synapses: pd.DataFrame, nodes_by_state: dict, side="pre"):
    """Map synapses (with level2 node information) to a sequence of level2 nodes."""
    if f"{side}_pt_level2_id" not in synapses.columns:
        raise ValueError(
            f"The synapses dataframe must have a column '{side}_pt_level2_id' to map synapses to components."
        )
    synapses = synapses.reset_index(drop=False).set_index(f"{side}_pt_level2_id")
    synapse_ids_by_edit = {}
    for state_id, nodes in tqdm(nodes_by_state.items()):
        component_synapse_index = synapses.index.intersection(list(nodes))
        synapse_ids_at_state = (
            synapses.loc[component_synapse_index, "id"].unique().tolist()
        )
        synapse_ids_by_edit[state_id] = synapse_ids_at_state

    return synapse_ids_by_edit
