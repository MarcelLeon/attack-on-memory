"""North-star metric aggregation for governed memory quality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol


class EventLike(Protocol):
    """Subset of simulation event results needed for aggregation."""

    passed: bool
    diagnostics: Mapping[str, int]


class VariantLike(Protocol):
    """Subset of simulation variant results needed for aggregation."""

    passed: bool
    event_results: list[EventLike]
    metric_snapshot: Mapping[str, float]


@dataclass(frozen=True)
class NorthStarSnapshot:
    """Unlabeled scenario safety and governance aggregates."""

    total_variants: int
    passed_variants: int
    total_events: int
    passed_events: int
    retrieved_memories: int
    projected_memories: int
    redacted_memories: int
    inherited_memories: int
    contradiction_flags: int
    avg_task_success_rate: float

    @property
    def governed_safe_projection_rate(self) -> float:
        """Share of candidates projected without a conflict flag.

        This is a safety proxy, not a usefulness metric: scenario diagnostics do
        not contain human relevance labels.
        """
        if self.retrieved_memories == 0:
            return 0.0
        safe_projected = max(0, self.projected_memories - self.contradiction_flags)
        return safe_projected / self.retrieved_memories

    @property
    def governed_useful_memory_rate(self) -> float:
        """Backward-compatible alias for the former, overstated metric name."""
        return self.governed_safe_projection_rate

    @property
    def scenario_pass_rate(self) -> float:
        if self.total_variants == 0:
            return 0.0
        return self.passed_variants / self.total_variants

    @property
    def governed_context_pass_rate(self) -> float:
        if self.total_events == 0:
            return 0.0
        return self.passed_events / self.total_events

    @property
    def redaction_rate(self) -> float:
        if self.retrieved_memories == 0:
            return 0.0
        return self.redacted_memories / self.retrieved_memories

    @property
    def inheritance_rate(self) -> float:
        if self.projected_memories == 0:
            return 0.0
        return self.inherited_memories / self.projected_memories

    @property
    def contradiction_rate(self) -> float:
        if self.projected_memories == 0:
            return 0.0
        return self.contradiction_flags / self.projected_memories


def build_north_star_snapshot(results: Iterable[VariantLike]) -> NorthStarSnapshot:
    """Aggregate scenario runner results into the project north-star snapshot."""
    variants = list(results)
    total_events = 0
    passed_events = 0
    retrieved = 0
    projected = 0
    redacted = 0
    inherited = 0
    contradictions = 0
    task_success_rates: list[float] = []

    for variant in variants:
        task_success_rates.append(float(variant.metric_snapshot.get("task_success_rate", 0.0)))
        for event in variant.event_results:
            total_events += 1
            if event.passed:
                passed_events += 1
            diagnostics = event.diagnostics
            retrieved += int(diagnostics.get("retrieved", 0))
            projected += int(diagnostics.get("projected", 0))
            redacted += int(diagnostics.get("redacted", 0))
            inherited += int(diagnostics.get("inherited", 0))
            contradictions += int(diagnostics.get("contradictions", 0))

    avg_task_success_rate = (
        sum(task_success_rates) / len(task_success_rates)
        if task_success_rates
        else 0.0
    )

    return NorthStarSnapshot(
        total_variants=len(variants),
        passed_variants=sum(1 for variant in variants if variant.passed),
        total_events=total_events,
        passed_events=passed_events,
        retrieved_memories=retrieved,
        projected_memories=projected,
        redacted_memories=redacted,
        inherited_memories=inherited,
        contradiction_flags=contradictions,
        avg_task_success_rate=avg_task_success_rate,
    )
