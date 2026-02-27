from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from attack_on_memory.scenarios.replay_converter import (
    build_scenario_from_replay,
    load_replay_records,
)
from attack_on_memory.scenarios.spec_validation import validate_scenario_spec


class ReplayConverterTests(unittest.TestCase):
    def test_jsonl_replay_to_scenario(self) -> None:
        records = [
            {
                "task_id": "evt-1",
                "actor": "armin",
                "role": "strategist",
                "domain": "survey-corps",
                "task": "operation-planning",
                "objective": "Plan operation",
                "seed_memory_ids": ["mem_a"],
                "context": {
                    "projected_memory_ids": ["mem_a", "mem_b"],
                    "citation_ids": ["mem_a"]
                },
                "outcome": {
                    "success": True,
                    "latency_ms": 120,
                    "token_cost": 900,
                    "error_signature": None,
                    "conflict": False,
                    "contamination": False
                }
            },
            {
                "task_id": "evt-2",
                "actor": "squad_lead",
                "role": "field_executor",
                "domain": "survey-corps",
                "task": "operation-planning",
                "objective": "Execute plan",
                "seed_memory_ids": ["mem_b"],
                "success": True,
                "latency_ms": 90,
                "token_cost": 700
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            replay_path = Path(tmp_dir) / "replay.jsonl"
            replay_path.write_text(
                "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
                encoding="utf-8",
            )

            loaded = load_replay_records(replay_path)
            scenario = build_scenario_from_replay(
                loaded,
                scenario_id="replay_import_test",
                title="Replay Import",
                description="Replay conversion test",
                assert_from_context=True,
            )

        errors = validate_scenario_spec(scenario)
        self.assertEqual(errors, [])

        variant = scenario["variants"][0]
        self.assertEqual(variant["variant_id"], "replay_import")

        memory_ids = {memory["id"] for memory in variant["memories"]}
        self.assertEqual(memory_ids, {"mem_a", "mem_b"})

        first_expected = variant["events"][0].get("expected", {})
        self.assertEqual(set(first_expected.get("must_include", [])), {"mem_a", "mem_b"})


if __name__ == "__main__":
    unittest.main()
