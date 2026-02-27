"""In-memory repositories for local experiments and unit tests."""

from __future__ import annotations

from typing import Iterable

from attack_on_memory.domain.models import Branch, BranchStatus, EdgeType, MemoryAtom, MemoryEdge
from attack_on_memory.infrastructure.graph_backend import GraphBackend, InMemoryGraphBackend


class InMemoryStore:
    """Single in-memory store implementing memory, graph, and branch repositories."""

    def __init__(self, graph_backend: GraphBackend | None = None) -> None:
        self._atoms: dict[str, MemoryAtom] = {}
        self._edges: list[MemoryEdge] = []
        self._graph_backend = graph_backend or InMemoryGraphBackend()
        self._branches: dict[str, Branch] = {}

    # Memory atom operations
    def upsert_atom(self, atom: MemoryAtom) -> None:
        self._atoms[atom.id] = atom

    def get_atom(self, atom_id: str) -> MemoryAtom | None:
        return self._atoms.get(atom_id)

    def list_atoms(self, branch_id: str | None = None) -> list[MemoryAtom]:
        atoms = list(self._atoms.values())
        if branch_id is None:
            return atoms
        return [atom for atom in atoms if atom.branch_id == branch_id]

    # Edge operations
    def add_edge(self, edge: MemoryEdge) -> None:
        if edge.source_id not in self._atoms or edge.target_id not in self._atoms:
            raise KeyError("Both source and target atoms must exist before adding an edge")
        self._edges.append(edge)
        self._graph_backend.add_edge(edge)

    def list_edges(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        edge_type: EdgeType | None = None,
    ) -> list[MemoryEdge]:
        result: list[MemoryEdge] = []
        for edge in self._edges:
            if source_id is not None and edge.source_id != source_id:
                continue
            if target_id is not None and edge.target_id != target_id:
                continue
            if edge_type is not None and edge.edge_type != edge_type:
                continue
            result.append(edge)
        return result

    def neighboring_atom_ids(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: set[EdgeType] | None = None,
    ) -> set[str]:
        return self._graph_backend.neighboring_atom_ids(
            seed_ids,
            max_hops=max_hops,
            edge_types=edge_types,
        )

    # Branch operations
    def upsert_branch(self, branch: Branch) -> None:
        self._branches[branch.id] = branch

    def get_branch(self, branch_id: str) -> Branch | None:
        return self._branches.get(branch_id)

    def list_branches(self, status: BranchStatus | None = None) -> list[Branch]:
        branches = list(self._branches.values())
        if status is None:
            return branches
        return [branch for branch in branches if branch.status == status]
