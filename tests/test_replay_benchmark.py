from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from attack_on_memory.evals.replay_benchmark import (
    load_replay_benchmark,
    render_replay_report,
    run_replay_benchmark,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "examples" / "replays" / "privacy_safe_incidents.json"


class ReplayBenchmarkTests(unittest.TestCase):
    def test_fixture_produces_reproducible_paired_results(self) -> None:
        dataset = load_replay_benchmark(DATASET)
        first = run_replay_benchmark(dataset, bootstrap_samples=200, seed=42)
        second = run_replay_benchmark(dataset, bootstrap_samples=200, seed=42)

        self.assertEqual(first, second)
        self.assertEqual(first["sample_size"], len(dataset["cases"]))
        self.assertGreater(
            first["treatment"]["context_acceptance_rate"],
            first["control"]["context_acceptance_rate"],
        )
        self.assertLess(
            first["treatment"]["unsafe_inclusion_rate"],
            first["control"]["unsafe_inclusion_rate"],
        )
        self.assertIn("not production traffic", render_replay_report(first))

    def test_rejects_unclassified_private_dataset(self) -> None:
        dataset = load_replay_benchmark(DATASET)
        dataset["metadata"]["privacy"] = "raw"
        with self.assertRaisesRegex(ValueError, "privacy"):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "raw.json"
                path.write_text(json.dumps(dataset), encoding="utf-8")
                load_replay_benchmark(path)

    def test_requires_evidence_manifest_and_frozen_label_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            missing.write_bytes(DATASET.read_bytes())
            with self.assertRaisesRegex(ValueError, "manifest is missing"):
                load_replay_benchmark(missing)

        dataset = json.loads(DATASET.read_text(encoding="utf-8"))
        dataset["cases"][0]["forbidden_memory_ids"] = []
        raw = (json.dumps(dataset, ensure_ascii=False, indent=2) + "\n").encode()
        manifest = json.loads(
            DATASET.with_name("privacy_safe_incidents.manifest.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["dataset_file"] = "tampered.json"
        manifest["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_bytes(raw)
            path.with_name("tampered.manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "label-set SHA-256"):
                load_replay_benchmark(path)

    def test_sanitized_execution_replay_requires_approved_privacy_review(self) -> None:
        dataset = json.loads(DATASET.read_text(encoding="utf-8"))
        dataset["metadata"]["privacy"] = "sanitized"
        raw = (json.dumps(dataset, ensure_ascii=False, indent=2) + "\n").encode()
        manifest = json.loads(
            DATASET.with_name("privacy_safe_incidents.manifest.json").read_text(
                encoding="utf-8"
            )
        )
        manifest.update(
            {
                "dataset_file": "execution.json",
                "dataset_sha256": hashlib.sha256(raw).hexdigest(),
                "evidence_class": "sanitized-execution-derived",
            }
        )
        manifest["source"] = {
            "kind": "production-execution",
            "systems": ["incident-runner"],
            "window_start": "2026-06-01T00:00:00+00:00",
            "window_end": "2026-06-10T00:00:00+00:00",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "execution.json"
            path.write_bytes(raw)
            path.with_name("execution.manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "approved privacy review"):
                load_replay_benchmark(path)


if __name__ == "__main__":
    unittest.main()
