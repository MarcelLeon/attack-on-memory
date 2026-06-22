"""Evidence-aware, auditable resolution of contradictory retrieved memories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from attack_on_memory.domain.models import (
    ConflictDecision,
    ConflictOutcome,
    RetrievedMemory,
)


class ConflictMode(str, Enum):
    """Runtime policy for contradictory memory groups."""

    FLAG = "flag"
    PREFER_STRONGER = "prefer_stronger"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class ConflictResolver:
    """Resolve connected contradiction groups without hiding the decision trail."""

    mode: ConflictMode = ConflictMode.FLAG
    min_authority_margin: float = 0.08

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_authority_margin <= 1.0:
            raise ValueError("min_authority_margin must be between 0 and 1")

    def resolve(
        self,
        retrieved: list[RetrievedMemory],
    ) -> tuple[list[RetrievedMemory], tuple[ConflictDecision, ...]]:
        by_id = {item.atom.id: item for item in retrieved}
        groups = _conflict_groups(retrieved, set(by_id))
        if not groups:
            return retrieved, ()

        excluded_ids: set[str] = set()
        decisions: list[ConflictDecision] = []
        for group_ids in groups:
            group = [by_id[item_id] for item_id in group_ids]
            decision = self._resolve_group(group)
            decisions.append(decision)
            if decision.outcome is ConflictOutcome.SELECTED:
                excluded_ids.update(set(group_ids) - {decision.selected_id})
            elif decision.outcome is ConflictOutcome.QUARANTINED:
                excluded_ids.update(group_ids)

        selected = [item for item in retrieved if item.atom.id not in excluded_ids]
        return selected, tuple(decisions)

    def _resolve_group(self, group: list[RetrievedMemory]) -> ConflictDecision:
        memory_ids = tuple(sorted(item.atom.id for item in group))
        if self.mode is ConflictMode.FLAG:
            return ConflictDecision(
                memory_ids=memory_ids,
                outcome=ConflictOutcome.FLAGGED,
                selected_id=None,
                rationale="policy=flag; contradictory memories retained for caller review",
            )
        if self.mode is ConflictMode.QUARANTINE:
            return ConflictDecision(
                memory_ids=memory_ids,
                outcome=ConflictOutcome.QUARANTINED,
                selected_id=None,
                rationale="policy=quarantine; contradictory memories withheld",
            )

        ranked = sorted(
            ((self._authority(item, group), item) for item in group),
            key=lambda pair: (-pair[0], pair[1].atom.id),
        )
        winner_score, winner = ranked[0]
        runner_up_score = ranked[1][0]
        margin = winner_score - runner_up_score
        if margin < self.min_authority_margin:
            return ConflictDecision(
                memory_ids=memory_ids,
                outcome=ConflictOutcome.QUARANTINED,
                selected_id=None,
                rationale=(
                    "policy=prefer_stronger; insufficient authority margin "
                    f"{margin:.3f} < {self.min_authority_margin:.3f}"
                ),
            )
        return ConflictDecision(
            memory_ids=memory_ids,
            outcome=ConflictOutcome.SELECTED,
            selected_id=winner.atom.id,
            rationale=(
                "policy=prefer_stronger; selected highest evidence authority "
                f"score={winner_score:.3f}; margin={margin:.3f}"
            ),
        )

    @staticmethod
    def _authority(item: RetrievedMemory, group: list[RetrievedMemory]) -> float:
        newest_evidence = max(evidence.captured_at for evidence in item.atom.evidence)
        group_times = [
            evidence.captured_at.timestamp()
            for candidate in group
            for evidence in candidate.atom.evidence
        ]
        oldest = min(group_times)
        newest = max(group_times)
        recency = (
            1.0
            if newest == oldest
            else (newest_evidence.timestamp() - oldest) / (newest - oldest)
        )
        evidence_depth = min(1.0, len(item.atom.evidence) / 3.0)
        return (
            0.45 * item.score
            + 0.35 * item.atom.confidence
            + 0.10 * recency
            + 0.10 * evidence_depth
        )


def _conflict_groups(
    retrieved: list[RetrievedMemory],
    candidate_ids: set[str],
) -> list[tuple[str, ...]]:
    adjacency: dict[str, set[str]] = {}
    for item in retrieved:
        neighbors = set(item.conflicting_ids) & candidate_ids
        if not neighbors:
            continue
        adjacency.setdefault(item.atom.id, set()).update(neighbors)
        for neighbor in neighbors:
            adjacency.setdefault(neighbor, set()).add(item.atom.id)

    groups: list[tuple[str, ...]] = []
    visited: set[str] = set()
    for start in sorted(adjacency):
        if start in visited:
            continue
        stack = [start]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(adjacency.get(current, set()) - visited)
        if len(component) > 1:
            groups.append(tuple(sorted(component)))
    return groups
