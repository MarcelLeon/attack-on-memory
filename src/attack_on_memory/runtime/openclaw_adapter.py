"""OpenClaw-facing adapter for context injection and feedback logging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from attack_on_memory.application.services import CaptureService
from attack_on_memory.domain.models import MemoryAtom, TaskIntent, utc_now
from attack_on_memory.evals.metrics import EvalTracker
from attack_on_memory.runtime.context import ContextAssembler, ContextPacket


@dataclass(frozen=True)
class OpenClawTaskEvent:
    """Minimal runtime contract for OpenClaw integration."""

    task_id: str
    actor: str
    role: str
    domain: str
    task: str
    objective: str
    branch_id: str = "main"
    seed_memory_ids: tuple[str, ...] = ()

    def to_intent(self, at: datetime | None = None) -> TaskIntent:
        return TaskIntent(
            request_id=self.task_id,
            actor=self.actor,
            role=self.role,
            domain=self.domain,
            task=self.task,
            query=self.objective,
            branch_id=self.branch_id,
            as_of=at or utc_now(),
        )


class OpenClawMemoryAdapter:
    """Bridge between OpenClaw runtime and the memory framework."""

    def __init__(
        self,
        *,
        context_assembler: ContextAssembler,
        capture_service: CaptureService,
        tracker: EvalTracker,
    ) -> None:
        self._context_assembler = context_assembler
        self._capture_service = capture_service
        self._tracker = tracker

    def build_context(
        self,
        event: OpenClawTaskEvent,
        *,
        at: datetime | None = None,
        top_k: int = 5,
        lookback_days: int | None = 30,
        graph_hops: int = 1,
    ) -> ContextPacket:
        intent = event.to_intent(at)
        packet = self._context_assembler.assemble(
            intent,
            top_k=top_k,
            lookback_days=lookback_days,
            seed_ids=event.seed_memory_ids,
            graph_hops=graph_hops,
        )
        self._tracker.record_retrieval(hit=len(packet.memories) > 0)
        return packet

    def record_outcome(
        self,
        *,
        success: bool,
        latency_ms: float,
        token_cost: float,
        error_signature: str | None = None,
        conflict: bool = False,
        contamination: bool = False,
        new_memories: tuple[MemoryAtom, ...] = (),
    ) -> None:
        self._tracker.record_task(
            success=success,
            latency_ms=latency_ms,
            token_cost=token_cost,
            error_signature=error_signature,
        )
        if conflict:
            self._tracker.record_conflict()
        if contamination:
            self._tracker.record_contamination()
        for atom in new_memories:
            self._capture_service.capture(atom)

    def metrics_snapshot(self) -> dict[str, float]:
        return self._tracker.snapshot()
