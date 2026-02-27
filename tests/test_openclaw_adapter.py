from __future__ import annotations

import unittest
from datetime import timedelta

from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.domain.models import Evidence, MemoryAtom, MemoryScope, Sensitivity, utc_now
from attack_on_memory.evals.metrics import EvalTracker
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.runtime.context import ContextAssembler
from attack_on_memory.runtime.openclaw_adapter import OpenClawMemoryAdapter, OpenClawTaskEvent


class OpenClawAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore()
        capture = CaptureService(self.store)
        retrieval = RetrievalService(self.store)

        governor = MemoryGovernor()
        governor.register_policy(
            DisclosurePolicy(
                role="planner",
                max_sensitivity=Sensitivity.RESTRICTED,
                allowed_domains=frozenset({"operations"}),
                allowed_tasks=frozenset({"incident-response"}),
                min_confidence=0.5,
            )
        )

        assembler = ContextAssembler(retrieval, governor)
        tracker = EvalTracker()
        self.adapter = OpenClawMemoryAdapter(
            context_assembler=assembler,
            capture_service=capture,
            tracker=tracker,
        )

        now = utc_now()
        atom = MemoryAtom(
            id="mem_incident_plan",
            claim="先限流后扩容可降低故障恢复时间",
            evidence=(Evidence(ref="incident#66", source="log", captured_at=now),),
            source_agent="reviewer",
            confidence=0.88,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(days=1),
            ttl=timedelta(days=45),
            sensitivity=Sensitivity.INTERNAL,
        )
        capture.capture(atom)

    def test_context_build_and_metrics(self) -> None:
        event = OpenClawTaskEvent(
            task_id="task-1",
            actor="planner-agent",
            role="planner",
            domain="operations",
            task="incident-response",
            objective="给出应急方案",
        )

        context = self.adapter.build_context(event, top_k=3, lookback_days=30)
        self.assertEqual(context.request_id, "task-1")
        self.assertGreaterEqual(len(context.memories), 1)

        self.adapter.record_outcome(
            success=False,
            latency_ms=120.0,
            token_cost=1024.0,
            error_signature="timeout",
            conflict=True,
        )
        self.adapter.record_outcome(
            success=False,
            latency_ms=100.0,
            token_cost=900.0,
            error_signature="timeout",
        )

        snapshot = self.adapter.metrics_snapshot()
        self.assertAlmostEqual(snapshot["hit_rate"], 1.0)
        self.assertAlmostEqual(snapshot["repeat_error_rate"], 0.5)
        self.assertAlmostEqual(snapshot["conflict_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
