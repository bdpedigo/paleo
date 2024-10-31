---
title: Layout
hide:
  - navigation
  - toc
---

The diagram below describes some of the current functions in the `paleo` library, and
how they interact with each other. Note that you can click on anything underlined to be
taken to the corresponding reference documentation. The diagram is a work in progress and will
be updated as the library evolves.

```mermaid
---
config:
  layout: elk
  <!-- look: handDrawn -->
  theme: neutral
---
graph TD;
    get_root_level2_edits[/"`_get_root_level2_edits_`"/]
    get_operations_level2_edits[/"`_get_operations_level2_edits_`"/]
    get_metaedits[/"`_get_metaedits_`"/]
    apply_edit[/"`_apply_edit_`"/]
    get_initial_graph[/"`_get_initial_graph_`"/]
    resolve_edit[/"`_resolve_edit_`"/]
    get_nucleus_supervoxel[/"`_get_nucleus_supervoxel_`"/]
    get_mutable_synapses[/"`_get_mutable_synapses_`"/]
    get_used_node_ids[/"`_get_used_node_ids_`"/]
    get_node_aliases[/"`_get_node_aliases_`"/]
    get_level2_data_table[/"`_level2_data_table_`"/]
    apply_edit_sequence[/"`_apply_edit_sequence_`"/]
    skeletonize_sequence[/"`_skeletonize_sequence_`"/]
    map_synapses_to_sequence[/"`_map_synapses_to_sequence_`"/]
    append1[/"`_append_`"/]
    ???1[/"`_???_`"/]
    ???2[/"`_???_`"/]

    click get_root_level2_edits "../reference/#paleo.get_root_level2_edits"
    click get_operations_level2_edits "../reference/#paleo.get_operations_level2_edits"
    click get_metaedits "../reference/#paleo.get_metaedits"
    click apply_edit "../reference/#paleo.apply_edit"
    click get_initial_graph "../reference/#paleo.get_initial_graph"
    click resolve_edit "../reference/#paleo.resolve_edit"
    click get_nucleus_supervoxel "../reference/#paleo.get_nucleus_supervoxel"
    click get_mutable_synapses "../reference/#paleo.get_mutable_synapses"
    click map_synapses_to_sequence "../reference/#paleo.map_synapses_to_sequence"
    click get_used_node_ids "../reference/#paleo.get_used_node_ids"
    click get_node_aliases "../reference/#paleo.get_node_aliases"
    click get_level2_data_table "https://caveconnectome.github.io/CAVEclient/api/l2cache/#caveclient.l2cache.L2CacheClient.get_l2data_table"
    click apply_edit_sequence "../reference/#paleo.apply_edit_sequence"
    click skeletonize_sequence "../reference/#paleo.skeletonize_sequence"

    RootID-->get_root_level2_edits;
    get_root_level2_edits-->Deltas;

    OperationIDs-->get_operations_level2_edits;
    get_operations_level2_edits-->Deltas;

    Deltas-->get_metaedits;
    get_metaedits-->Metadeltas;

    RootID-->get_initial_graph;
    get_initial_graph-->InitialGraph

    Deltas-->AnyDelta{OR};
    Metadeltas-->AnyDelta{OR};
    AnyDelta-->apply_edit;

    get_nucleus_supervoxel-->NucleusSupervoxel;

    RootID-->get_node_aliases;
    NucleusSupervoxel-->get_node_aliases;
    get_node_aliases-->NucleusIDsOverTime;

    InitialGraph-->apply_edit

    NucleusIDsOverTime-->resolve_edit;

    RootID-->get_mutable_synapses;
    AnyDelta-->get_mutable_synapses;
    get_mutable_synapses-->SynapseTable;

    InitialGraph-->get_used_node_ids;
    AnyDelta-->get_used_node_ids;
    get_used_node_ids-->UsedNodes;
    UsedNodes-->get_level2_data_table;
    get_level2_data_table-->Level2DataTable;

    subgraph Repeat
        apply_edit_sequence[/"`_apply_edit_sequence_`"/]

        apply_edit-->UnresolvedGraph;
        UnresolvedGraph-->resolve_edit;
        resolve_edit-->ResolvedGraph;
    end

    ResolvedGraph-->append1;
    append1-->GraphsByState;

    GraphsByState-->skeletonize_sequence;
    Level2DataTable-->skeletonize_sequence;
    skeletonize_sequence-->SkeletonsByState;

    GraphsByState-->map_synapses_to_sequence;
    SynapseTable-->map_synapses_to_sequence;
    map_synapses_to_sequence-->SynapseIDsByState;

    SkeletonsByState-->???1;
    SynapseIDsByState-->???2;
```