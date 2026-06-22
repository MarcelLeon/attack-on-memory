from __future__ import annotations

import unittest
from pathlib import Path

from attack_on_memory.evals.project_state import (
    load_project_state,
    render_project_status,
    validate_project_state,
)


ROOT = Path(__file__).resolve().parents[1]


class ProjectStateTests(unittest.TestCase):
    def test_repository_ledger_is_valid_and_renderable(self) -> None:
        state = load_project_state(ROOT / "docs" / "project-state.json")
        self.assertEqual(validate_project_state(state, ROOT), [])
        report = render_project_status(state)
        self.assertIn(state["goal"], report)
        self.assertIn("Current milestone: M1", report)
        self.assertIn("D004 [in_progress]", report)

    def test_done_deliverable_requires_evidence(self) -> None:
        state = load_project_state(ROOT / "docs" / "project-state.json")
        state["deliverables"][0]["evidence"] = []
        failures = validate_project_state(state, ROOT)
        self.assertTrue(any("done but has no evidence" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
