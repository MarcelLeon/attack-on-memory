"""Runtime context assembly for agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from attack_on_memory.application.services import RetrievalService
from attack_on_memory.domain.models import MemoryCitation, ProjectedMemory, RetrievalQuery, TaskIntent
from attack_on_memory.governance.policies import MemoryGovernor


@dataclass(frozen=True)
class ContextPacket:
    """Context payload delivered to an execution agent."""

    request_id: str
    actor: str
    role: str
    domain: str
    task: str
    memories: tuple[ProjectedMemory, ...]
    citations: tuple[MemoryCitation, ...]
    diagnostics: dict[str, int] = field(default_factory=dict)


class ContextAssembler:
    """Assemble retrieval results into a governance-approved context packet."""

    def __init__(self, retrieval_service: RetrievalService, governor: MemoryGovernor) -> None:
        self._retrieval_service = retrieval_service
        self._governor = governor

    def assemble(
        self,
        intent: TaskIntent,
        *,
        top_k: int = 5,
        lookback_days: int | None = 30,
        seed_ids: tuple[str, ...] = (),
        graph_hops: int = 1,
    ) -> ContextPacket:
        lookback = None if lookback_days is None else timedelta(days=lookback_days)
        query = RetrievalQuery(
            intent=intent,
            top_k=top_k,
            lookback=lookback,
            seed_ids=seed_ids,
            graph_hops=graph_hops,
        )

        retrieved = self._retrieval_service.retrieve(query)
        memories, citations = self._governor.project(retrieved, intent)

        diagnostics = {
            "retrieved": len(retrieved),
            "projected": len(memories),
            "redacted": len(retrieved) - len(memories),
        }
        return ContextPacket(
            request_id=intent.request_id,
            actor=intent.actor,
            role=intent.role,
            domain=intent.domain,
            task=intent.task,
            memories=tuple(memories),
            citations=tuple(citations),
            diagnostics=diagnostics,
        )
