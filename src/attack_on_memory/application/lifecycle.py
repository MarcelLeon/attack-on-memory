"""Auditable memory lifecycle, consolidation, erasure, and contamination recovery."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from typing import ContextManager, Iterable

from attack_on_memory.domain.models import (
    EdgeType,
    MemoryAtom,
    MemoryEdge,
    MemoryLifecycleRecord,
    MemoryLifecycleState,
    utc_now,
)
from attack_on_memory.infrastructure.store import MemoryStore


ALLOWED_TRANSITIONS: dict[MemoryLifecycleState, frozenset[MemoryLifecycleState]] = {
    MemoryLifecycleState.ACTIVE: frozenset(
        {
            MemoryLifecycleState.QUARANTINED,
            MemoryLifecycleState.SUPERSEDED,
            MemoryLifecycleState.EXPIRED,
            MemoryLifecycleState.FORGOTTEN,
        }
    ),
    MemoryLifecycleState.QUARANTINED: frozenset(
        {MemoryLifecycleState.ACTIVE, MemoryLifecycleState.FORGOTTEN}
    ),
    MemoryLifecycleState.SUPERSEDED: frozenset({MemoryLifecycleState.FORGOTTEN}),
    MemoryLifecycleState.EXPIRED: frozenset({MemoryLifecycleState.FORGOTTEN}),
    MemoryLifecycleState.FORGOTTEN: frozenset(),
}


class MemoryLifecycleService:
    """Enforce lifecycle transitions and preserve content-minimized audit evidence."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def quarantine(
        self,
        atom_id: str,
        *,
        actor: str,
        reason_code: str,
        changed_at: datetime | None = None,
    ) -> MemoryLifecycleRecord:
        return self._transition(
            atom_id,
            MemoryLifecycleState.QUARANTINED,
            actor=actor,
            reason_code=reason_code,
            changed_at=changed_at,
        )

    def restore(
        self,
        atom_id: str,
        *,
        actor: str,
        reason_code: str,
        changed_at: datetime | None = None,
    ) -> MemoryLifecycleRecord:
        return self._transition(
            atom_id,
            MemoryLifecycleState.ACTIVE,
            actor=actor,
            reason_code=reason_code,
            changed_at=changed_at,
        )

    def forget(
        self,
        atom_id: str,
        *,
        actor: str,
        reason_code: str,
        changed_at: datetime | None = None,
    ) -> MemoryLifecycleRecord:
        """Physically erase content/edges/vectors while retaining a minimal event."""
        with self._atomic():
            record = self._transition_without_transaction(
                atom_id,
                MemoryLifecycleState.FORGOTTEN,
                actor=actor,
                reason_code=reason_code,
                changed_at=changed_at,
            )
            self._store.delete_atom(atom_id)
        return record

    def expire_due(
        self,
        *,
        at: datetime | None = None,
        actor: str = "lifecycle-sweeper",
    ) -> tuple[MemoryLifecycleRecord, ...]:
        check_time = at or utc_now()
        records: list[MemoryLifecycleRecord] = []
        with self._atomic():
            for atom in self._store.list_atoms():
                if atom.expires_at > check_time or not self._is_active(atom.id):
                    continue
                records.append(
                    self._transition_without_transaction(
                        atom.id,
                        MemoryLifecycleState.EXPIRED,
                        actor=actor,
                        reason_code="ttl.expired",
                        changed_at=check_time,
                    )
                )
        return tuple(records)

    def consolidate(
        self,
        summary: MemoryAtom,
        source_ids: Iterable[str],
        *,
        actor: str,
        changed_at: datetime | None = None,
    ) -> tuple[MemoryLifecycleRecord, ...]:
        """Persist a derived summary and supersede its active source memories."""
        sources = tuple(dict.fromkeys(source_ids))
        if len(sources) < 2:
            raise ValueError("consolidation requires at least two source memories")
        if summary.id in sources:
            raise ValueError("summary cannot consolidate itself")
        if self._store.get_atom(summary.id) is not None:
            raise ValueError(f"summary memory id already exists: {summary.id}")
        if self._store.get_lifecycle(summary.id) is not None:
            raise ValueError(f"summary memory id has a lifecycle tombstone: {summary.id}")
        missing_supersedes = set(sources) - set(summary.supersedes)
        if missing_supersedes:
            raise ValueError(
                "summary.metadata.supersedes must include every source id: "
                f"{sorted(missing_supersedes)}"
            )
        for atom_id in sources:
            if self._store.get_atom(atom_id) is None:
                raise KeyError(f"Unknown memory atom id: {atom_id}")
            if not self._is_active(atom_id):
                raise ValueError(f"source memory is not active: {atom_id}")

        transition_time = changed_at or utc_now()
        records: list[MemoryLifecycleRecord] = []
        with self._atomic():
            self._store.upsert_atom(summary)
            for atom_id in sources:
                self._store.add_edge(
                    MemoryEdge(
                        source_id=summary.id,
                        target_id=atom_id,
                        edge_type=EdgeType.DERIVED_FROM,
                    )
                )
                records.append(
                    self._transition_without_transaction(
                        atom_id,
                        MemoryLifecycleState.SUPERSEDED,
                        actor=actor,
                        reason_code="consolidation.superseded",
                        changed_at=transition_time,
                    )
                )
        return tuple(records)

    def quarantine_related(
        self,
        atom_id: str,
        *,
        actor: str,
        reason_code: str = "poisoning.related",
        max_hops: int = 2,
        edge_types: set[EdgeType] | None = None,
        changed_at: datetime | None = None,
    ) -> tuple[MemoryLifecycleRecord, ...]:
        """Fail closed by quarantining a suspect atom and its derivation neighborhood."""
        if self._store.get_atom(atom_id) is None:
            raise KeyError(f"Unknown memory atom id: {atom_id}")
        relationship_types = edge_types or {EdgeType.DERIVED_FROM, EdgeType.CAUSED_BY}
        related = self._store.neighboring_atom_ids(
            (atom_id,),
            max_hops=max_hops,
            edge_types=relationship_types,
        )
        candidates = (atom_id, *sorted(related))
        records: list[MemoryLifecycleRecord] = []
        with self._atomic():
            for candidate in candidates:
                if self._store.get_atom(candidate) is None or not self._is_active(candidate):
                    continue
                records.append(
                    self._transition_without_transaction(
                        candidate,
                        MemoryLifecycleState.QUARANTINED,
                        actor=actor,
                        reason_code=reason_code,
                        changed_at=changed_at,
                    )
                )
        return tuple(records)

    def _transition(
        self,
        atom_id: str,
        target: MemoryLifecycleState,
        *,
        actor: str,
        reason_code: str,
        changed_at: datetime | None,
    ) -> MemoryLifecycleRecord:
        with self._atomic():
            return self._transition_without_transaction(
                atom_id,
                target,
                actor=actor,
                reason_code=reason_code,
                changed_at=changed_at,
            )

    def _transition_without_transaction(
        self,
        atom_id: str,
        target: MemoryLifecycleState,
        *,
        actor: str,
        reason_code: str,
        changed_at: datetime | None,
    ) -> MemoryLifecycleRecord:
        if self._store.get_atom(atom_id) is None:
            raise KeyError(f"Unknown memory atom id: {atom_id}")
        current = self._store.get_lifecycle(atom_id)
        current_state = current.state if current else MemoryLifecycleState.ACTIVE
        if target not in ALLOWED_TRANSITIONS[current_state]:
            raise ValueError(
                f"illegal memory lifecycle transition: {current_state.value} -> {target.value}"
            )
        transition_time = changed_at or utc_now()
        if current is not None and transition_time < current.changed_at:
            raise ValueError("lifecycle transition time cannot move backwards")
        record = MemoryLifecycleRecord(
            atom_id=atom_id,
            state=target,
            reason_code=reason_code,
            actor=actor,
            changed_at=transition_time,
            version=1 if current is None else current.version + 1,
        )
        self._store.set_lifecycle(record)
        return record

    def _is_active(self, atom_id: str) -> bool:
        current = self._store.get_lifecycle(atom_id)
        return current is None or current.state is MemoryLifecycleState.ACTIVE

    def _atomic(self) -> ContextManager[None]:
        transaction = getattr(self._store, "transaction", None)
        return transaction() if callable(transaction) else nullcontext()
