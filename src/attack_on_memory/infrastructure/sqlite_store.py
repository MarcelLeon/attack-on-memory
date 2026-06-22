"""Transactional SQLite storage for memory atoms, graph edges, and branches."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import tempfile
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

from attack_on_memory.application.vector_adapter import TextEmbedder, VectorMatch
from attack_on_memory.domain.models import (
    Branch,
    BranchStatus,
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryLifecycleRecord,
    MemoryLifecycleState,
    MemoryScope,
    Sensitivity,
)
from attack_on_memory.governance.policies import GovernanceDecision


SCHEMA_VERSION = 4


class SQLiteStore:
    """Durable store with atomic write groups and deterministic read semantics."""

    def __init__(self, path: str | Path, *, embedder: TextEmbedder | None = None) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._transaction_depth = 0
        self._closed = False
        self._embedder = embedder
        self._connection = sqlite3.connect(
            self._path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if self._path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
        self._initialize_schema()

    @property
    def schema_version(self) -> int:
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT value FROM store_metadata WHERE key = 'schema_version'"
            ).fetchone()
        return int(row["value"])

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes atomically; nested groups share the outer transaction."""
        with self._lock:
            self._ensure_open()
            outermost = self._transaction_depth == 0
            savepoint = f"aom_nested_{self._transaction_depth}"
            if outermost:
                self._connection.execute("BEGIN IMMEDIATE")
            else:
                self._connection.execute(f"SAVEPOINT {savepoint}")
            self._transaction_depth += 1
            try:
                yield
            except BaseException:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.execute("ROLLBACK")
                else:
                    self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.execute("COMMIT")
                else:
                    self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._transaction_depth:
                raise RuntimeError("cannot close SQLiteStore during a transaction")
            self._connection.close()
            self._closed = True

    def verify_integrity(self) -> dict[str, int]:
        """Run a full SQLite integrity check and return auditable object counts."""
        with self._lock:
            self._ensure_open()
            try:
                rows = self._connection.execute("PRAGMA integrity_check").fetchall()
                messages = tuple(str(row[0]) for row in rows)
                if messages != ("ok",):
                    raise RuntimeError(
                        f"SQLiteStore integrity check failed: {'; '.join(messages)}"
                    )
                return {
                    "schema_version": self.schema_version,
                    "atoms": int(
                        self._connection.execute(
                            "SELECT COUNT(*) FROM memory_atoms"
                        ).fetchone()[0]
                    ),
                    "edges": int(
                        self._connection.execute(
                            "SELECT COUNT(*) FROM memory_edges"
                        ).fetchone()[0]
                    ),
                    "branches": int(
                        self._connection.execute(
                            "SELECT COUNT(*) FROM branches"
                        ).fetchone()[0]
                    ),
                    "vectors": int(
                        self._connection.execute(
                            "SELECT COUNT(*) FROM memory_vectors"
                        ).fetchone()[0]
                    ),
                    "lifecycle_events": int(
                        self._connection.execute(
                            "SELECT COUNT(*) FROM memory_lifecycle_events"
                        ).fetchone()[0]
                    ),
                    "governance_decisions": int(
                        self._connection.execute(
                            "SELECT COUNT(*) FROM governance_decisions"
                        ).fetchone()[0]
                    ),
                }
            except sqlite3.DatabaseError as exc:
                raise RuntimeError("SQLiteStore integrity check could not complete") from exc

    def backup_to(self, destination: str | Path, *, overwrite: bool = False) -> Path:
        """Create an online, transactionally consistent, integrity-checked backup."""
        destination_path = Path(destination).expanduser().resolve()
        if self._path != ":memory:" and destination_path == Path(self._path).expanduser().resolve():
            raise ValueError("backup destination must differ from the live database")
        with self._lock:
            self._ensure_open()
            if self._transaction_depth:
                raise RuntimeError("cannot back up SQLiteStore during a transaction")
            self.verify_integrity()
            _backup_connection_to_path(
                self._connection,
                destination_path,
                overwrite=overwrite,
            )
        return destination_path

    @classmethod
    def restore_from(
        cls,
        backup: str | Path,
        destination: str | Path,
        *,
        overwrite: bool = False,
        embedder: TextEmbedder | None = None,
    ) -> SQLiteStore:
        """Verify a backup, atomically restore it, then open the recovered store."""
        backup_path = Path(backup).expanduser().resolve()
        destination_path = Path(destination).expanduser().resolve()
        if backup_path == destination_path:
            raise ValueError("backup and restore destination must differ")
        try:
            source = sqlite3.connect(
                f"file:{backup_path.as_posix()}?mode=ro",
                uri=True,
            )
        except sqlite3.DatabaseError as exc:
            raise RuntimeError("backup could not be opened read-only") from exc
        try:
            rows = source.execute("PRAGMA integrity_check").fetchall()
            messages = tuple(str(row[0]) for row in rows)
            if messages != ("ok",):
                raise RuntimeError(
                    f"backup integrity check failed: {'; '.join(messages)}"
                )
            row = source.execute(
                "SELECT value FROM store_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None or not 1 <= int(row[0]) <= SCHEMA_VERSION:
                raise RuntimeError("backup schema version is missing or unsupported")
            _backup_connection_to_path(source, destination_path, overwrite=overwrite)
        except sqlite3.DatabaseError as exc:
            raise RuntimeError("backup is not a valid SQLiteStore database") from exc
        finally:
            source.close()
        return cls(destination_path, embedder=embedder)

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def upsert_atom(self, atom: MemoryAtom) -> None:
        payload = _serialize_atom(atom)
        vector = (
            _validated_vector(
                self._embedder.embed(f"{atom.claim} {' '.join(atom.tags)}")
            )
            if self._embedder is not None
            else None
        )
        with self._lock:
            self._ensure_open()
            owns_transaction = vector is not None and self._transaction_depth == 0
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """
                    INSERT INTO memory_atoms (id, branch_id, created_at, payload)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        branch_id = excluded.branch_id,
                        created_at = excluded.created_at,
                        payload = excluded.payload
                    """,
                    (atom.id, atom.branch_id, atom.created_at.isoformat(), payload),
                )
                if vector is not None:
                    self._connection.execute(
                        """
                        INSERT INTO memory_vectors (atom_id, dimensions, vector_json)
                        VALUES (?, ?, ?)
                        ON CONFLICT(atom_id) DO UPDATE SET
                            dimensions = excluded.dimensions,
                            vector_json = excluded.vector_json
                        """,
                        (atom.id, len(vector), json.dumps(vector, separators=(",", ":"))),
                    )
            except BaseException:
                if owns_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            else:
                if owns_transaction:
                    self._connection.execute("COMMIT")

    def search(self, *, query: str, top_k: int) -> list[VectorMatch]:
        """Search persisted vectors by cosine similarity."""
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self._embedder is None:
            return []
        query_vector = _validated_vector(self._embedder.embed(query))
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT vectors.atom_id, vectors.dimensions, vectors.vector_json
                FROM memory_vectors AS vectors
                LEFT JOIN memory_lifecycle_current AS lifecycle
                    ON lifecycle.atom_id = vectors.atom_id
                WHERE lifecycle.state IS NULL OR lifecycle.state = 'active'
                ORDER BY vectors.atom_id
                """
            ).fetchall()
        matches: list[VectorMatch] = []
        for row in rows:
            if int(row["dimensions"]) != len(query_vector):
                continue
            stored = tuple(float(value) for value in json.loads(row["vector_json"]))
            score = _cosine_similarity(query_vector, stored)
            if score > 0.0:
                matches.append(VectorMatch(atom_id=row["atom_id"], score=score))
        return sorted(matches, key=lambda item: (-item.score, item.atom_id))[:top_k]

    def get_atom(self, atom_id: str) -> MemoryAtom | None:
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT payload FROM memory_atoms WHERE id = ?",
                (atom_id,),
            ).fetchone()
        return _deserialize_atom(row["payload"]) if row is not None else None

    def delete_atom(self, atom_id: str) -> None:
        with self._lock:
            self._ensure_open()
            self._connection.execute("DELETE FROM memory_atoms WHERE id = ?", (atom_id,))

    def list_atoms(
        self,
        branch_id: str | None = None,
        *,
        include_inherited: bool = False,
    ) -> list[MemoryAtom]:
        with self._lock:
            self._ensure_open()
            if branch_id is None:
                rows = self._connection.execute(
                    "SELECT payload FROM memory_atoms ORDER BY rowid"
                ).fetchall()
            elif not include_inherited:
                rows = self._connection.execute(
                    "SELECT payload FROM memory_atoms WHERE branch_id = ? ORDER BY rowid",
                    (branch_id,),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT payload FROM memory_atoms ORDER BY rowid"
                ).fetchall()
        atoms = [_deserialize_atom(row["payload"]) for row in rows]
        if branch_id is None or not include_inherited:
            return atoms
        lineage = self.resolve_branch_lineage(branch_id)
        lineage_index = {current: index for index, current in enumerate(lineage)}
        inherited = [atom for atom in atoms if atom.branch_id in lineage_index]
        return sorted(
            inherited,
            key=lambda atom: (
                lineage_index[atom.branch_id],
                -atom.created_at.timestamp(),
                atom.id,
            ),
        )

    def add_edge(self, edge: MemoryEdge) -> None:
        with self._lock:
            self._ensure_open()
            placeholders = self._connection.execute(
                "SELECT id FROM memory_atoms WHERE id IN (?, ?)",
                (edge.source_id, edge.target_id),
            ).fetchall()
            if len({row["id"] for row in placeholders}) != len(
                {edge.source_id, edge.target_id}
            ):
                raise KeyError("Both source and target atoms must exist before adding an edge")
            self._connection.execute(
                """
                INSERT INTO memory_edges (source_id, target_id, edge_type, weight)
                VALUES (?, ?, ?, ?)
                """,
                (edge.source_id, edge.target_id, edge.edge_type.value, edge.weight),
            )

    def list_edges(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        edge_type: EdgeType | None = None,
    ) -> list[MemoryEdge]:
        clauses: list[str] = []
        values: list[object] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            values.append(source_id)
        if target_id is not None:
            clauses.append("target_id = ?")
            values.append(target_id)
        if edge_type is not None:
            clauses.append("edge_type = ?")
            values.append(edge_type.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                "SELECT source_id, target_id, edge_type, weight "
                f"FROM memory_edges{where} ORDER BY id",
                values,
            ).fetchall()
        return [
            MemoryEdge(
                source_id=row["source_id"],
                target_id=row["target_id"],
                edge_type=EdgeType(row["edge_type"]),
                weight=float(row["weight"]),
            )
            for row in rows
        ]

    def neighboring_atom_ids(
        self,
        seed_ids: Iterable[str],
        *,
        max_hops: int = 1,
        edge_types: set[EdgeType] | None = None,
    ) -> set[str]:
        if max_hops <= 0:
            return set()
        edges = self.list_edges()
        outgoing: dict[str, list[MemoryEdge]] = defaultdict(list)
        incoming: dict[str, list[MemoryEdge]] = defaultdict(list)
        for edge in edges:
            outgoing[edge.source_id].append(edge)
            incoming[edge.target_id].append(edge)

        seed_set = set(seed_ids)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque((seed_id, 0) for seed_id in seed_set)
        while queue:
            current_id, hops = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            if hops >= max_hops:
                continue
            for edge in outgoing[current_id] + incoming[current_id]:
                if edge_types is not None and edge.edge_type not in edge_types:
                    continue
                neighbor = edge.target_id if edge.source_id == current_id else edge.source_id
                if neighbor not in visited:
                    queue.append((neighbor, hops + 1))
        return visited - seed_set

    def upsert_branch(self, branch: Branch) -> None:
        payload = _serialize_branch(branch)
        with self._lock:
            self._ensure_open()
            self._connection.execute(
                """
                INSERT INTO branches (id, parent_id, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    parent_id = excluded.parent_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (
                    branch.id,
                    branch.parent_id,
                    branch.status.value,
                    branch.created_at.isoformat(),
                    payload,
                ),
            )

    def get_branch(self, branch_id: str) -> Branch | None:
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT payload FROM branches WHERE id = ?",
                (branch_id,),
            ).fetchone()
        return _deserialize_branch(row["payload"]) if row is not None else None

    def resolve_branch_lineage(self, branch_id: str) -> tuple[str, ...]:
        if not branch_id.strip():
            raise ValueError("branch_id cannot be empty")
        lineage: list[str] = []
        current_id: str | None = branch_id
        visited: set[str] = set()
        while current_id is not None and current_id not in visited:
            lineage.append(current_id)
            visited.add(current_id)
            branch = self.get_branch(current_id)
            current_id = branch.parent_id if branch is not None else None
        if branch_id != "main" and self.get_branch("main") is not None and "main" not in visited:
            lineage.append("main")
        return tuple(lineage)

    def list_branches(self, status: BranchStatus | None = None) -> list[Branch]:
        with self._lock:
            self._ensure_open()
            if status is None:
                rows = self._connection.execute(
                    "SELECT payload FROM branches ORDER BY rowid"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT payload FROM branches WHERE status = ? ORDER BY rowid",
                    (status.value,),
                ).fetchall()
        return [_deserialize_branch(row["payload"]) for row in rows]

    def set_lifecycle(self, record: MemoryLifecycleRecord) -> None:
        with self._lock:
            self._ensure_open()
            if self.get_atom(record.atom_id) is None:
                raise KeyError(f"Unknown memory atom id: {record.atom_id}")
            row = self._connection.execute(
                "SELECT version FROM memory_lifecycle_current WHERE atom_id = ?",
                (record.atom_id,),
            ).fetchone()
            expected_version = 1 if row is None else int(row["version"]) + 1
            if record.version != expected_version:
                raise ValueError(
                    f"lifecycle version for {record.atom_id} must be {expected_version}"
                )
            owns_transaction = self._transaction_depth == 0
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            values = (
                record.atom_id,
                record.state.value,
                record.reason_code,
                record.actor,
                record.changed_at.isoformat(),
                record.version,
            )
            try:
                self._connection.execute(
                    """
                    INSERT INTO memory_lifecycle_events
                        (atom_id, state, reason_code, actor, changed_at, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                self._connection.execute(
                    """
                    INSERT INTO memory_lifecycle_current
                        (atom_id, state, reason_code, actor, changed_at, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(atom_id) DO UPDATE SET
                        state = excluded.state,
                        reason_code = excluded.reason_code,
                        actor = excluded.actor,
                        changed_at = excluded.changed_at,
                        version = excluded.version
                    """,
                    values,
                )
            except BaseException:
                if owns_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            else:
                if owns_transaction:
                    self._connection.execute("COMMIT")

    def get_lifecycle(self, atom_id: str) -> MemoryLifecycleRecord | None:
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                """
                SELECT atom_id, state, reason_code, actor, changed_at, version
                FROM memory_lifecycle_current WHERE atom_id = ?
                """,
                (atom_id,),
            ).fetchone()
        return _deserialize_lifecycle(row) if row is not None else None

    def list_lifecycle_events(
        self,
        atom_id: str | None = None,
    ) -> list[MemoryLifecycleRecord]:
        with self._lock:
            self._ensure_open()
            if atom_id is None:
                rows = self._connection.execute(
                    """
                    SELECT atom_id, state, reason_code, actor, changed_at, version
                    FROM memory_lifecycle_events ORDER BY id
                    """
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT atom_id, state, reason_code, actor, changed_at, version
                    FROM memory_lifecycle_events WHERE atom_id = ? ORDER BY version
                    """,
                    (atom_id,),
                ).fetchall()
        return [_deserialize_lifecycle(row) for row in rows]

    def record_governance_decisions(
        self,
        decisions: Iterable[GovernanceDecision],
    ) -> None:
        batch = tuple(decisions)
        keys = [(item.request_id, item.atom_id) for item in batch]
        if len(keys) != len(set(keys)):
            raise ValueError("governance audit batch contains duplicate request/atom keys")
        if not batch:
            return
        rows = [
            (
                item.request_id,
                item.atom_id,
                int(item.allowed),
                item.reason_code,
                item.policy_id,
                item.policy_version,
                item.role,
                item.purpose,
                item.decided_at.isoformat(),
            )
            for item in batch
        ]
        with self._lock:
            self._ensure_open()
            owns_transaction = self._transaction_depth == 0
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.executemany(
                    """
                    INSERT INTO governance_decisions
                        (request_id, atom_id, allowed, reason_code, policy_id,
                         policy_version, role, purpose, decided_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            except sqlite3.IntegrityError as exc:
                if owns_transaction:
                    self._connection.execute("ROLLBACK")
                raise ValueError("governance decisions are immutable and unique") from exc
            except BaseException:
                if owns_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            else:
                if owns_transaction:
                    self._connection.execute("COMMIT")

    def list_governance_decisions(
        self,
        request_id: str | None = None,
    ) -> list[GovernanceDecision]:
        with self._lock:
            self._ensure_open()
            if request_id is None:
                rows = self._connection.execute(
                    "SELECT * FROM governance_decisions ORDER BY id"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM governance_decisions
                    WHERE request_id = ? ORDER BY id
                    """,
                    (request_id,),
                ).fetchall()
        return [_deserialize_governance_decision(row) for row in rows]

    def _initialize_schema(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            row = self._connection.execute(
                "SELECT value FROM store_metadata WHERE key = 'schema_version'"
            ).fetchone()
            version = int(row["value"]) if row is not None else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported SQLiteStore schema version {version}; "
                    f"expected at most {SCHEMA_VERSION}"
                )
            if version == 0:
                self._migrate_0_to_1()
                version = 1
            if version == 1:
                self._migrate_1_to_2()
                version = 2
            if version == 2:
                self._migrate_2_to_3()
                version = 3
            if version == 3:
                self._migrate_3_to_4()
                version = 4
            if version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"failed to migrate SQLiteStore schema to {SCHEMA_VERSION}"
                )

    def _migrate_0_to_1(self) -> None:
        self._connection.executescript(
            """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS memory_atoms (
                    id TEXT PRIMARY KEY,
                    branch_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_atoms_branch_created
                    ON memory_atoms(branch_id, created_at);
                CREATE TABLE IF NOT EXISTS memory_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES memory_atoms(id) ON DELETE CASCADE,
                    target_id TEXT NOT NULL REFERENCES memory_atoms(id) ON DELETE CASCADE,
                    edge_type TEXT NOT NULL,
                    weight REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_edges_type ON memory_edges(edge_type);
                CREATE TABLE IF NOT EXISTS branches (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_branches_status ON branches(status);
                INSERT INTO store_metadata (key, value)
                    VALUES ('schema_version', '1')
                    ON CONFLICT(key) DO UPDATE SET value = '1';
                COMMIT;
            """
        )

    def _migrate_1_to_2(self) -> None:
        self._connection.executescript(
            """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    atom_id TEXT PRIMARY KEY
                        REFERENCES memory_atoms(id) ON DELETE CASCADE,
                    dimensions INTEGER NOT NULL,
                    vector_json TEXT NOT NULL
                );
                UPDATE store_metadata SET value = '2' WHERE key = 'schema_version';
                COMMIT;
            """
        )

    def _migrate_2_to_3(self) -> None:
        self._connection.executescript(
            """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS memory_lifecycle_current (
                    atom_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    atom_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    UNIQUE(atom_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_lifecycle_events_atom
                    ON memory_lifecycle_events(atom_id, version);
                UPDATE store_metadata SET value = '3' WHERE key = 'schema_version';
                COMMIT;
            """
        )

    def _migrate_3_to_4(self) -> None:
        self._connection.executescript(
            """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS governance_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    atom_id TEXT NOT NULL,
                    allowed INTEGER NOT NULL CHECK(allowed IN (0, 1)),
                    reason_code TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    policy_version INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    UNIQUE(request_id, atom_id)
                );
                CREATE INDEX IF NOT EXISTS idx_governance_request
                    ON governance_decisions(request_id, id);
                UPDATE store_metadata SET value = '4' WHERE key = 'schema_version';
                COMMIT;
            """
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLiteStore is closed")


def _serialize_atom(atom: MemoryAtom) -> str:
    payload = {
        "id": atom.id,
        "claim": atom.claim,
        "evidence": [
            {
                "ref": item.ref,
                "source": item.source,
                "captured_at": item.captured_at.isoformat(),
                "note": item.note,
            }
            for item in atom.evidence
        ],
        "source_agent": atom.source_agent,
        "confidence": atom.confidence,
        "scope": {
            "domain": atom.scope.domain,
            "task": atom.scope.task,
            "owner": atom.scope.owner,
        },
        "created_at": atom.created_at.isoformat(),
        "ttl_seconds": atom.ttl.total_seconds(),
        "branch_id": atom.branch_id,
        "sensitivity": atom.sensitivity.value,
        "tags": list(atom.tags),
        "metadata": dict(atom.metadata),
    }
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TypeError(f"MemoryAtom {atom.id!r} contains non-JSON metadata") from exc


def _deserialize_atom(payload: str) -> MemoryAtom:
    raw: dict[str, Any] = json.loads(payload)
    return MemoryAtom(
        id=raw["id"],
        claim=raw["claim"],
        evidence=tuple(
            Evidence(
                ref=item["ref"],
                source=item["source"],
                captured_at=datetime.fromisoformat(item["captured_at"]),
                note=item.get("note"),
            )
            for item in raw["evidence"]
        ),
        source_agent=raw["source_agent"],
        confidence=float(raw["confidence"]),
        scope=MemoryScope(**raw["scope"]),
        created_at=datetime.fromisoformat(raw["created_at"]),
        ttl=timedelta(seconds=float(raw["ttl_seconds"])),
        branch_id=raw["branch_id"],
        sensitivity=Sensitivity(raw["sensitivity"]),
        tags=tuple(raw.get("tags", ())),
        metadata=raw.get("metadata", {}),
    )


def _serialize_branch(branch: Branch) -> str:
    return json.dumps(
        {
            "id": branch.id,
            "name": branch.name,
            "hypothesis": branch.hypothesis,
            "created_at": branch.created_at.isoformat(),
            "parent_id": branch.parent_id,
            "status": branch.status.value,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _deserialize_branch(payload: str) -> Branch:
    raw = json.loads(payload)
    return Branch(
        id=raw["id"],
        name=raw["name"],
        hypothesis=raw["hypothesis"],
        created_at=datetime.fromisoformat(raw["created_at"]),
        parent_id=raw.get("parent_id"),
        status=BranchStatus(raw["status"]),
    )


def _deserialize_lifecycle(row: sqlite3.Row) -> MemoryLifecycleRecord:
    return MemoryLifecycleRecord(
        atom_id=row["atom_id"],
        state=MemoryLifecycleState(row["state"]),
        reason_code=row["reason_code"],
        actor=row["actor"],
        changed_at=datetime.fromisoformat(row["changed_at"]),
        version=int(row["version"]),
    )


def _deserialize_governance_decision(row: sqlite3.Row) -> GovernanceDecision:
    return GovernanceDecision(
        request_id=row["request_id"],
        atom_id=row["atom_id"],
        allowed=bool(row["allowed"]),
        reason_code=row["reason_code"],
        policy_id=row["policy_id"],
        policy_version=int(row["policy_version"]),
        role=row["role"],
        purpose=row["purpose"],
        decided_at=datetime.fromisoformat(row["decided_at"]),
    )


def _validated_vector(values: Iterable[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector:
        raise ValueError("embedder returned an empty vector")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("embedder returned a non-finite vector")
    return vector


def _cosine_similarity(lhs: tuple[float, ...], rhs: tuple[float, ...]) -> float:
    lhs_norm = math.sqrt(sum(value * value for value in lhs))
    rhs_norm = math.sqrt(sum(value * value for value in rhs))
    if lhs_norm == 0.0 or rhs_norm == 0.0:
        return 0.0
    dot = sum(left * right for left, right in zip(lhs, rhs, strict=True))
    return max(-1.0, min(1.0, dot / (lhs_norm * rhs_norm)))


def _backup_connection_to_path(
    source: sqlite3.Connection,
    destination: Path,
    *,
    overwrite: bool,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"backup destination already exists: {destination}")
    sidecars = [
        Path(f"{destination}-wal"),
        Path(f"{destination}-shm"),
    ]
    if any(path.exists() for path in sidecars):
        raise RuntimeError("refusing to replace a database with live WAL sidecars")

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    target: sqlite3.Connection | None = None
    try:
        target = sqlite3.connect(temporary)
        source.backup(target)
        rows = target.execute("PRAGMA integrity_check").fetchall()
        messages = tuple(str(row[0]) for row in rows)
        if messages != ("ok",):
            raise RuntimeError(
                f"generated backup integrity check failed: {'; '.join(messages)}"
            )
        target.close()
        target = None
        file_descriptor = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        if target is not None:
            target.close()
        temporary.unlink(missing_ok=True)
        raise
