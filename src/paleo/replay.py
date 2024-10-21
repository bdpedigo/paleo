import networkx as nx
import numpy as np

from .networkdelta import NetworkDelta


class Level2GraphNetworkX:
    def __init__(self, nodes: np.ndarray, edges: np.ndarray):
        self.graph = nx.Graph()
        self.graph.add_nodes_from(nodes)
        self.graph.add_edges_from(edges)

    def apply_edit(self, networkdelta: NetworkDelta):
        removed_edges = networkdelta.removed_edges
        removed_nodes = networkdelta.removed_nodes

        added_edges = networkdelta.added_edges
        added_nodes = networkdelta.added_nodes

        # NOTE: these do not error if the nodes or edges are not in the graph
        # may want to revisit that
        self.graph.remove_nodes_from(removed_nodes)
        self.graph.remove_edges_from(removed_edges)

        self.graph.add_nodes_from(added_nodes)
        self.graph.add_edges_from(added_edges)
