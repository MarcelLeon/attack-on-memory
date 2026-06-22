from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from attack_on_memory.evals.runtime_qualification import (
    QualificationThresholds,
    SemanticProbe,
    qualify_runtime,
    validate_runtime_qualification_report,
)


NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
LOOSE = QualificationThresholds(
    min_write_ops_per_second=0,
    max_write_p95_ms=10_000,
    min_read_ops_per_second=0,
    max_read_p95_ms=10_000,
    max_backup_restore_seconds=30,
    min_semantic_margin=0.5,
    max_embedding_p95_ms=10_000,
)


class _SemanticEmbedder:
    identity = {
        "adapter": "test-semantic-provider",
        "endpoint_origin": "https://embedding.example.test",
        "model": "semantic-v1",
        "expected_dimensions": 2,
    }

    def embed(self, text: str) -> tuple[float, float]:
        return (0.9, 0.1) if text != "banana recipe" else (0.0, 1.0)


class _FailingSemanticEmbedder(_SemanticEmbedder):
    def embed(self, text: str) -> tuple[float, float]:
        raise RuntimeError(f"provider echoed sensitive input: {text}")


PROBES = (
    SemanticProbe(
        anchor="restore the database backup",
        paraphrase="recover the database from a snapshot",
        unrelated="banana recipe",
    ),
)


class RuntimeQualificationTests(unittest.TestCase):
    def test_cli_writes_machine_readable_development_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "qualify_runtime.py"),
                    "--workdir",
                    str(root / "workload"),
                    "--output",
                    str(output),
                    "--profile-id",
                    "cli-development",
                    "--environment",
                    "development",
                    "--sample-count",
                    "6",
                    "--writers",
                    "2",
                    "--min-write-ops",
                    "0",
                    "--max-write-p95-ms",
                    "10000",
                    "--min-read-ops",
                    "0",
                    "--max-read-p95-ms",
                    "10000",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["profile_id"], "cli-development")
        self.assertTrue(report["checks_passed"])
        self.assertFalse(report["production_claim_eligible"])

    def test_development_storage_run_is_measured_but_not_production_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = qualify_runtime(
                directory,
                profile_id="local-contract",
                environment="development",
                sample_count=12,
                writer_count=2,
                thresholds=LOOSE,
                now=NOW,
            )
        self.assertTrue(report["checks_passed"])
        self.assertFalse(report["production_claim_eligible"])
        self.assertEqual(report["claim_scope"], "non-production-evidence")
        self.assertEqual(report["storage"]["status"], "pass")
        self.assertEqual(report["storage"]["live_integrity"]["atoms"], 12)
        self.assertEqual(report["storage"]["restored_integrity"]["atoms"], 12)
        self.assertEqual(report["semantic_embedding"]["status"], "not_run")
        validate_runtime_qualification_report(report)

        tampered = copy.deepcopy(report)
        tampered["production_claim_eligible"] = True
        with self.assertRaisesRegex(ValueError, "production conclusion"):
            validate_runtime_qualification_report(tampered)

    def test_production_eligibility_requires_semantics_and_retention_evidence(self) -> None:
        evidence = {"ref": "s3://audit/retention-proof.json", "sha256": "a" * 64}
        with tempfile.TemporaryDirectory() as directory:
            report = qualify_runtime(
                directory,
                profile_id="prod-cn-east-1",
                environment="production",
                sample_count=12,
                writer_count=2,
                thresholds=LOOSE,
                embedder=_SemanticEmbedder(),
                semantic_probes=PROBES,
                backup_retention_evidence=evidence,
                now=NOW,
            )
        self.assertTrue(report["production_claim_eligible"])
        self.assertEqual(report["claim_scope"], "production-eligible")
        self.assertEqual(report["semantic_embedding"]["status"], "pass")
        self.assertGreater(report["semantic_embedding"]["minimum_margin"], 0.5)
        self.assertNotIn("credential", str(report))
        validate_runtime_qualification_report(report)

        tampered_margin = copy.deepcopy(report)
        tampered_margin["semantic_embedding"]["minimum_margin"] = -1.0
        with self.assertRaisesRegex(ValueError, "semantic check is not bound"):
            validate_runtime_qualification_report(tampered_margin)

        with tempfile.TemporaryDirectory() as directory:
            without_retention = qualify_runtime(
                directory,
                profile_id="prod-without-retention",
                environment="production",
                sample_count=6,
                writer_count=2,
                thresholds=LOOSE,
                embedder=_SemanticEmbedder(),
                semantic_probes=PROBES,
                now=NOW,
            )
        self.assertFalse(without_retention["production_claim_eligible"])

    def test_threshold_failure_is_explicit_and_machine_readable(self) -> None:
        impossible = QualificationThresholds(
            min_write_ops_per_second=10**12,
            max_write_p95_ms=10_000,
            min_read_ops_per_second=0,
            max_read_p95_ms=10_000,
            max_backup_restore_seconds=30,
        )
        with tempfile.TemporaryDirectory() as directory:
            report = qualify_runtime(
                Path(directory),
                profile_id="strict",
                environment="staging",
                sample_count=4,
                writer_count=1,
                thresholds=impossible,
                now=NOW,
            )
        self.assertFalse(report["checks_passed"])
        failed = [
            check["name"]
            for check in report["storage"]["checks"]
            if not check["passed"]
        ]
        self.assertIn("write_rate", failed)

    def test_provider_failure_is_reported_without_echoing_probe_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = qualify_runtime(
                directory,
                profile_id="provider-failure",
                environment="staging",
                sample_count=4,
                writer_count=1,
                thresholds=LOOSE,
                embedder=_FailingSemanticEmbedder(),
                semantic_probes=PROBES,
                now=NOW,
            )
        semantic = report["semantic_embedding"]
        self.assertEqual(semantic["status"], "fail")
        self.assertEqual(semantic["error_type"], "RuntimeError")
        self.assertNotIn(PROBES[0].anchor, str(semantic))

    def test_rejects_unverifiable_retention_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "retention evidence"):
                qualify_runtime(
                    directory,
                    profile_id="bad-proof",
                    environment="production",
                    sample_count=1,
                    writer_count=1,
                    thresholds=LOOSE,
                    backup_retention_evidence={"ref": "ticket-1", "sha256": "nope"},
                    now=NOW,
                )


if __name__ == "__main__":
    unittest.main()
