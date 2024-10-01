import json
import pprint
import pandas as pd


class NetworkDelta:
    def __init__(
        self,
        removed_nodes: pd.DataFrame,
        added_nodes: pd.DataFrame,
        removed_edges: pd.DataFrame,
        added_edges: pd.DataFrame,
        metadata: dict = {},
    ):
        self.removed_nodes = removed_nodes
        self.added_nodes = added_nodes
        self.removed_edges = removed_edges.reset_index(drop=True)
        self.added_edges = added_edges.reset_index(drop=True)
        self.metadata = metadata

    def __repr__(self):
        rep = "NetworkDelta(\n"
        rep += f"   removed_nodes: {self.removed_nodes.shape[0]},\n"
        rep += f"   added_nodes: {self.added_nodes.shape[0]},\n"
        rep += f"   removed_edges: {self.removed_edges.shape[0]},\n"
        rep += f"   added_edges: {self.added_edges.shape[0]},\n"
        rep += "   metadata: {\n"
        rep += " " + pprint.pformat(self.metadata, indent=6)[1:-1]
        rep += "\n   }\n"
        rep += ")"
        return rep

    def to_dict(self):
        out = dict(
            removed_nodes=self.removed_nodes.index.to_list(),
            added_nodes=self.added_nodes.index.to_list(),
            removed_edges=self.removed_edges.values.tolist(),
            added_edges=self.added_edges.values.tolist(),
            metadata=self.metadata,
        )
        return out

    def to_json(self):
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, input):
        removed_nodes = pd.DataFrame(index=input["removed_nodes"])
        added_nodes = pd.DataFrame(index=input["added_nodes"])
        removed_edges = pd.DataFrame(
            input["removed_edges"], columns=["source", "target"]
        )
        added_edges = pd.DataFrame(input["added_edges"], columns=["source", "target"])
        metadata = input["metadata"]
        return cls(
            removed_nodes, added_nodes, removed_edges, added_edges, metadata=metadata
        )

    @classmethod
    def from_json(cls, input):
        return cls.from_dict(json.loads(input))

    def __eq__(self, other: "NetworkDelta") -> bool:
        if not isinstance(other, NetworkDelta):
            return False
        if not self.removed_nodes.equals(other.removed_nodes):
            return False
        if not self.added_nodes.equals(other.added_nodes):
            return False
        if not self.removed_edges.equals(other.removed_edges):
            return False
        if not self.added_edges.equals(other.added_edges):
            return False
        return True


def combine_deltas(deltas):
    total_added_nodes = pd.concat(
        [delta.added_nodes for delta in deltas], verify_integrity=True
    )
    total_removed_nodes = pd.concat(
        [delta.removed_nodes for delta in deltas], verify_integrity=True
    )

    total_added_edges = pd.concat(
        [
            delta.added_edges.set_index(["source", "target"], drop=True)
            for delta in deltas
        ],
        verify_integrity=True,
    ).reset_index(drop=False)
    total_removed_edges = pd.concat(
        [
            delta.removed_edges.set_index(["source", "target"], drop=True)
            for delta in deltas
        ],
        verify_integrity=True,
    ).reset_index(drop=False)

    return NetworkDelta(
        total_removed_nodes,
        total_added_nodes,
        total_removed_edges,
        total_added_edges,
    )
