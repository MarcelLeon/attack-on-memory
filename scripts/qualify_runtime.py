#!/usr/bin/env python3
"""Run target-environment storage and semantic embedding qualification."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from attack_on_memory.evals.runtime_qualification import (
    QualificationThresholds,
    SemanticProbe,
    qualify_runtime,
)
from attack_on_memory.infrastructure.http_embedder import HTTPTextEmbedder


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROBES = ROOT / "examples" / "qualification" / "semantic-probes.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument(
        "--environment",
        required=True,
        choices=("development", "staging", "production"),
    )
    parser.add_argument("--sample-count", type=int, default=500)
    parser.add_argument("--writers", type=int, default=4)
    parser.add_argument("--embedding-endpoint")
    parser.add_argument("--embedding-model")
    parser.add_argument("--embedding-dimensions", type=int)
    parser.add_argument("--embedding-key-env", default="AOM_EMBEDDING_API_KEY")
    parser.add_argument("--semantic-probes", type=Path, default=DEFAULT_PROBES)
    parser.add_argument("--backup-retention-ref")
    parser.add_argument("--backup-retention-sha256")
    parser.add_argument("--min-write-ops", type=float, default=100.0)
    parser.add_argument("--max-write-p95-ms", type=float, default=100.0)
    parser.add_argument("--min-read-ops", type=float, default=1_000.0)
    parser.add_argument("--max-read-p95-ms", type=float, default=20.0)
    parser.add_argument("--max-backup-restore-seconds", type=float, default=30.0)
    parser.add_argument("--min-semantic-margin", type=float, default=0.10)
    parser.add_argument("--max-embedding-p95-ms", type=float, default=1_000.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.embedding_endpoint) != bool(args.embedding_model):
        raise ValueError("--embedding-endpoint and --embedding-model must be used together")
    if bool(args.backup_retention_ref) != bool(args.backup_retention_sha256):
        raise ValueError("backup retention ref and sha256 must be used together")
    embedder = None
    probes: tuple[SemanticProbe, ...] = ()
    if args.embedding_endpoint:
        embedder = HTTPTextEmbedder(
            endpoint=args.embedding_endpoint,
            model=args.embedding_model,
            api_key_env=args.embedding_key_env,
            expected_dimensions=args.embedding_dimensions,
        )
        probes = _load_probes(args.semantic_probes)
    retention = (
        {"ref": args.backup_retention_ref, "sha256": args.backup_retention_sha256}
        if args.backup_retention_ref
        else None
    )
    thresholds = QualificationThresholds(
        min_write_ops_per_second=args.min_write_ops,
        max_write_p95_ms=args.max_write_p95_ms,
        min_read_ops_per_second=args.min_read_ops,
        max_read_p95_ms=args.max_read_p95_ms,
        max_backup_restore_seconds=args.max_backup_restore_seconds,
        min_semantic_margin=args.min_semantic_margin,
        max_embedding_p95_ms=args.max_embedding_p95_ms,
    )
    report = qualify_runtime(
        args.workdir,
        profile_id=args.profile_id,
        environment=args.environment,
        sample_count=args.sample_count,
        writer_count=args.writers,
        thresholds=thresholds,
        embedder=embedder,
        semantic_probes=probes,
        backup_retention_evidence=retention,
    )
    _atomic_json(args.output, report)
    print(
        f"Runtime qualification: storage={report['storage']['status']} "
        f"semantic={report['semantic_embedding']['status']} "
        f"scope={report['claim_scope']}"
    )
    print(f"Report: {args.output.resolve()}")
    if not report["checks_passed"]:
        return 2
    if args.environment == "production" and not report["production_claim_eligible"]:
        print(
            "Production claim rejected: semantic qualification and digest-bound retention "
            "evidence are mandatory.",
            file=sys.stderr,
        )
        return 3
    return 0


def _load_probes(path: Path) -> tuple[SemanticProbe, ...]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or set(parsed) != {"schema_version", "probes"}:
        raise ValueError("semantic probe file must contain schema_version and probes")
    if parsed["schema_version"] != 1 or isinstance(parsed["schema_version"], bool):
        raise ValueError("unsupported semantic probe schema_version")
    if not isinstance(parsed["probes"], list) or not parsed["probes"]:
        raise ValueError("semantic probe file must contain at least one probe")
    probes: list[SemanticProbe] = []
    for raw in parsed["probes"]:
        if not isinstance(raw, dict) or set(raw) != {"anchor", "paraphrase", "unrelated"}:
            raise ValueError("semantic probe fields are invalid")
        probes.append(SemanticProbe(**raw))
    return tuple(probes)


def _atomic_json(path: Path, value: object) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
