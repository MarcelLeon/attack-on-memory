from __future__ import annotations

import tempfile
import threading
import unittest
import sqlite3
import multiprocessing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.domain.models import (
    Branch,
    BranchStatus,
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryScope,
    RetrievalQuery,
    TaskIntent,
)
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.infrastructure.hashing_embedder import HashingTextEmbedder
from attack_on_memory.infrastructure.sqlite_store import SCHEMA_VERSION, SQLiteStore
from attack_on_memory.infrastructure.store import MemoryStore


NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _process_write_batch(
    database_path: str,
    worker: int,
    start_event,
) -> None:
    start_event.wait()
    with SQLiteStore(database_path) as store:
        for index in range(25):
            store.upsert_atom(_atom(f"process-{worker}-{index}"))


def _atom(
    atom_id: str,
    *,
    branch_id: str = "main",
    age_hours: int = 1,
    metadata: dict[str, object] | None = None,
) -> MemoryAtom:
    return MemoryAtom(
        id=atom_id,
        claim=f"Recovery fact {atom_id}",
        evidence=(
            Evidence(
                ref=f"evidence:{atom_id}",
                source="contract-test",
                captured_at=NOW - timedelta(hours=age_hours),
                note="round-trip",
            ),
        ),
        source_agent="contract-test",
        confidence=0.9,
        scope=MemoryScope(domain="ops", task="recovery", owner="shared"),
        created_at=NOW - timedelta(hours=age_hours),
        ttl=timedelta(days=30),
        branch_id=branch_id,
        tags=("recovery", atom_id),
        metadata=metadata or {},
    )


def _exercise_contract(store: MemoryStore) -> dict[str, object]:
    store.upsert_branch(
        Branch(id="main", name="Main", hypothesis="baseline", created_at=NOW)
    )
    store.upsert_branch(
        Branch(
            id="child",
            name="Child",
            hypothesis="alternative",
            created_at=NOW,
            parent_id="main",
        )
    )
    parent = _atom("parent", age_hours=4, metadata={"memory_key": "plan"})
    child = _atom("child", branch_id="child", metadata={"memory_key": "plan"})
    support = _atom("support", age_hours=2)
    store.upsert_atom(parent)
    store.upsert_atom(child)
    store.upsert_atom(support)
    edge = MemoryEdge(
        source_id=child.id,
        target_id=support.id,
        edge_type=EdgeType.SUPPORTS,
        weight=0.75,
    )
    store.add_edge(edge)

    inherited = store.list_atoms("child", include_inherited=True)
    retrieval = RetrievalService(store).retrieve(
        RetrievalQuery(
            intent=TaskIntent(
                request_id="contract",
                actor="tester",
                role="planner",
                domain="ops",
                task="recovery",
                query="Recovery fact support",
                branch_id="child",
                as_of=NOW,
            ),
            top_k=10,
        )
    )
    return {
        "parent": store.get_atom("parent"),
        "lineage": store.resolve_branch_lineage("child"),
        "inherited_ids": tuple(atom.id for atom in inherited),
        "edges": tuple(store.list_edges(edge_type=EdgeType.SUPPORTS)),
        "neighbors": store.neighboring_atom_ids(("child",), max_hops=1),
        "retrieved_ids": tuple(item.atom.id for item in retrieval),
        "active_branches": tuple(branch.id for branch in store.list_branches(BranchStatus.ACTIVE)),
    }


