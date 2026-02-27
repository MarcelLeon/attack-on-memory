"""Graph backend abstractions for memory-edge traversal."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable, Protocol

from attack_on_memory.domain.models import EdgeType, MemoryEdge


class GraphBackend(Protocol):
    """Contract for graph traversal over memory edges."""

    def add_edge(self, edge: MemoryEdge) -> None:
        ...

    def neighboring_atom_ids(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: set[EdgeType] | None = None,
    ) -> set[str]:
        ...


class InMemoryGraphBackend:
    """Default in-process graph backend."""

    def __init__(self) -> None:
        self._outgoing: dict[str, list[MemoryEdge]] = defaultdict(list)
        self._incoming: dict[str, list[MemoryEdge]] = defaultdict(list)

    def add_edge(self, edge: MemoryEdge) -> None:
        self._outgoing[edge.source_id].append(edge)
        self._incoming[edge.target_id].append(edge)

    def neighboring_atom_ids(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: set[EdgeType] | None = None,
    ) -> set[str]:
        if max_hops <= 0:
            return set()

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque((seed_id, 0) for seed_id in seed_ids)
        seed_set = set(seed_ids)

        while queue:
            current_id, hops = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            if hops >= max_hops:
                continue

            outgoing_edges = self._outgoing.get(current_id, [])
            incoming_edges = self._incoming.get(current_id, [])
            for edge in outgoing_edges + incoming_edges:
                if edge_types is not None and edge.edge_type not in edge_types:
                    continue
                neighbor_id = edge.target_id if edge.source_id == current_id else edge.source_id
                if neighbor_id not in visited:
                    queue.append((neighbor_id, hops + 1))

        return visited - seed_set


class NetworkXGraphBackend:
    """Optional networkx-powered graph backend."""

    def __init__(self) -> None:
        try:
            import networkx as nx  # type: ignore
        except Exception as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(
                "networkx is required for NetworkXGraphBackend. Install with: pip install networkx"
            ) from exc
        self._nx = nx
        self._graph = nx.MultiGraph()

    def add_edge(self, edge: MemoryEdge) -> None:
        self._graph.add_node(edge.source_id)
        self._graph.add_node(edge.target_id)
        self._graph.add_edge(
            edge.source_id,
            edge.target_id,
            edge_type=edge.edge_type.value,
            weight=edge.weight,
        )

    def neighboring_atom_ids(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: set[EdgeType] | None = None,
    ) -> set[str]:
        if max_hops <= 0:
            return set()

        allowed = {edge_type.value for edge_type in edge_types} if edge_types else None
        seed_set = set(seed_ids)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque((seed_id, 0) for seed_id in seed_set)

        while queue:
            current_id, hops = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            if hops >= max_hops:
                continue
            if current_id not in self._graph:
                continue

            for neighbor in self._graph.neighbors(current_id):
                if allowed is not None:
                    edge_bundle = self._graph.get_edge_data(current_id, neighbor, default={})
                    has_allowed = any(data.get("edge_type") in allowed for data in edge_bundle.values())
                    if not has_allowed:
                        continue
                if neighbor not in visited:
                    queue.append((neighbor, hops + 1))

        return visited - seed_set
