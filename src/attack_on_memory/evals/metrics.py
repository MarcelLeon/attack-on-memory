"""Evaluation and observability metrics for the memory framework."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalTracker:
    """Collect runtime metrics used for experiment and production validation."""

    retrieval_requests: int = 0
    retrieval_hits: int = 0
    conflicts: int = 0
    contaminations: int = 0

    tasks_total: int = 0
    tasks_success: int = 0
    total_latency_ms: float = 0.0
    total_token_cost: float = 0.0

    _error_counter: dict[str, int] = field(default_factory=dict)
    repeated_errors: int = 0

    def record_retrieval(self, hit: bool) -> None:
        self.retrieval_requests += 1
        if hit:
            self.retrieval_hits += 1

    def record_conflict(self) -> None:
        self.conflicts += 1

    def record_contamination(self) -> None:
        self.contaminations += 1

    def record_task(
        self,
        *,
        success: bool,
        latency_ms: float,
        token_cost: float,
        error_signature: str | None = None,
    ) -> None:
        self.tasks_total += 1
        if success:
            self.tasks_success += 1

        self.total_latency_ms += max(0.0, latency_ms)
        self.total_token_cost += max(0.0, token_cost)

        if error_signature is None:
            return

        count = self._error_counter.get(error_signature, 0)
        if count >= 1:
            self.repeated_errors += 1
        self._error_counter[error_signature] = count + 1

    def snapshot(self) -> dict[str, float]:
        return {
            "hit_rate": _safe_div(self.retrieval_hits, self.retrieval_requests),
            "task_success_rate": _safe_div(self.tasks_success, self.tasks_total),
            "repeat_error_rate": _safe_div(self.repeated_errors, self.tasks_total),
            "conflict_rate": _safe_div(self.conflicts, self.tasks_total),
            "contamination_rate": _safe_div(self.contaminations, self.tasks_total),
            "avg_latency_ms": _safe_div(self.total_latency_ms, self.tasks_total),
            "avg_token_cost": _safe_div(self.total_token_cost, self.tasks_total),
        }


def _safe_div(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return num / den
