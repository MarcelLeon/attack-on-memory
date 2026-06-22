from __future__ import annotations

import unittest
from datetime import timedelta

from attack_on_memory.application.conflict_resolution import (
    ConflictMode,
    ConflictResolver,
)
from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.domain.models import (
    ConflictOutcome,
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryScope,
    Sensitivity,
    TaskIntent,
    utc_now,
)
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.runtime.context import ContextAssembler


class ConflictResolutionTests(unittest.TestCase):
    def test_prefer_stronger_selects_evidence_authority_and_audits_decision(self) -> None:
        now = utc_now()
        store = InMemoryStore()
        capture = CaptureService(store)
        scope = MemoryScope(domain="operations", task="recovery")
        strong = MemoryAtom(
            id="verified-plan",
            claim="Throttle writes before recovery.",
            evidence=(
                Evidence(ref="runbook#9", source="signed-runbook", captured_at=now),
                Evidence(ref="incident#4", source="production-log", captured_at=now),
            ),
            source_agent="reliability-reviewer",
            confidence=0.98,
            scope=scope,
            created_at=now - timedelta(hours=1),
            ttl=timedelta(days=30),
            tags=("throttle", "recovery"),
        )
        weak = MemoryAtom(
            id="stale-plan",
            claim="Do not throttle writes before recovery.",
            evidence=(
                Evidence(
                    ref="chat#2",
                    source="unreviewed-chat",
                    captured_at=now - timedelta(days=10),
                ),
            ),
            source_agent="assistant",
            confidence=0.40,
            scope=scope,
            created_at=now - timedelta(days=10),
            ttl=timedelta(days=30),
            tags=("throttle", "recovery"),
        )
        capture.capture(strong)
        capture.capture(weak)
        store.add_edge(
            MemoryEdge(
                source_id=strong.id,
                target_id=weak.id,
                edge_type=EdgeType.CONTRADICTS,
            )
        )

        governor = MemoryGovernor()
        governor.register_policy(
            DisclosurePolicy(
                role="planner",
                max_sensitivity=Sensitivity.INTERNAL,
                allowed_domains=frozenset({"operations"}),
                allowed_tasks=frozenset({"recovery"}),
            )
        )
        assembler = ContextAssembler(
            RetrievalService(store),
            governor,
            ConflictResolver(mode=ConflictMode.PREFER_STRONGER),
        )
        packet = assembler.assemble(
            TaskIntent(
                request_id="resolve-1",
                actor="openclaw",
                role="planner",
                domain="operations",
                task="recovery",
                query="Should we throttle writes before recovery?",
                as_of=now,
            ),
            top_k=10,
        )

        self.assertEqual([item.atom_id for item in packet.memories], [strong.id])
        self.assertEqual(len(packet.conflict_decisions), 1)
        decision = packet.conflict_decisions[0]
        self.assertEqual(decision.outcome, ConflictOutcome.SELECTED)
        self.assertEqual(decision.selected_id, strong.id)
        self.assertIn("authority", decision.rationale)
        self.assertEqual(packet.diagnostics["conflict_resolved"], 1)

    def test_prefer_stronger_quarantines_ambiguous_conflict(self) -> None:
        from attack_on_memory.domain.models import RetrievedMemory

        now = utc_now()
        scope = MemoryScope(domain="operations", task="recovery")

        def atom(atom_id: str) -> MemoryAtom:
            return MemoryAtom(
                id=atom_id,
                claim=atom_id,
                evidence=(Evidence(ref=atom_id, source="same", captured_at=now),),
                source_agent="same",
                confidence=0.8,
                scope=scope,
                created_at=now,
                ttl=timedelta(days=1),
            )

        first = RetrievedMemory(atom("a"), 0.7, "risk", ("b",))
        second = RetrievedMemory(atom("b"), 0.7, "risk", ("a",))
        selected, decisions = ConflictResolver(
            mode=ConflictMode.PREFER_STRONGER
        ).resolve([first, second])

        self.assertEqual(selected, [])
        self.assertEqual(decisions[0].outcome, ConflictOutcome.QUARANTINED)


if __name__ == "__main__":
    unittest.main()
