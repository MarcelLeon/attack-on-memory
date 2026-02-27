from __future__ import annotations

import unittest

from attack_on_memory.domain.models import EdgeType, MemoryEdge
from attack_on_memory.infrastructure.graph_backend import NetworkXGraphBackend


class GraphBackendAdapterTests(unittest.TestCase):
    def test_networkx_traversal_semantics(self) -> None:
        try:
            backend = NetworkXGraphBackend()
        except RuntimeError:
            self.skipTest("networkx not installed")

        backend.add_edge(MemoryEdge(source_id="a", target_id="b", edge_type=EdgeType.SUPPORTS))
        backend.add_edge(MemoryEdge(source_id="b", target_id="c", edge_type=EdgeType.CONTRADICTS))
        backend.add_edge(MemoryEdge(source_id="c", target_id="d", edge_type=EdgeType.DERIVED_FROM))

        one_hop = backend.neighboring_atom_ids(("a",), max_hops=1)
        self.assertEqual(one_hop, {"b"})

        two_hops = backend.neighboring_atom_ids(("a",), max_hops=2)
        self.assertEqual(two_hops, {"b", "c"})

        supports_only = backend.neighboring_atom_ids(
            ("a",),
            max_hops=3,
            edge_types={EdgeType.SUPPORTS},
        )
        self.assertEqual(supports_only, {"b"})


if __name__ == "__main__":
    unittest.main()
