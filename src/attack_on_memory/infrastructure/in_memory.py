"""In-memory repositories for local experiments and unit tests."""

from __future__ import annotations

from typing import Iterable

from attack_on_memory.domain.models import (
    Branch,
    BranchStatus,
    EdgeType,
    MemoryAtom,
    MemoryEdge,
    MemoryLifecycleRecord,
)
from attack_on_memory.infrastructure.graph_backend import GraphBackend, InMemoryGraphBackend


class InMemoryStore:
    """Single in-memory store implementing memory, graph, and branch repositories."""

    def __init__(self, graph_backend: GraphBackend | None = None) -> None:
        self._atoms: dict[str, MemoryAtom] = {}
        self._edges: list[MemoryEdge] = []
        self._graph_backend = graph_backend or InMemoryGraphBackend()
        self._branches: dict[str, Branch] = {}
        self._lifecycle_current: dict[str, MemoryLifecycleRecord] = {}
        self._lifecycle_events: list[MemoryLifecycleRecord] = []

    # Memory atom operations
    def upsert_atom(self, atom: MemoryAtom) -> None:
        self._atoms[atom.id] = atom

    def get_atom(self, atom_id: str) -> MemoryAtom | None:
        return self._atoms.get(atom_id)

    def delete_atom(self, atom_id: str) -> None:
        self._atoms.pop(atom_id, None)
        self._edges = [
            edge
            for edge in self._edges
            if edge.source_id != atom_id and edge.target_id != atom_id
        ]
        self._graph_backend.remove_atom(atom_id)

    def list_atoms(
        self,
        branch_id: str | None = None,
        *,
        include_inherited: bool = False,
    ) -> list[MemoryAtom]:
        atoms = list(self._atoms.values())
        if branch_id is None:
            return atoms
        if include_inherited:
            lineage = self.resolve_branch_lineage(branch_id)
            lineage_index = {current_branch: idx for idx, current_branch in enumerate(lineage)}
            inherited_atoms = [atom for atom in atoms if atom.branch_id in lineage_index]
            return sorted(
                inherited_atoms,
                key=lambda atom: (
                    lineage_index[atom.branch_id],
                    -atom.created_at.timestamp(),
                    atom.id,
                ),
            )
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

    def resolve_branch_lineage(self, branch_id: str) -> tuple[str, ...]:
        if not branch_id.strip():
            raise ValueError("branch_id cannot be empty")

        lineage: list[str] = []
        current_id: str | None = branch_id
        visited: set[str] = set()

        while current_id is not None and current_id not in visited:
            lineage.append(current_id)
            visited.add(current_id)
            branch = self._branches.get(current_id)
            current_id = branch.parent_id if branch is not None else None

        if branch_id != "main" and "main" in self._branches and "main" not in visited:
            lineage.append("main")

        return tuple(lineage)

    def list_branches(self, status: BranchStatus | None = None) -> list[Branch]:
        branches = list(self._branches.values())
        if status is None:
            return branches
        return [branch for branch in branches if branch.status == status]

    # Lifecycle operations
    def set_lifecycle(self, record: MemoryLifecycleRecord) -> None:
        if record.atom_id not in self._atoms:
            raise KeyError(f"Unknown memory atom id: {record.atom_id}")
        current = self._lifecycle_current.get(record.atom_id)
        expected_version = 1 if current is None else current.version + 1
        if record.version != expected_version:
            raise ValueError(
                f"lifecycle version for {record.atom_id} must be {expected_version}"
            )
        self._lifecycle_current[record.atom_id] = record
        self._lifecycle_events.append(record)

    def get_lifecycle(self, atom_id: str) -> MemoryLifecycleRecord | None:
        return self._lifecycle_current.get(atom_id)

    def list_lifecycle_events(
        self,
        atom_id: str | None = None,
    ) -> list[MemoryLifecycleRecord]:
        if atom_id is None:
            return list(self._lifecycle_events)
        return [event for event in self._lifecycle_events if event.atom_id == atom_id]
