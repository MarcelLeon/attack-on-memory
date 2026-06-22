"""Executable storage and semantic-model qualification for target environments."""

from __future__ import annotations

import hashlib
import math
import platform
import sqlite3
import statistics
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from attack_on_memory.application.vector_adapter import TextEmbedder
from attack_on_memory.domain.models import Evidence, MemoryAtom, MemoryScope
from attack_on_memory.infrastructure.sqlite_store import SQLiteStore


QUALIFICATION_SCHEMA_VERSION = 1
REPORT_FIELDS = {
    "schema_version",
    "generated_at",
    "profile_id",
    "environment",
    "claim_scope",
    "production_claim_eligible",
    "checks_passed",
    "runtime",
    "workload",
    "thresholds",
    "storage",
    "semantic_embedding",
    "backup_retention_evidence",
}


@dataclass(frozen=True)
class QualificationThresholds:
    min_write_ops_per_second: float = 100.0
    max_write_p95_ms: float = 100.0
    min_read_ops_per_second: float = 1_000.0
    max_read_p95_ms: float = 20.0
    max_backup_restore_seconds: float = 30.0
    min_semantic_margin: float = 0.10
    max_embedding_p95_ms: float = 1_000.0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value < 0 or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite non-negative number")


@dataclass(frozen=True)
class SemanticProbe:
    anchor: str
    paraphrase: str
    unrelated: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.anchor, self.paraphrase, self.unrelated)):
            raise ValueError("semantic probe texts cannot be empty")


