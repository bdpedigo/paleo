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
  look: handDrawn
  theme: neutral
---
graph TD;
    get_root_level2_edits[/"`_get_root_level2_edits_`"/]
    get_operations_level2_edits[/"`_get_operations_level2_edits_`"/]
    get_detailed_change_log[/"`_get_detailed_change_log_`"/]
    get_metaedits[/"`_get_metaedits_`"/]
    apply_edit[/"`_apply_edit_`"/]
    get_initial_graph[/"`_get_initial_graph_`"/]
    resolve_edit[/"`_resolve_edit_`"/]
    get_nucleus_supervoxel[/"`_get_nucleus_supervoxel_`"/]
    skeletonize_graph[/"`_skeletonize_graph_`"/]
    get_all_time_synapses[/"`_get_all_time_synapses_`"/]
    map_synapses_to_graph[/"`_map_synapses_to_graph_`"/]
    get_supervoxel_mappings[/"`_get_supervoxel_mappings_`"/]
    map_synapses_to_skeleton[/"`_map_synapses_to_skeleton_`"/]
    get_used_node_ids[/"`_get_used_node_ids_`"/]
    get_node_aliases[/"`_get_node_aliases_`"/]
    get_level2_data_table[/"`_level2_data_table_`"/]
    append1[/"`_append_`"/]
    append2[/"`_append_`"/]
    append3[/"`_append_`"/]
    ???1[/"`_???_`"/]
    ???2[/"`_???_`"/]

    click get_root_level2_edits "../reference/#paleo.get_root_level2_edits"
    click get_operations_level2_edits "../reference/#paleo.get_operations_level2_edits"
    click get_detailed_change_log "../reference/#paleo.get_detailed_change_log"
    click get_metaedits "../reference/#paleo.get_metaedits"
    click apply_edit "../reference/#paleo.apply_edit"
    click get_initial_graph "../reference/#paleo.get_initial_graph"
    click resolve_edit "../reference/#paleo.resolve_edit"
    click get_nucleus_supervoxel "../reference/#paleo.get_nucleus_supervoxel"
    click skeletonize_graph "../reference/#paleo.skeletonize_graph"
    click get_all_time_synapses "../reference/#paleo.get_all_time_synapses"
    click map_synapses_to_graph "../reference/#paleo.map_synapses_to_graph"
    click get_supervoxel_mappings "../reference/#paleo.get_supervoxel_mappings"
    click map_synapses_to_skeleton "../reference/#paleo.map_synapses_to_skeleton"
    click get_used_node_ids "../reference/#paleo.get_used_node_ids"
    click get_node_aliases "../reference/#paleo.get_node_aliases"
    click get_level2_data_table "https://caveconnectome.github.io/CAVEclient/api/l2cache/#caveclient.l2cache.L2CacheClient.get_l2data_table"

    RootID-->get_root_level2_edits;
    get_root_level2_edits-->Deltas;

    OperationIDs-->get_operations_level2_edits;
    get_operations_level2_edits-->Deltas;

    RootID-->get_detailed_change_log;
    get_detailed_change_log-->TabularChangelog;

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

    RootID-->get_all_time_synapses;
    get_all_time_synapses-->SynapseTable;

    SynapseTable-->get_supervoxel_mappings;
    Deltas-->get_supervoxel_mappings;
    get_supervoxel_mappings-->SynapseSupervoxelsOverTime;

    SynapseSupervoxelsOverTime-->map_synapses_to_graph;

    InitialGraph-->get_used_node_ids;
    AnyDelta-->get_used_node_ids;
    get_used_node_ids-->UsedNodes;
    UsedNodes-->get_level2_data_table;
    get_level2_data_table-->Level2DataTable;
    Level2DataTable-->skeletonize_graph;

    subgraph Repeat
        apply_edit-->UnresolvedGraph;
        UnresolvedGraph-->resolve_edit;
        resolve_edit-->ResolvedGraph;

        ResolvedGraph-->skeletonize_graph;
        skeletonize_graph-->Skeleton;
        Skeleton-->append1

        ResolvedGraph-->map_synapses_to_graph;
        map_synapses_to_graph-->ActiveSynapseIDs;

        ActiveSynapseIDs-->append2

        ActiveSynapseIDs-->map_synapses_to_skeleton

        Skeleton-->map_synapses_to_skeleton
        map_synapses_to_skeleton-->SkeletonWithSynapses

        SkeletonWithSynapses-->append3
    end

    append1-->SkeletonList
    append2-->SynapseList
    append3-->SkeletonList

    SkeletonList-->???1
    ???1-->MorphologicalFeatureTable;

    SynapseList-->???2
    ???2-->ConnectivityFeatureTable;

```
