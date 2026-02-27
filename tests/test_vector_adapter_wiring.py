from __future__ import annotations

import unittest
from datetime import timedelta

from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.application.vector_adapter import VectorMatch
from attack_on_memory.domain.models import Evidence, MemoryAtom, MemoryScope, RetrievalQuery, Sensitivity, TaskIntent, utc_now
from attack_on_memory.infrastructure.in_memory import InMemoryStore


class FakeVectorIndex:
    def search(self, *, query: str, top_k: int) -> list[VectorMatch]:  # noqa: ARG002
        return [VectorMatch(atom_id="mem_target", score=0.91)]


class VectorAdapterWiringTests(unittest.TestCase):
    def test_vector_match_bonus_is_applied(self) -> None:
        store = InMemoryStore()
        capture = CaptureService(store)
        now = utc_now()

        capture.capture(
            MemoryAtom(
                id="mem_target",
                claim="priority memory for vector hit",
                evidence=(Evidence(ref="e1", source="test", captured_at=now),),
                source_agent="tester",
                confidence=0.7,
                scope=MemoryScope(domain="ops", task="triage"),
                created_at=now - timedelta(days=1),
                ttl=timedelta(days=30),
                sensitivity=Sensitivity.INTERNAL,
            )
        )

        retrieval = RetrievalService(store, vector_index=FakeVectorIndex(), vector_bonus=0.25)
        query = RetrievalQuery(
            intent=TaskIntent(
                request_id="r1",
                actor="tester",
                role="planner",
                domain="ops",
                task="triage",
                query="priority memory",
                as_of=now,
            ),
            top_k=3,
            lookback=timedelta(days=10),
        )
        results = retrieval.retrieve(query)
        self.assertEqual(results[0].atom.id, "mem_target")
        self.assertIn("vector_match=0.91(+0.25)", results[0].reason)


if __name__ == "__main__":
    unittest.main()
