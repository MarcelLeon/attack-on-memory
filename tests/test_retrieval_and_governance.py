from __future__ import annotations

import unittest
from datetime import timedelta

from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.domain.models import (
    Branch,
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryScope,
    RetrievalQuery,
    Sensitivity,
    TaskIntent,
    utc_now,
)
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor
from attack_on_memory.infrastructure.in_memory import InMemoryStore


class RetrievalAndGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore()
        self.capture = CaptureService(self.store)
        self.retrieval = RetrievalService(self.store)

        now = utc_now()
        self.fresh_internal = MemoryAtom(
            id="mem_fresh_internal",
            claim="处理故障应先启用 v2 限流",
            evidence=(Evidence(ref="incident#1", source="log", captured_at=now),),
            source_agent="planner",
            confidence=0.90,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(days=2),
            ttl=timedelta(days=30),
            sensitivity=Sensitivity.INTERNAL,
            tags=("限流", "故障"),
        )
        self.restricted = MemoryAtom(
            id="mem_restricted",
            claim="客户 PII 不能写入执行日志",
            evidence=(Evidence(ref="policy#12", source="policy", captured_at=now),),
            source_agent="compliance",
            confidence=0.95,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(days=1),
            ttl=timedelta(days=120),
            sensitivity=Sensitivity.RESTRICTED,
            tags=("隐私", "合规"),
        )
        self.expired = MemoryAtom(
            id="mem_expired",
            claim="旧版本 v1 限流方案",
            evidence=(Evidence(ref="incident#old", source="log", captured_at=now),),
            source_agent="legacy",
            confidence=0.65,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(days=80),
            ttl=timedelta(days=7),
            sensitivity=Sensitivity.INTERNAL,
            tags=("旧版",),
        )

        self.capture.capture(self.fresh_internal)
        self.capture.capture(self.restricted)
        self.capture.capture(self.expired)

        self.store.add_edge(
            MemoryEdge(
                source_id=self.fresh_internal.id,
                target_id=self.restricted.id,
                edge_type=EdgeType.SUPPORTS,
            )
        )

    def test_time_window_and_ttl_filter(self) -> None:
        intent = TaskIntent(
            request_id="req-1",
            actor="openclaw",
            role="planner",
            domain="operations",
            task="incident-response",
            query="如何处理故障限流",
            as_of=utc_now(),
        )
        query = RetrievalQuery(intent=intent, top_k=10, lookback=timedelta(days=60))
        results = self.retrieval.retrieve(query)
        atom_ids = {item.atom.id for item in results}

        self.assertIn("mem_fresh_internal", atom_ids)
        self.assertIn("mem_restricted", atom_ids)
        self.assertNotIn("mem_expired", atom_ids)

    def test_governance_blocks_high_sensitivity_for_executor(self) -> None:
        intent = TaskIntent(
            request_id="req-2",
            actor="openclaw",
            role="executor",
            domain="operations",
            task="incident-response",
            query="执行故障处理方案",
            as_of=utc_now(),
        )
        query = RetrievalQuery(
            intent=intent,
            top_k=10,
            lookback=timedelta(days=60),
            seed_ids=("mem_fresh_internal",),
            graph_hops=1,
        )
        retrieved = self.retrieval.retrieve(query)
        self.assertTrue(any("graph_neighbor" in item.reason for item in retrieved))

        governor = MemoryGovernor()
        governor.register_policy(
            DisclosurePolicy(
                role="executor",
                max_sensitivity=Sensitivity.INTERNAL,
                allowed_domains=frozenset({"operations"}),
                allowed_tasks=frozenset({"incident-response"}),
                min_confidence=0.60,
            )
        )

        projected, citations = governor.project(retrieved, intent)
        projected_ids = {item.atom_id for item in projected}

        self.assertIn("mem_fresh_internal", projected_ids)
        self.assertNotIn("mem_restricted", projected_ids)
        self.assertTrue(all(citation.atom_id != "mem_restricted" for citation in citations))

    def test_branch_inheritance_prefers_child_override(self) -> None:
        now = utc_now()
        self.store.upsert_branch(
            Branch(
                id="main",
                name="Main",
                hypothesis="stable baseline",
                created_at=now,
            )
        )
        self.store.upsert_branch(
            Branch(
                id="branch_armin",
                name="Armin",
                hypothesis="refine retreat timing",
                parent_id="main",
                created_at=now,
            )
        )

        inherited_main = MemoryAtom(
            id="mem_main_signal",
            claim="Retreat after first smoke signal.",
            evidence=(Evidence(ref="plan#1", source="manual", captured_at=now),),
            source_agent="commander",
            confidence=0.70,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(days=5),
            ttl=timedelta(days=90),
            branch_id="main",
            tags=("retreat",),
            metadata={"memory_key": "retreat_signal"},
        )
        branch_override = MemoryAtom(
            id="mem_branch_signal",
            claim="Retreat only after confirming corridor stability.",
            evidence=(Evidence(ref="plan#2", source="review", captured_at=now),),
            source_agent="armin",
            confidence=0.92,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(hours=12),
            ttl=timedelta(days=90),
            branch_id="branch_armin",
            tags=("retreat", "stability"),
            metadata={"memory_key": "retreat_signal"},
        )
        inherited_support = MemoryAtom(
            id="mem_main_corridor",
            claim="Keep the north corridor clear for fallback.",
            evidence=(Evidence(ref="plan#3", source="manual", captured_at=now),),
            source_agent="commander",
            confidence=0.85,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(days=3),
            ttl=timedelta(days=90),
            branch_id="main",
            tags=("corridor", "fallback"),
        )

        self.capture.capture(inherited_main)
        self.capture.capture(branch_override)
        self.capture.capture(inherited_support)

        intent = TaskIntent(
            request_id="req-branch",
            actor="openclaw",
            role="planner",
            domain="operations",
            task="incident-response",
            query="Retreat timing and fallback corridor",
            branch_id="branch_armin",
            as_of=now,
        )
        results = self.retrieval.retrieve(
            RetrievalQuery(intent=intent, top_k=10, lookback=timedelta(days=30))
        )

        atom_ids = [item.atom.id for item in results]
        self.assertIn("mem_branch_signal", atom_ids)
        self.assertIn("mem_main_corridor", atom_ids)
        self.assertNotIn("mem_main_signal", atom_ids)
        support_reason = next(item.reason for item in results if item.atom.id == "mem_main_corridor")
        self.assertIn("inherited_from=main", support_reason)

    def test_contradiction_penalty_marks_conflicting_memories(self) -> None:
        now = utc_now()
        conflict_a = MemoryAtom(
            id="mem_conflict_a",
            claim="Throttle writes before restart.",
            evidence=(Evidence(ref="plan#a", source="playbook", captured_at=now),),
            source_agent="planner",
            confidence=0.83,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(hours=3),
            ttl=timedelta(days=30),
            tags=("throttle", "restart"),
        )
        conflict_b = MemoryAtom(
            id="mem_conflict_b",
            claim="Do not throttle writes before restart.",
            evidence=(Evidence(ref="plan#b", source="review", captured_at=now),),
            source_agent="reviewer",
            confidence=0.81,
            scope=MemoryScope(domain="operations", task="incident-response"),
            created_at=now - timedelta(hours=2),
            ttl=timedelta(days=30),
            tags=("throttle", "restart"),
        )
        self.capture.capture(conflict_a)
        self.capture.capture(conflict_b)
        self.store.add_edge(
            MemoryEdge(
                source_id="mem_conflict_a",
                target_id="mem_conflict_b",
                edge_type=EdgeType.CONTRADICTS,
            )
        )

        intent = TaskIntent(
            request_id="req-conflict",
            actor="openclaw",
            role="planner",
            domain="operations",
            task="incident-response",
            query="Should we throttle writes before restart?",
            as_of=now,
        )
        results = self.retrieval.retrieve(
            RetrievalQuery(intent=intent, top_k=10, lookback=timedelta(days=30))
        )

        flagged = [item for item in results if item.atom.id in {"mem_conflict_a", "mem_conflict_b"}]
        self.assertEqual(len(flagged), 2)
        self.assertTrue(all("contradiction_risk=" in item.reason for item in flagged))


if __name__ == "__main__":
    unittest.main()
