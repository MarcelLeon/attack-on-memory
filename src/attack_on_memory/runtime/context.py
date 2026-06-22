"""Runtime context assembly for agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from attack_on_memory.application.conflict_resolution import ConflictResolver
from attack_on_memory.application.services import RetrievalService
from attack_on_memory.domain.models import (
    ConflictDecision,
    ConflictOutcome,
    MemoryCitation,
    ProjectedMemory,
    RetrievalQuery,
    TaskIntent,
)
from attack_on_memory.governance.policies import MemoryGovernor
from attack_on_memory.governance.audit import (
    GovernanceAuditSink,
    InMemoryGovernanceAuditSink,
)


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
    conflict_decisions: tuple[ConflictDecision, ...] = ()
    governance_audit_id: str | None = None
    diagnostics: dict[str, int] = field(default_factory=dict)


class ContextAssembler:
    """Assemble retrieval results into a governance-approved context packet."""

    def __init__(
        self,
        retrieval_service: RetrievalService,
        governor: MemoryGovernor,
        conflict_resolver: ConflictResolver | None = None,
        governance_audit_sink: GovernanceAuditSink | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._governor = governor
        self._conflict_resolver = conflict_resolver or ConflictResolver()
        self._governance_audit_sink = (
            governance_audit_sink or InMemoryGovernanceAuditSink()
        )

    @property
    def governance_audit_sink(self) -> GovernanceAuditSink:
        """Administrative audit plane; never serialized into memory projections."""
        return self._governance_audit_sink

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
        resolved, conflict_decisions = self._conflict_resolver.resolve(retrieved)
        evaluation = self._governor.evaluate(resolved, intent)
        memories = evaluation.memories
        citations = evaluation.citations
        self._governance_audit_sink.record_governance_decisions(
            evaluation.decisions
        )
        denied_reasons = [
            decision.reason_code
            for decision in evaluation.decisions
            if not decision.allowed
        ]

        diagnostics = {
            "retrieved": len(retrieved),
            "projected": len(memories),
            "redacted": len(retrieved) - len(memories),
            "inherited": sum(
                1 for citation in citations if "inherited_from=" in citation.reason
            ),
            "contradictions": sum(
                1 for citation in citations if "contradiction_risk=" in citation.reason
            ),
            "conflict_groups": len(conflict_decisions),
            "conflict_resolved": sum(
                1
                for decision in conflict_decisions
                if decision.outcome is ConflictOutcome.SELECTED
            ),
            "conflict_quarantined": sum(
                len(decision.memory_ids)
                for decision in conflict_decisions
                if decision.outcome is ConflictOutcome.QUARANTINED
            ),
            "governance_denied": len(denied_reasons),
            "purpose_denied": sum(
                reason in {"purpose.required", "purpose.not_allowed"}
                for reason in denied_reasons
            ),
            "sensitivity_denied": denied_reasons.count("sensitivity.exceeded"),
            "policy_missing": denied_reasons.count("policy.missing"),
        }
        return ContextPacket(
            request_id=intent.request_id,
            actor=intent.actor,
            role=intent.role,
            domain=intent.domain,
            task=intent.task,
            memories=tuple(memories),
            citations=tuple(citations),
            conflict_decisions=conflict_decisions,
            governance_audit_id=(
                intent.request_id if evaluation.decisions else None
            ),
            diagnostics=diagnostics,
        )
