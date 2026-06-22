from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from attack_on_memory.application.lifecycle import MemoryLifecycleService
from attack_on_memory.application.services import RetrievalService
from attack_on_memory.domain.models import (
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryLifecycleState,
    MemoryScope,
    RetrievalQuery,
    TaskIntent,
)
from attack_on_memory.infrastructure.hashing_embedder import HashingTextEmbedder
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.infrastructure.sqlite_store import SQLiteStore


NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _atom(
    atom_id: str,
    *,
    claim: str | None = None,
    age_days: int = 0,
    ttl_days: int = 30,
    supersedes: tuple[str, ...] = (),
) -> MemoryAtom:
    return MemoryAtom(
        id=atom_id,
        claim=claim or f"verified recovery {atom_id}",
        evidence=(
            Evidence(
                ref=f"evidence:{atom_id}",
                source="lifecycle-test",
                captured_at=NOW - timedelta(days=age_days),
            ),
        ),
        source_agent="lifecycle-test",
        confidence=0.9,
        scope=MemoryScope(domain="ops", task="recovery"),
        created_at=NOW - timedelta(days=age_days),
        ttl=timedelta(days=ttl_days),
        tags=("verified", "recovery", atom_id),
        metadata={"supersedes": list(supersedes)} if supersedes else {},
    )


def _retrieve_ids(store) -> set[str]:
    results = RetrievalService(store).retrieve(
        RetrievalQuery(
            intent=TaskIntent(
                request_id="lifecycle-query",
                actor="tester",
                role="planner",
                domain="ops",
                task="recovery",
                query="verified recovery",
                as_of=NOW,
            ),
            top_k=20,
            lookback=None,
        )
    )
    return {item.atom.id for item in results}


