"""Separate audit plane for governance decisions."""

from __future__ import annotations

import threading
from typing import Iterable, Protocol

from attack_on_memory.governance.policies import GovernanceDecision


class GovernanceAuditSink(Protocol):
    """Persistence boundary that must not be exposed as Agent context."""

    def record_governance_decisions(
        self,
        decisions: Iterable[GovernanceDecision],
    ) -> None: ...

    def list_governance_decisions(
        self,
        request_id: str | None = None,
    ) -> list[GovernanceDecision]: ...


class InMemoryGovernanceAuditSink:
    """Thread-safe local audit sink for tests and ephemeral runtimes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._decisions: list[GovernanceDecision] = []
        self._keys: set[tuple[str, str]] = set()

    def record_governance_decisions(
        self,
        decisions: Iterable[GovernanceDecision],
    ) -> None:
        batch = tuple(decisions)
        keys = [(item.request_id, item.atom_id) for item in batch]
        if len(keys) != len(set(keys)):
            raise ValueError("governance audit batch contains duplicate request/atom keys")
        with self._lock:
            duplicates = set(keys) & self._keys
            if duplicates:
                raise ValueError(
                    f"governance decisions are immutable; duplicate keys: {sorted(duplicates)}"
                )
            self._decisions.extend(batch)
            self._keys.update(keys)

    def list_governance_decisions(
        self,
        request_id: str | None = None,
    ) -> list[GovernanceDecision]:
        with self._lock:
            if request_id is None:
                return list(self._decisions)
            return [
                decision
                for decision in self._decisions
                if decision.request_id == request_id
            ]
