"""Storage contracts shared by in-memory and durable backends."""

from __future__ import annotations

from typing import ContextManager, Iterable, Protocol

from attack_on_memory.domain.models import (
    Branch,
    BranchStatus,
    EdgeType,
    MemoryAtom,
    MemoryEdge,
    MemoryLifecycleRecord,
)


class MemoryStore(Protocol):
    """Behavioral contract required by capture, retrieval, and branch services."""

    def upsert_atom(self, atom: MemoryAtom) -> None: ...

    def get_atom(self, atom_id: str) -> MemoryAtom | None: ...

    def delete_atom(self, atom_id: str) -> None: ...

    def list_atoms(
        self,
        branch_id: str | None = None,
        *,
        include_inherited: bool = False,
    ) -> list[MemoryAtom]: ...

    def add_edge(self, edge: MemoryEdge) -> None: ...

    def list_edges(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        edge_type: EdgeType | None = None,
    ) -> list[MemoryEdge]: ...

    def neighboring_atom_ids(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: set[EdgeType] | None = None,
    ) -> set[str]: ...

    def upsert_branch(self, branch: Branch) -> None: ...

    def get_branch(self, branch_id: str) -> Branch | None: ...

    def resolve_branch_lineage(self, branch_id: str) -> tuple[str, ...]: ...

    def list_branches(self, status: BranchStatus | None = None) -> list[Branch]: ...

    def set_lifecycle(self, record: MemoryLifecycleRecord) -> None: ...

    def get_lifecycle(self, atom_id: str) -> MemoryLifecycleRecord | None: ...

    def list_lifecycle_events(
        self,
        atom_id: str | None = None,
    ) -> list[MemoryLifecycleRecord]: ...


class TransactionalMemoryStore(MemoryStore, Protocol):
    """Optional durable-store capabilities for atomic write groups and cleanup."""

    def transaction(self) -> ContextManager[None]: ...

    def close(self) -> None: ...