class MemoryLifecycleTests(unittest.TestCase):
    def test_quarantine_exits_retrieval_and_restore_is_audited(self) -> None:
        for store in (
            InMemoryStore(),
            SQLiteStore(":memory:", embedder=HashingTextEmbedder(dimensions=32)),
        ):
            with self.subTest(store=type(store).__name__):
                store.upsert_atom(_atom("suspect"))
                lifecycle = MemoryLifecycleService(store)
                self.assertIn("suspect", _retrieve_ids(store))

                quarantined = lifecycle.quarantine(
                    "suspect",
                    actor="security-reviewer",
                    reason_code="poisoning.suspected",
                    changed_at=NOW,
                )
                self.assertEqual(quarantined.version, 1)
                self.assertNotIn("suspect", _retrieve_ids(store))
                if isinstance(store, SQLiteStore):
                    self.assertEqual(store.search(query="suspect", top_k=10), [])

                restored = lifecycle.restore(
                    "suspect",
                    actor="security-reviewer",
                    reason_code="review.cleared",
                    changed_at=NOW + timedelta(minutes=1),
                )
                self.assertEqual(restored.version, 2)
                self.assertIn("suspect", _retrieve_ids(store))
                self.assertEqual(
                    [event.state for event in store.list_lifecycle_events("suspect")],
                    [MemoryLifecycleState.QUARANTINED, MemoryLifecycleState.ACTIVE],
                )
                if isinstance(store, SQLiteStore):
                    store.close()

    def test_transition_time_cannot_move_backwards(self) -> None:
        store = InMemoryStore()
        store.upsert_atom(_atom("clocked"))
        lifecycle = MemoryLifecycleService(store)
        lifecycle.quarantine(
            "clocked",
            actor="reviewer",
            reason_code="review.hold",
            changed_at=NOW,
        )
        with self.assertRaisesRegex(ValueError, "backwards"):
            lifecycle.restore(
                "clocked",
                actor="reviewer",
                reason_code="review.cleared",
                changed_at=NOW - timedelta(seconds=1),
            )

    def test_illegal_transition_fails_closed(self) -> None:
        store = InMemoryStore()
        store.upsert_atom(_atom("superseded"))
        lifecycle = MemoryLifecycleService(store)
        lifecycle.quarantine(
            "superseded",
            actor="reviewer",
            reason_code="review.hold",
            changed_at=NOW,
        )
        lifecycle.restore(
            "superseded",
            actor="reviewer",
            reason_code="review.cleared",
            changed_at=NOW,
        )
        with self.assertRaisesRegex(ValueError, "active -> active"):
            lifecycle.restore(
                "superseded",
                actor="reviewer",
                reason_code="review.duplicate",
                changed_at=NOW,
            )

    def test_consolidation_supersedes_sources_and_preserves_derivation(self) -> None:
        store = InMemoryStore()
        store.upsert_atom(_atom("source-a"))
        store.upsert_atom(_atom("source-b"))
        summary = _atom(
            "summary",
            claim="verified recovery consolidated plan",
            supersedes=("source-a", "source-b"),
        )

        records = MemoryLifecycleService(store).consolidate(
            summary,
            ("source-a", "source-b"),
            actor="memory-consolidator",
            changed_at=NOW,
        )

        self.assertEqual({record.state for record in records}, {MemoryLifecycleState.SUPERSEDED})
        self.assertEqual(_retrieve_ids(store), {"summary"})
        self.assertEqual(
            {edge.target_id for edge in store.list_edges(source_id="summary")},
            {"source-a", "source-b"},
        )

    def test_consolidation_rejects_reused_summary_identity(self) -> None:
        store = InMemoryStore()
        for atom_id in ("source-a", "source-b", "summary"):
            store.upsert_atom(_atom(atom_id))
        with self.assertRaisesRegex(ValueError, "already exists"):
            MemoryLifecycleService(store).consolidate(
                _atom("summary", supersedes=("source-a", "source-b")),
                ("source-a", "source-b"),
                actor="memory-consolidator",
                changed_at=NOW,
            )

    def test_expiry_sweep_creates_audit_state(self) -> None:
        store = InMemoryStore()
        store.upsert_atom(_atom("expired", age_days=10, ttl_days=5))
        store.upsert_atom(_atom("fresh", age_days=1, ttl_days=5))

        records = MemoryLifecycleService(store).expire_due(at=NOW)

        self.assertEqual([record.atom_id for record in records], ["expired"])
        self.assertEqual(
            store.get_lifecycle("expired").state,
            MemoryLifecycleState.EXPIRED,
        )
        self.assertIsNone(store.get_lifecycle("fresh"))

    def test_poisoning_recovery_quarantines_derivation_neighborhood(self) -> None:
        store = InMemoryStore()
        for atom_id in ("poison", "derived", "downstream", "unrelated"):
            store.upsert_atom(_atom(atom_id))
        store.add_edge(MemoryEdge("derived", "poison", EdgeType.DERIVED_FROM))
        store.add_edge(MemoryEdge("downstream", "derived", EdgeType.DERIVED_FROM))

        records = MemoryLifecycleService(store).quarantine_related(
            "poison",
            actor="incident-responder",
            max_hops=2,
            changed_at=NOW,
        )

        self.assertEqual(
            {record.atom_id for record in records},
            {"poison", "derived", "downstream"},
        )
        self.assertEqual(_retrieve_ids(store), {"unrelated"})

    def test_forget_erases_content_graph_and_vector_but_keeps_minimal_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            embedder = HashingTextEmbedder(dimensions=32)
            with SQLiteStore(path, embedder=embedder) as store:
                store.upsert_atom(_atom("erase-me"))
                store.upsert_atom(_atom("keep-me"))
                store.add_edge(MemoryEdge("erase-me", "keep-me", EdgeType.SUPPORTS))
                MemoryLifecycleService(store).forget(
                    "erase-me",
                    actor="privacy-officer",
                    reason_code="privacy.erasure",
                    changed_at=NOW,
                )
                self.assertIsNone(store.get_atom("erase-me"))
                self.assertEqual(store.list_edges(), [])
                self.assertTrue(
                    all(match.atom_id != "erase-me" for match in store.search(query="erase-me", top_k=10))
                )

            with SQLiteStore(path, embedder=embedder) as reopened:
                self.assertIsNone(reopened.get_atom("erase-me"))
                tombstone = reopened.get_lifecycle("erase-me")
                self.assertEqual(tombstone.state, MemoryLifecycleState.FORGOTTEN)
                self.assertEqual(tombstone.reason_code, "privacy.erasure")
                self.assertNotIn("claim", tombstone.__dict__)


if __name__ == "__main__":
    unittest.main()
