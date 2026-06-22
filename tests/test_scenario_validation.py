from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from attack_on_memory.scenarios.spec_validation import validate_scenario_spec


class ScenarioValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        case_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "scenarios"
            / "case_02_scout_inheritance.json"
        )
        self.spec = json.loads(case_path.read_text(encoding="utf-8"))

    def test_known_valid_case(self) -> None:
        errors = validate_scenario_spec(self.spec)
        self.assertEqual(errors, [])

    def test_detects_edge_reference_errors(self) -> None:
        broken = copy.deepcopy(self.spec)
        broken["variants"][0]["edges"][0]["source_id"] = "missing_memory"
        errors = validate_scenario_spec(broken)
        self.assertTrue(any("source_id 'missing_memory' not found in memories" in err for err in errors))

    def test_detects_event_role_without_policy(self) -> None:
        broken = copy.deepcopy(self.spec)
        broken["variants"][0]["events"][0]["role"] = "ghost_role"
        errors = validate_scenario_spec(broken)
        self.assertTrue(any("role 'ghost_role' has no matching policy" in err for err in errors))

    def test_purpose_bound_scenario_is_valid(self) -> None:
        case_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "scenarios"
            / "case_04_purpose_bound_disclosure.json"
        )
        spec = json.loads(case_path.read_text(encoding="utf-8"))
        self.assertEqual(validate_scenario_spec(spec), [])

    def test_policy_version_must_be_positive_integer(self) -> None:
        broken = copy.deepcopy(self.spec)
        broken["variants"][0]["policies"][0]["version"] = 1.5
        errors = validate_scenario_spec(broken)
        self.assertTrue(any("version must be an integer >= 1" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