class StoreContractTests(unittest.TestCase):
    def test_in_memory_and_sqlite_have_matching_semantics(self) -> None:
        expected = _exercise_contract(InMemoryStore())
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteStore(Path(directory) / "memory.db") as store:
                actual = _exercise_contract(store)
                self.assertEqual(store.schema_version, SCHEMA_VERSION)
        self.assertEqual(actual, expected)

    def test_sqlite_recovers_atoms_edges_and_branches_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            first = SQLiteStore(path)
            snapshot = _exercise_contract(first)
            first.close()

            with SQLiteStore(path) as reopened:
                self.assertEqual(reopened.get_atom("parent"), snapshot["parent"])
                self.assertEqual(reopened.resolve_branch_lineage("child"), ("child", "main"))
                self.assertEqual(
                    reopened.neighboring_atom_ids(("child",), max_hops=1),
                    {"support"},
                )
                self.assertEqual(len(reopened.list_edges()), 1)

    def test_sqlite_transaction_rolls_back_all_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with SQLiteStore(path) as store:
                with self.assertRaisesRegex(RuntimeError, "abort"):
                    with store.transaction():
                        store.upsert_atom(_atom("rolled-back-a"))
                        store.upsert_atom(_atom("rolled-back-b"))
                        raise RuntimeError("abort")
                self.assertIsNone(store.get_atom("rolled-back-a"))
                self.assertIsNone(store.get_atom("rolled-back-b"))

    def test_sqlite_nested_transaction_uses_savepoint(self) -> None:
        with SQLiteStore(":memory:") as store:
            with store.transaction():
                store.upsert_atom(_atom("outer-a"))
                with self.assertRaisesRegex(RuntimeError, "inner abort"):
                    with store.transaction():
                        store.upsert_atom(_atom("inner"))
                        raise RuntimeError("inner abort")
                store.upsert_atom(_atom("outer-b"))

            self.assertIsNotNone(store.get_atom("outer-a"))
            self.assertIsNotNone(store.get_atom("outer-b"))
            self.assertIsNone(store.get_atom("inner"))

    def test_sqlite_serializes_concurrent_writers_without_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteStore(Path(directory) / "memory.db") as store:
                barrier = threading.Barrier(5)

                def write_batch(worker: int) -> None:
                    barrier.wait()
                    for index in range(20):
                        CaptureService(store).capture(_atom(f"worker-{worker}-{index}"))

                threads = [
                    threading.Thread(target=write_batch, args=(worker,))
                    for worker in range(4)
                ]
                for thread in threads:
                    thread.start()
                barrier.wait()
                for thread in threads:
                    thread.join()

                self.assertEqual(len(store.list_atoms()), 80)

    def test_sqlite_rejects_non_json_metadata_at_boundary(self) -> None:
        with SQLiteStore(":memory:") as store:
            with self.assertRaisesRegex(TypeError, "non-JSON metadata"):
                store.upsert_atom(_atom("bad", metadata={"value": object()}))

    def test_sqlite_vector_index_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            embedder = HashingTextEmbedder(dimensions=64)
            with SQLiteStore(path, embedder=embedder) as store:
                store.upsert_atom(_atom("database-checksum"))
                store.upsert_atom(_atom("deployment-approval"))

            with SQLiteStore(path, embedder=embedder) as reopened:
                matches = reopened.search(query="Recovery fact database-checksum", top_k=2)
                self.assertEqual(matches[0].atom_id, "database-checksum")
                self.assertGreater(matches[0].score, matches[1].score)
                retrieved = RetrievalService(reopened, vector_index=reopened).retrieve(
                    RetrievalQuery(
                        intent=TaskIntent(
                            request_id="vector-restart",
                            actor="tester",
                            role="planner",
                            domain="ops",
                            task="recovery",
                            query="Recovery fact database-checksum",
                            as_of=NOW,
                        ),
                        top_k=2,
                    )
                )
                self.assertEqual(retrieved[0].atom.id, "database-checksum")
                self.assertIn("vector_match=", retrieved[0].reason)

    def test_sqlite_migrates_v1_fixture_through_current_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory-v1.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO store_metadata VALUES ('schema_version', '1');
                CREATE TABLE memory_atoms (
                    id TEXT PRIMARY KEY,
                    branch_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE memory_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES memory_atoms(id),
                    target_id TEXT NOT NULL REFERENCES memory_atoms(id),
                    edge_type TEXT NOT NULL,
                    weight REAL NOT NULL
                );
                CREATE TABLE branches (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            connection.close()

            embedder = HashingTextEmbedder(dimensions=32)
            with SQLiteStore(path, embedder=embedder) as migrated:
                self.assertEqual(migrated.schema_version, SCHEMA_VERSION)
                migrated.upsert_atom(_atom("after-migration"))
                self.assertEqual(
                    migrated.search(query="after-migration", top_k=1)[0].atom_id,
                    "after-migration",
                )

    def test_sqlite_online_backup_is_consistent_and_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_path = root / "live.db"
            backup_path = root / "backup.db"
            restored_path = root / "restored.db"
            embedder = HashingTextEmbedder(dimensions=32)
            with SQLiteStore(live_path, embedder=embedder) as live:
                live.upsert_atom(_atom("before-backup"))
                snapshot = live.verify_integrity()
                self.assertEqual(snapshot["atoms"], 1)
                live.backup_to(backup_path)
                live.upsert_atom(_atom("after-backup"))

            with SQLiteStore.restore_from(
                backup_path,
                restored_path,
                embedder=embedder,
            ) as restored:
                self.assertIsNotNone(restored.get_atom("before-backup"))
                self.assertIsNone(restored.get_atom("after-backup"))
                self.assertEqual(restored.verify_integrity()["atoms"], 1)
                self.assertEqual(
                    restored.search(query="before-backup", top_k=1)[0].atom_id,
                    "before-backup",
                )

    def test_sqlite_recovers_over_corrupted_primary_from_verified_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_path = root / "live.db"
            backup_path = root / "backup.db"
            with SQLiteStore(live_path) as live:
                live.upsert_atom(_atom("durable"))
                live.backup_to(backup_path)

            live_path.write_bytes(b"not-a-sqlite-database")
            with SQLiteStore.restore_from(
                backup_path,
                live_path,
                overwrite=True,
            ) as recovered:
                self.assertIsNotNone(recovered.get_atom("durable"))
                self.assertEqual(recovered.verify_integrity()["atoms"], 1)

    def test_sqlite_multi_process_writers_do_not_lose_committed_atoms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.db"
            with SQLiteStore(path):
                pass
            context = multiprocessing.get_context("spawn")
            start_event = context.Event()
            processes = [
                context.Process(
                    target=_process_write_batch,
                    args=(str(path), worker, start_event),
                )
                for worker in range(4)
            ]
            for process in processes:
                process.start()
            start_event.set()
            for process in processes:
                process.join(timeout=15)
                if process.is_alive():
                    process.terminate()
                    process.join()
                self.assertEqual(process.exitcode, 0)

            with SQLiteStore(path) as reopened:
                self.assertEqual(len(reopened.list_atoms()), 100)
                self.assertEqual(reopened.verify_integrity()["atoms"], 100)


if __name__ == "__main__":
    unittest.main()
