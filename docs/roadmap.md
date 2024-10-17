---
title: Roadmap
---

## Problem statement

Many connectome datasets have undergone heavy proofreading. Information
has been logged in the chunkedgraph about how each edit in a dataset affected the segmentation.
However, accessing this information requires some knowledge of the chunkedgraph and how the
editing infrastructure works. It often requires hitting several endpoints to get out
specific information about what has changed. Further, if one is trying to compute derived
metadata about how an edit affected things (e.g., "how many synapses were added by this
edit?"), this requires even more in depth knowledge about the CAVE ecosystem.

The goal of `paleo` is to make this information more accessible by exposing some derived
information from edit histories.

The philosophy will be to first create an API around these features in this Python package,
and make sure that it is useful and easy to use. Some of this information will be fairly
slow and burdensome to compute, so in the future we may want to create server-side
implementations for some of it. Nevertheless, the Python package will be a good starting
point for understanding what is possible and what is useful.

Some potential applications of this work include:

- Tooling for monitoring proofreading progress, possibly in real-time
- Visualization of proofreading progress
- Data extraction for training automated proofreading algorithms
- Development of metrics for weighting the impact individual edits
- Attaching semantic information to edits, such as "this edit is an undo"
- Developing models of how well proofread a cell is

Here, we describe some of the possible features we might want to implement in `paleo`.

## Comparison targets

What quantities might we want to compare between roots, operations, timepoints, etc.?

### Morphology representations/features

One type of comparison is between representations of morphology at various resolutions.
These comparisons would return something like `added_nodes`, `removed_nodes`,
`added_edges`, `removed_edges`, etc. For an example, see the functions currently
implemented in `paleo`, which do this already for `level2_graphs`.

- `supervoxel_graphs`
- `level2_graphs`
- `skeletons`
- `meshes`
- `synapses`

### Statistics

We also might want to have comparisons of derived statistics of morphology and
connectivity. Many of these would be derived from the representations above. I imagine
that for any of these statistics, there would be something like `path_length_added`,
`path_length_removed`, `path_length_net` (added - removed, so could be negative).

- `n_level2_nodes` (this is actually a decent proxy for path length, w/o skeletonizing)
- `path_lengths`
- `volume`
- `n_synapses`
- `n_pre_synapses`
- `n_post_synapses`
- `n_edits`
- `n_merges`
- `n_splits`

## Comparison types

For any of the above comparisons, what inputs would be convenient to provide?

- `compare_roots_{target}`: given two roots, compare the target feature.
- `compare_operation_{target}`: given a specific operation ID, compare the target features before and after.
- `compare_operations_{target}`: given a list of operation IDs, compare the target features before and after for each operation.
- `compare_root_operations_{target}`: given a root, compare the target features before and after each operation in its history.
- `compare_timepoints_{target}`: given two timepoints and a root/nucleus ID, compare the target features between the timepoints.

<!-- ## Notes

- How long since a cell has been edited?
- What were the edits that were necessary for connecting this edit to this cell
  - And metadata about those edits, like who connected them
- Are there metrics on how good a proofreader is? -->
