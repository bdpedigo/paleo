import time

import pandas as pd


def get_all_time_synapses(
    root_id, client, synapse_table=None, remove_self=True, verbose=False
):
    # TODO is it worth parallelizing this?
    if synapse_table is None:
        synapse_table = client.info.get_datastack_info()["synapse_table"]

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
    for side in ["pre", "post"]:
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
            syn_df = syn_df.query("pre_pt_root_id != post_pt_root_id")

        tables.append(syn_df)

    return (tables[0], tables[1])
