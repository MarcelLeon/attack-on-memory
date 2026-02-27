"""Selective disclosure and memory governance policies."""

from __future__ import annotations

from dataclasses import dataclass, field

from attack_on_memory.domain.models import (
    MemoryCitation,
    ProjectedMemory,
    RetrievedMemory,
    SENSITIVITY_ORDER,
    Sensitivity,
    TaskIntent,
)


@dataclass(frozen=True)
class DisclosurePolicy:
    """Role-based disclosure policy."""

    role: str
    max_sensitivity: Sensitivity = Sensitivity.INTERNAL
    allowed_domains: frozenset[str] = field(default_factory=frozenset)
    allowed_tasks: frozenset[str] = field(default_factory=frozenset)
    min_confidence: float = 0.0

    def allows(self, item: RetrievedMemory, intent: TaskIntent) -> bool:
        atom = item.atom

        if item.atom.confidence < self.min_confidence:
            return False
        if SENSITIVITY_ORDER[atom.sensitivity] > SENSITIVITY_ORDER[self.max_sensitivity]:
            return False
        if self.allowed_domains and atom.scope.domain not in self.allowed_domains:
            return False
        if self.allowed_tasks and atom.scope.task not in self.allowed_tasks:
            return False
        if atom.scope.domain != intent.domain or atom.scope.task != intent.task:
            return False
        return True


class MemoryGovernor:
    """Apply selective disclosure policies over retrieval outputs."""

    def __init__(self) -> None:
        self._policies: dict[str, DisclosurePolicy] = {}

    def register_policy(self, policy: DisclosurePolicy) -> None:
        self._policies[policy.role] = policy

    def project(
        self,
        retrieved: list[RetrievedMemory],
        intent: TaskIntent,
    ) -> tuple[list[ProjectedMemory], list[MemoryCitation]]:
        policy = self._policies.get(intent.role)
        if policy is None:
            return [], []

        projected: list[ProjectedMemory] = []
        citations: list[MemoryCitation] = []
        for item in retrieved:
            if not policy.allows(item, intent):
                continue
            atom = item.atom
            projected.append(
                ProjectedMemory(
                    atom_id=atom.id,
                    claim=atom.claim,
                    confidence=atom.confidence,
                    scope=atom.scope,
                    branch_id=atom.branch_id,
                    tags=atom.tags,
                )
            )
            citations.append(
                MemoryCitation(
                    atom_id=atom.id,
                    score=item.score,
                    reason=item.reason,
                )
            )
        return projected, citations
