import json
import pprint
from typing import Collection

import numpy as np


class NetworkDelta:
    def __init__(
        self,
        removed_nodes: np.ndarray,
        added_nodes: np.ndarray,
        removed_edges: np.ndarray,
        added_edges: np.ndarray,
        metadata: dict = {},
    ):
        """
        A class to represent a change to a network.

        Parameters
        ----------
        removed_nodes :
            IDs of nodes that were removed by this operation.
        added_nodes :
            IDs of nodes that were added by this operation.
        removed_edges :
            Edges that were removed by this operation.
        added_edges :
            Edges that were added by this operation.
        metadata :
            A dictionary of arbitrary metadata about the operation.
        """
        self.removed_nodes = removed_nodes
        self.added_nodes = added_nodes
        self.removed_edges = removed_edges
        self.added_edges = added_edges
        self.metadata = metadata

    def __repr__(self):
        rep = "NetworkDelta(\n"
        rep += f"   removed_nodes: {self.removed_nodes.shape[0]},\n"
        rep += f"   added_nodes: {self.added_nodes.shape[0]},\n"
        rep += f"   removed_edges: {self.removed_edges.shape[0]},\n"
        rep += f"   added_edges: {self.added_edges.shape[0]},\n"
        if len(self.metadata) > 0:
            rep += "   metadata: {\n"
            rep += " " + pprint.pformat(self.metadata, indent=6)[1:-1]
            rep += "\n   }\n"
            rep += ")"
        else:
            rep += "   metadata: {}\n"
            rep += ")"
        return rep

    def to_dict(self) -> dict:
        out = dict(
            removed_nodes=self.removed_nodes.tolist(),
            added_nodes=self.added_nodes.tolist(),
            removed_edges=self.removed_edges.tolist(),
            added_edges=self.added_edges.tolist(),
            metadata=self.metadata,
        )
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, input):
        removed_nodes = np.array(input["removed_nodes"], dtype=int)
        added_nodes = np.array(input["added_nodes"], dtype=int)
        removed_edges = np.array(input["removed_edges"], dtype=int).reshape(-1, 2)
        added_edges = np.array(input["added_edges"], dtype=int).reshape(-1, 2)
        metadata = input["metadata"]
        return cls(
            removed_nodes, added_nodes, removed_edges, added_edges, metadata=metadata
        )

    # @classmethod
    # def from_dict(cls, input):
    #     removed_nodes = pd.DataFrame(index=input["removed_nodes"])
    #     added_nodes = pd.DataFrame(index=input["added_nodes"])
    #     removed_edges = pd.DataFrame(
    #         input["removed_edges"], columns=["source", "target"]
    #     )
    #     added_edges = pd.DataFrame(input["added_edges"], columns=["source", "target"])
    #     metadata = input["metadata"]
    #     return cls(
    #         removed_nodes, added_nodes, removed_edges, added_edges, metadata=metadata
    #     )

    # @classmethod
    # def from_json(cls, input):
    #     return cls.from_dict(json.loads(input))

    def __eq__(self, other: "NetworkDelta") -> bool:
        if not isinstance(other, NetworkDelta):
            print("other is not instance of NetworkDelta")
            return False
        if not np.array_equal(self.removed_nodes, other.removed_nodes):
            print("removed_nodes not equal")
            return False
        if not np.array_equal(self.added_nodes, other.added_nodes):
            print("added_nodes not equal")
            return False
        if not np.array_equal(self.removed_edges, other.removed_edges):
            print("removed_edges not equal")
            return False
        if not np.array_equal(self.added_edges, other.added_edges):
            print("added_edges not equal")
            return False
        return True

    def __ne__(self, other: "NetworkDelta") -> bool:
        return not self.__eq__(other)

    def __add__(self, other: "NetworkDelta") -> "NetworkDelta":
        return combine_deltas([self, other])


def _unique_concatenate(
    arrays: Collection[np.ndarray], verify_integrity=True
) -> np.ndarray:
    concat_array = np.concatenate(arrays)
    if verify_integrity:
        unique_array, unique_counts = np.unique(
            concat_array, axis=0, return_counts=True
        )
        if np.any(unique_counts > 1):
            raise ValueError("Duplicate values found in arrays")
    return concat_array


def combine_deltas(deltas: Collection[NetworkDelta]) -> NetworkDelta:
    total_added_nodes = _unique_concatenate([delta.added_nodes for delta in deltas])
    total_removed_nodes = _unique_concatenate([delta.removed_nodes for delta in deltas])
    total_added_edges = _unique_concatenate([delta.added_edges for delta in deltas])
    total_removed_edges = _unique_concatenate([delta.removed_edges for delta in deltas])

    return NetworkDelta(
        total_removed_nodes,
        total_added_nodes,
        total_removed_edges,
        total_added_edges,
    )
