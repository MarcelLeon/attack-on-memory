"""Selective disclosure and memory governance policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from attack_on_memory.domain.models import (
    MemoryCitation,
    ProjectedMemory,
    RetrievedMemory,
    SENSITIVITY_ORDER,
    Sensitivity,
    TaskIntent,
)


@dataclass(frozen=True)
class GovernanceDecision:
    """Content-minimized, versioned explanation for one projection decision."""

    request_id: str
    atom_id: str
    allowed: bool
    reason_code: str
    policy_id: str
    policy_version: int
    role: str
    purpose: str
    decided_at: datetime


@dataclass(frozen=True)
class GovernanceEvaluation:
    """Projection payload plus decisions that belong in a separate audit plane."""

    memories: tuple[ProjectedMemory, ...]
    citations: tuple[MemoryCitation, ...]
    decisions: tuple[GovernanceDecision, ...]


@dataclass(frozen=True)
class DisclosurePolicy:
    """Role-based disclosure policy."""

    role: str
    policy_id: str = "default-disclosure"
    version: int = 1
    max_sensitivity: Sensitivity = Sensitivity.INTERNAL
    allowed_domains: frozenset[str] = field(default_factory=frozenset)
    allowed_tasks: frozenset[str] = field(default_factory=frozenset)
    allowed_purposes: frozenset[str] = field(default_factory=frozenset)
    require_explicit_purpose: bool = False
    min_confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.policy_id.strip():
            raise ValueError("policy role and policy_id cannot be empty")
        if self.version <= 0:
            raise ValueError("policy version must be > 0")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")

    def allows(self, item: RetrievedMemory, intent: TaskIntent) -> bool:
        allowed, _ = self.decide(item, intent)
        return allowed

    def decide(self, item: RetrievedMemory, intent: TaskIntent) -> tuple[bool, str]:
        atom = item.atom

        if item.atom.confidence < self.min_confidence:
            return False, "confidence.below_minimum"
        if SENSITIVITY_ORDER[atom.sensitivity] > SENSITIVITY_ORDER[self.max_sensitivity]:
            return False, "sensitivity.exceeded"
        if self.allowed_domains and atom.scope.domain not in self.allowed_domains:
            return False, "domain.not_allowed"
        if self.allowed_tasks and atom.scope.task not in self.allowed_tasks:
            return False, "task.not_allowed"
        if atom.scope.domain != intent.domain or atom.scope.task != intent.task:
            return False, "scope.mismatch"
        if self.require_explicit_purpose and intent.purpose is None:
            return False, "purpose.required"
        if self.allowed_purposes and intent.effective_purpose not in self.allowed_purposes:
            return False, "purpose.not_allowed"
        return True, "policy.allowed"


class MemoryGovernor:
    """Apply selective disclosure policies over retrieval outputs."""

    def __init__(self) -> None:
        self._policies: dict[str, DisclosurePolicy] = {}

    def register_policy(self, policy: DisclosurePolicy) -> None:
        if policy.role in self._policies:
            current = self._policies[policy.role]
            raise ValueError(
                f"policy already registered for role {policy.role!r}: "
                f"{current.policy_id}@{current.version}; use update_policy"
            )
        self._policies[policy.role] = policy

    def update_policy(
        self,
        policy: DisclosurePolicy,
        *,
        expected_policy_id: str,
        expected_version: int,
    ) -> None:
        """Optimistically replace one role policy with its next exact version."""
        current = self._policies.get(policy.role)
        if current is None:
            raise KeyError(f"no policy registered for role {policy.role!r}")
        if (
            current.policy_id != expected_policy_id
            or current.version != expected_version
        ):
            raise ValueError("current policy identity/version does not match expectation")
        if policy.policy_id != current.policy_id:
            raise ValueError("policy_id cannot change during an in-place update")
        if policy.version != current.version + 1:
            raise ValueError("policy update version must increment by exactly one")
        self._policies[policy.role] = policy

    def policy_for(self, role: str) -> DisclosurePolicy | None:
        return self._policies.get(role)

    def project(
        self,
        retrieved: list[RetrievedMemory],
        intent: TaskIntent,
    ) -> tuple[list[ProjectedMemory], list[MemoryCitation]]:
        evaluation = self.evaluate(retrieved, intent)
        return list(evaluation.memories), list(evaluation.citations)

    def evaluate(
        self,
        retrieved: list[RetrievedMemory],
        intent: TaskIntent,
    ) -> GovernanceEvaluation:
        policy = self._policies.get(intent.role)
        if policy is None:
            decisions = tuple(
                GovernanceDecision(
                    request_id=intent.request_id,
                    atom_id=item.atom.id,
                    allowed=False,
                    reason_code="policy.missing",
                    policy_id="<none>",
                    policy_version=0,
                    role=intent.role,
                    purpose=intent.effective_purpose,
                    decided_at=intent.as_of,
                )
                for item in retrieved
            )
            return GovernanceEvaluation(memories=(), citations=(), decisions=decisions)

        projected: list[ProjectedMemory] = []
        citations: list[MemoryCitation] = []
        decisions: list[GovernanceDecision] = []
        for item in retrieved:
            allowed, reason_code = policy.decide(item, intent)
            decisions.append(
                GovernanceDecision(
                    request_id=intent.request_id,
                    atom_id=item.atom.id,
                    allowed=allowed,
                    reason_code=reason_code,
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                    role=intent.role,
                    purpose=intent.effective_purpose,
                    decided_at=intent.as_of,
                )
            )
            if not allowed:
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
        return GovernanceEvaluation(
            memories=tuple(projected),
            citations=tuple(citations),
            decisions=tuple(decisions),
        )
