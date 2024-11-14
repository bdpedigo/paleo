import json

import networkx as nx
import numpy as np

from paleo import NetworkDelta


def edits_to_json(networkdeltas_by_operation: dict) -> str:
    networkdelta_dicts = {}
    for operation_id, delta in networkdeltas_by_operation.items():
        networkdelta_dicts[operation_id] = delta.to_dict()
    return json.dumps(networkdelta_dicts)


def json_to_edits(edits_json) -> dict:
    networkdelta_dicts = json.loads(edits_json)
    networkdeltas_by_operation = {}
    for operation_id, delta in networkdelta_dicts.items():
        networkdeltas_by_operation[int(operation_id)] = NetworkDelta.from_dict(delta)
    return networkdeltas_by_operation


def graph_to_json(graph: nx.Graph):
    edges = np.array(list(graph.edges(data=False))).astype(str).tolist()
    nodes = np.array(list(graph.nodes(data=False))).astype(str).tolist()

    return json.dumps({"edges": edges, "nodes": nodes})


def json_to_graph(json_str):
    data = json.loads(json_str)
    nodes = np.array(data["nodes"]).astype(int)
    edges = np.array(data["edges"]).astype(int)
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)
    return graph
