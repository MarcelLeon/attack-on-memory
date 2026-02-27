"""Branch-world model services for hypothesis management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from attack_on_memory.domain.models import Branch, BranchStatus, utc_now
from attack_on_memory.infrastructure.in_memory import InMemoryStore


@dataclass(frozen=True)
class BranchEvaluation:
    """Evaluation tuple for comparing branch outcomes."""

    branch_id: str
    success_rate: float
    risk_score: float
    cost_score: float

    def __post_init__(self) -> None:
        for field_name in ("success_rate", "risk_score", "cost_score"):
            value = getattr(self, field_name)
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{field_name} must be between 0 and 1")


@dataclass(frozen=True)
class BranchRank:
    """Branch rank output used by orchestrators."""

    branch_id: str
    utility: float


class BranchWorldModelService:
    """Manage branch lifecycle and utility-based ranking."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def create_branch(
        self,
        *,
        branch_id: str,
        name: str,
        hypothesis: str,
        parent_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Branch:
        branch = Branch(
            id=branch_id,
            name=name,
            hypothesis=hypothesis,
            parent_id=parent_id,
            created_at=created_at or utc_now(),
            status=BranchStatus.ACTIVE,
        )
        self._store.upsert_branch(branch)
        return branch

    def update_status(self, branch_id: str, status: BranchStatus) -> Branch:
        branch = self._store.get_branch(branch_id)
        if branch is None:
            raise KeyError(f"Unknown branch id: {branch_id}")

        updated = Branch(
            id=branch.id,
            name=branch.name,
            hypothesis=branch.hypothesis,
            parent_id=branch.parent_id,
            created_at=branch.created_at,
            status=status,
        )
        self._store.upsert_branch(updated)
        return updated

    def rank_branches(
        self,
        evaluations: list[BranchEvaluation],
        *,
        risk_weight: float = 0.20,
        cost_weight: float = 0.15,
    ) -> list[BranchRank]:
        ranks: list[BranchRank] = []
        for evaluation in evaluations:
            utility = (
                evaluation.success_rate
                - risk_weight * evaluation.risk_score
                - cost_weight * evaluation.cost_score
            )
            ranks.append(BranchRank(branch_id=evaluation.branch_id, utility=utility))
        return sorted(ranks, key=lambda rank: rank.utility, reverse=True)