def qualify_runtime(
    workspace: str | Path,
    *,
    profile_id: str,
    environment: str,
    sample_count: int = 200,
    writer_count: int = 4,
    thresholds: QualificationThresholds | None = None,
    embedder: TextEmbedder | None = None,
    semantic_probes: Sequence[SemanticProbe] = (),
    backup_retention_evidence: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run a destructive qualification workload in an isolated directory.

    A production claim is eligible only when the caller labels the target as
    production, all measured checks pass, a semantic provider is exercised, and
    independently verifiable backup-retention evidence is attached.
    """
    if not profile_id.strip():
        raise ValueError("profile_id cannot be empty")
    if environment not in {"development", "staging", "production"}:
        raise ValueError("environment must be development, staging, or production")
    if sample_count < 1:
        raise ValueError("sample_count must be >= 1")
    if writer_count < 1 or writer_count > sample_count:
        raise ValueError("writer_count must be between 1 and sample_count")
    if (embedder is None) != (len(semantic_probes) == 0):
        raise ValueError("embedder and semantic_probes must be supplied together")
    retention = _validate_retention_evidence(backup_retention_evidence)
    thresholds = thresholds or QualificationThresholds()
    generated_at = now or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    database = root / "qualification-live.db"
    backup = root / "qualification-backup.db"
    restored = root / "qualification-restored.db"
    for path in (database, backup, restored):
        if path.exists():
            raise FileExistsError(f"qualification artifact already exists: {path.name}")

    storage = _qualify_storage(
        database,
        backup,
        restored,
        sample_count=sample_count,
        writer_count=writer_count,
        thresholds=thresholds,
        now=generated_at,
    )
    semantic = _qualify_semantic_model(embedder, semantic_probes, thresholds)
    checks_passed = storage["status"] == "pass" and semantic["status"] in {
        "pass",
        "not_run",
    }
    production_claim_eligible = (
        environment == "production"
        and storage["status"] == "pass"
        and semantic["status"] == "pass"
        and retention is not None
    )
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "profile_id": profile_id,
        "environment": environment,
        "claim_scope": (
            "production-eligible" if production_claim_eligible else "non-production-evidence"
        ),
        "production_claim_eligible": production_claim_eligible,
        "checks_passed": checks_passed,
        "runtime": _runtime_identity(),
        "workload": {
            "sample_count": sample_count,
            "writer_count": writer_count,
        },
        "thresholds": asdict(thresholds),
        "storage": storage,
        "semantic_embedding": semantic,
        "backup_retention_evidence": retention,
    }


def validate_runtime_qualification_report(report: object) -> None:
    """Reject malformed reports and conclusions inconsistent with their checks."""
    if not isinstance(report, Mapping) or set(report) != REPORT_FIELDS:
        raise ValueError("runtime qualification report fields are invalid")
    if (
        not isinstance(report["schema_version"], int)
        or isinstance(report["schema_version"], bool)
        or report["schema_version"] != QUALIFICATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported runtime qualification schema version")
    if report["environment"] not in {"development", "staging", "production"}:
        raise ValueError("runtime qualification environment is invalid")
    if not isinstance(report["profile_id"], str) or not report["profile_id"].strip():
        raise ValueError("runtime qualification profile_id is invalid")
    generated_at = datetime.fromisoformat(str(report["generated_at"]))
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("runtime qualification generated_at must be timezone-aware")
    storage = report["storage"]
    semantic = report["semantic_embedding"]
    workload = report["workload"]
    threshold_values = report["thresholds"]
    if (
        not isinstance(storage, Mapping)
        or not isinstance(semantic, Mapping)
        or not isinstance(workload, Mapping)
        or not isinstance(threshold_values, Mapping)
    ):
        raise ValueError("runtime qualification result sections are invalid")
    if set(workload) != {"sample_count", "writer_count"}:
        raise ValueError("runtime qualification workload is invalid")
    for field in ("sample_count", "writer_count"):
        if (
            not isinstance(workload[field], int)
            or isinstance(workload[field], bool)
            or workload[field] < 1
        ):
            raise ValueError("runtime qualification workload is invalid")
    expected_threshold_fields = set(asdict(QualificationThresholds()))
    if set(threshold_values) != expected_threshold_fields:
        raise ValueError("runtime qualification thresholds are invalid")
    for value in threshold_values.values():
        _validate_non_negative_finite(value, "threshold")
    metrics = storage.get("metrics")
    live_integrity = storage.get("live_integrity")
    restored_integrity = storage.get("restored_integrity")
    if not all(
        isinstance(section, Mapping)
        for section in (metrics, live_integrity, restored_integrity)
    ):
        raise ValueError("runtime qualification storage measurements are invalid")
    checks = storage.get("checks")
    failures = storage.get("failures")
    if not isinstance(checks, list) or not checks or not isinstance(failures, list):
        raise ValueError("runtime qualification storage checks are invalid")
    expected_checks = {
        "all_writes_committed": (metrics.get("committed_writes"), "==", workload["sample_count"]),
        "write_rate": (
            metrics.get("write_ops_per_second"),
            ">=",
            threshold_values["min_write_ops_per_second"],
        ),
        "write_p95": (
            metrics.get("write_p95_ms"),
            "<=",
            threshold_values["max_write_p95_ms"],
        ),
        "read_rate": (
            metrics.get("read_ops_per_second"),
            ">=",
            threshold_values["min_read_ops_per_second"],
        ),
        "read_p95": (
            metrics.get("read_p95_ms"),
            "<=",
            threshold_values["max_read_p95_ms"],
        ),
        "backup_restore_time": (
            metrics.get("backup_restore_seconds"),
            "<=",
            threshold_values["max_backup_restore_seconds"],
        ),
        "live_integrity_count": (
            live_integrity.get("atoms"),
            "==",
            workload["sample_count"],
        ),
        "restored_integrity_count": (
            restored_integrity.get("atoms"),
            "==",
            workload["sample_count"],
        ),
    }
    for check in checks:
        _validate_report_check(check)
    if {check["name"] for check in checks} != set(expected_checks) or len(checks) != len(
        expected_checks
    ):
        raise ValueError("runtime qualification check set is invalid")
    for check in checks:
        observed, operator, threshold = expected_checks[check["name"]]
        _validate_non_negative_finite(observed, "storage measurement")
        if (
            check["observed"] != observed
            or check["operator"] != operator
            or check["threshold"] != threshold
        ):
            raise ValueError("runtime qualification check is not bound to measurements")
    storage_passed = not failures and all(check["passed"] for check in checks)
    if storage.get("status") != ("pass" if storage_passed else "fail"):
        raise ValueError("runtime qualification storage status is inconsistent")
    semantic_status = semantic.get("status")
    if semantic_status not in {"pass", "fail", "not_run"}:
        raise ValueError("runtime qualification semantic status is invalid")
    if semantic_status == "pass" and "checks" not in semantic:
        raise ValueError("passing semantic qualification requires checks")
    if semantic_status in {"pass", "fail"} and "checks" in semantic:
        dimensions = semantic.get("dimensions")
        if (
            not isinstance(dimensions, list)
            or not dimensions
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
                for value in dimensions
            )
        ):
            raise ValueError("runtime qualification semantic dimensions are invalid")
        _validate_finite(semantic.get("minimum_margin"), "semantic margin")
        _validate_non_negative_finite(
            semantic.get("embedding_p95_ms"), "embedding latency"
        )
        semantic_checks = semantic["checks"]
        if not isinstance(semantic_checks, list) or not semantic_checks:
            raise ValueError("runtime qualification semantic checks are invalid")
        for check in semantic_checks:
            _validate_report_check(check)
        expected_semantic_checks = {
            "dimension_consistency": (len(dimensions), "==", 1),
            "minimum_semantic_margin": (
                semantic.get("minimum_margin"),
                ">=",
                threshold_values["min_semantic_margin"],
            ),
            "embedding_p95": (
                semantic.get("embedding_p95_ms"),
                "<=",
                threshold_values["max_embedding_p95_ms"],
            ),
        }
        if {check["name"] for check in semantic_checks} != set(
            expected_semantic_checks
        ) or len(semantic_checks) != len(expected_semantic_checks):
            raise ValueError("runtime qualification semantic check set is invalid")
        for check in semantic_checks:
            observed, operator, threshold = expected_semantic_checks[check["name"]]
            if (
                check["observed"] != observed
                or check["operator"] != operator
                or check["threshold"] != threshold
            ):
                raise ValueError("runtime qualification semantic check is not bound")
        semantic_checks_passed = all(
            isinstance(check, Mapping) and check.get("passed") is True
            for check in semantic_checks
        )
        if (semantic_status == "pass") != semantic_checks_passed:
            raise ValueError("runtime qualification semantic status is inconsistent")
    checks_passed = storage_passed and semantic_status in {"pass", "not_run"}
    if report["checks_passed"] is not checks_passed:
        raise ValueError("runtime qualification overall check status is inconsistent")
    retention = _validate_retention_evidence(report["backup_retention_evidence"])
    eligible = (
        report["environment"] == "production"
        and storage_passed
        and semantic_status == "pass"
        and retention is not None
    )
    if report["production_claim_eligible"] is not eligible:
        raise ValueError("runtime qualification production conclusion is inconsistent")
    expected_scope = "production-eligible" if eligible else "non-production-evidence"
    if report["claim_scope"] != expected_scope:
        raise ValueError("runtime qualification claim scope is inconsistent")
    digest = storage.get("backup_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise ValueError("runtime qualification backup digest is invalid")


def _qualify_storage(
    database: Path,
    backup: Path,
    restored: Path,
    *,
    sample_count: int,
    writer_count: int,
    thresholds: QualificationThresholds,
    now: datetime,
) -> dict[str, Any]:
    with SQLiteStore(database):
        pass
    ids = [f"qualification-{index:08d}" for index in range(sample_count)]
    batches = [ids[index::writer_count] for index in range(writer_count)]
    write_latencies: list[float] = []
    failures: list[str] = []
    guard = threading.Lock()
    start = threading.Barrier(writer_count + 1)

    def writer(batch: Sequence[str]) -> None:
        try:
            with SQLiteStore(database) as store:
                start.wait(timeout=10)
                for atom_id in batch:
                    began = time.perf_counter_ns()
                    store.upsert_atom(_qualification_atom(atom_id, now))
                    elapsed = _elapsed_ms(began)
                    with guard:
                        write_latencies.append(elapsed)
        except BaseException as exc:  # surfaced in the report and failed checks
            start.abort()
            with guard:
                failures.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=writer, args=(batch,)) for batch in batches]
    for thread in threads:
        thread.start()
    began_writes = time.perf_counter_ns()
    try:
        start.wait(timeout=10)
    except threading.BrokenBarrierError:
        failures.append("writer start barrier failed")
    for thread in threads:
        thread.join()
    write_seconds = _elapsed_seconds(began_writes)

    read_latencies: list[float] = []
    began_reads = time.perf_counter_ns()
    with SQLiteStore(database) as store:
        for atom_id in ids:
            began = time.perf_counter_ns()
            atom = store.get_atom(atom_id)
            read_latencies.append(_elapsed_ms(began))
            if atom is None:
                failures.append(f"missing atom after committed write: {atom_id}")
        read_seconds = _elapsed_seconds(began_reads)
        live_integrity = store.verify_integrity()
        began_recovery = time.perf_counter_ns()
        store.backup_to(backup)
    with SQLiteStore.restore_from(backup, restored) as recovered:
        restored_integrity = recovered.verify_integrity()
    recovery_seconds = _elapsed_seconds(began_recovery)

    write_rate = len(write_latencies) / write_seconds if write_seconds else 0.0
    read_rate = len(read_latencies) / read_seconds if read_seconds else 0.0
    metrics = {
        "committed_writes": len(write_latencies),
        "write_ops_per_second": write_rate,
        "write_p50_ms": _percentile(write_latencies, 50),
        "write_p95_ms": _percentile(write_latencies, 95),
        "reads": len(read_latencies),
        "read_ops_per_second": read_rate,
        "read_p50_ms": _percentile(read_latencies, 50),
        "read_p95_ms": _percentile(read_latencies, 95),
        "backup_restore_seconds": recovery_seconds,
    }
    checks = [
        _check("all_writes_committed", len(write_latencies), "==", sample_count),
        _check("write_rate", write_rate, ">=", thresholds.min_write_ops_per_second),
        _check("write_p95", metrics["write_p95_ms"], "<=", thresholds.max_write_p95_ms),
        _check("read_rate", read_rate, ">=", thresholds.min_read_ops_per_second),
        _check("read_p95", metrics["read_p95_ms"], "<=", thresholds.max_read_p95_ms),
        _check(
            "backup_restore_time",
            recovery_seconds,
            "<=",
            thresholds.max_backup_restore_seconds,
        ),
        _check("live_integrity_count", live_integrity["atoms"], "==", sample_count),
        _check("restored_integrity_count", restored_integrity["atoms"], "==", sample_count),
    ]
    passed = not failures and all(check["passed"] for check in checks)
    return {
        "status": "pass" if passed else "fail",
        "metrics": metrics,
        "checks": checks,
        "failures": failures,
        "live_integrity": live_integrity,
        "restored_integrity": restored_integrity,
        "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
    }


def _qualify_semantic_model(
    embedder: TextEmbedder | None,
    probes: Sequence[SemanticProbe],
    thresholds: QualificationThresholds,
) -> dict[str, Any]:
    if embedder is None:
        return {
            "status": "not_run",
            "reason": "No semantic provider and probe set were supplied.",
        }
    identity = getattr(embedder, "identity", None)
    if not isinstance(identity, Mapping):
        return {
            "status": "fail",
            "reason": "Semantic provider must expose a non-secret identity mapping.",
        }
    latencies: list[float] = []
    margins: list[float] = []
    dimensions: set[int] = set()
    try:
        for probe in probes:
            vectors: list[Sequence[float]] = []
            for text in (probe.anchor, probe.paraphrase, probe.unrelated):
                began = time.perf_counter_ns()
                vector = tuple(float(value) for value in embedder.embed(text))
                latencies.append(_elapsed_ms(began))
                vectors.append(vector)
                dimensions.add(len(vector))
            positive = _cosine(vectors[0], vectors[1])
            negative = _cosine(vectors[0], vectors[2])
            margins.append(positive - negative)
    except BaseException as exc:
        # Provider errors are evidence too. Avoid exception text because a custom
        # adapter could include the sensitive probe input or credentials in it.
        return {
            "status": "fail",
            "provider": dict(identity),
            "probe_count": len(probes),
            "error_type": type(exc).__name__,
            "reason": "Semantic provider or response validation failed.",
        }
    minimum_margin = min(margins)
    p95 = _percentile(latencies, 95)
    checks = [
        _check("dimension_consistency", len(dimensions), "==", 1),
        _check("minimum_semantic_margin", minimum_margin, ">=", thresholds.min_semantic_margin),
        _check("embedding_p95", p95, "<=", thresholds.max_embedding_p95_ms),
    ]
    return {
        "status": "pass" if all(check["passed"] for check in checks) else "fail",
        "provider": dict(identity),
        "probe_count": len(probes),
        "dimensions": sorted(dimensions),
        "minimum_margin": minimum_margin,
        "median_margin": statistics.median(margins),
        "embedding_p95_ms": p95,
        "checks": checks,
    }


def _qualification_atom(atom_id: str, now: datetime) -> MemoryAtom:
    return MemoryAtom(
        id=atom_id,
        claim=f"Qualification recovery fact {atom_id}",
        evidence=(
            Evidence(
                ref=f"qualification:{atom_id}",
                source="runtime-qualification",
                captured_at=now,
            ),
        ),
        source_agent="runtime-qualification",
        confidence=1.0,
        scope=MemoryScope(domain="qualification", task="storage", owner="system"),
        created_at=now,
        ttl=timedelta(days=1),
        tags=("qualification",),
    )


def _validate_retention_evidence(
    value: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if value is None:
        return None
    if set(value) != {"ref", "sha256"}:
        raise ValueError("backup retention evidence must contain only ref and sha256")
    ref = value["ref"]
    digest = value["sha256"]
    if not ref.strip() or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("backup retention evidence ref or sha256 is invalid")
    return {"ref": ref, "sha256": digest}


def _runtime_identity() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "sqlite": sqlite3.sqlite_version,
    }


def _check(name: str, observed: float, operator: str, threshold: float) -> dict[str, Any]:
    passed = _comparison(observed, operator, threshold)
    return {
        "name": name,
        "observed": observed,
        "operator": operator,
        "threshold": threshold,
        "passed": passed,
    }


def _comparison(observed: float, operator: str, threshold: float) -> bool:
    if operator == ">=":
        return observed >= threshold
    if operator == "<=":
        return observed <= threshold
    if operator == "==":
        return observed == threshold
    raise ValueError(f"unsupported check operator: {operator}")


def _validate_report_check(check: object) -> None:
    if (
        not isinstance(check, Mapping)
        or set(check) != {"name", "observed", "operator", "threshold", "passed"}
        or not isinstance(check["name"], str)
        or not check["name"]
        or not isinstance(check["passed"], bool)
        or check["operator"] not in {">=", "<=", "=="}
    ):
        raise ValueError("runtime qualification check is invalid")
    _validate_finite(check["observed"], "check observed")
    _validate_non_negative_finite(check["threshold"], "check threshold")
    expected = _comparison(check["observed"], check["operator"], check["threshold"])
    if check["passed"] != expected:
        raise ValueError("runtime qualification check conclusion is inconsistent")


def _validate_non_negative_finite(value: object, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < 0
        or not math.isfinite(value)
    ):
        raise ValueError(f"runtime qualification {field} is invalid")


def _validate_finite(value: object, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"runtime qualification {field} is invalid")


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("semantic provider returned inconsistent dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("semantic provider returned a zero vector")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return ordered[index]


def _elapsed_ms(began: int) -> float:
    return (time.perf_counter_ns() - began) / 1_000_000


def _elapsed_seconds(began: int) -> float:
    return (time.perf_counter_ns() - began) / 1_000_000_000
