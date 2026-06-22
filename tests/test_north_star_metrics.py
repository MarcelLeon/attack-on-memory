from __future__ import annotations

import unittest
from dataclasses import dataclass

from attack_on_memory.evals.north_star import build_north_star_snapshot


@dataclass
class FakeEvent:
    passed: bool
    diagnostics: dict[str, int]


@dataclass
class FakeVariant:
    passed: bool
    event_results: list[FakeEvent]
    metric_snapshot: dict[str, float]


class NorthStarMetricTests(unittest.TestCase):
    def test_builds_governed_safe_projection_snapshot(self) -> None:
        snapshot = build_north_star_snapshot(
            [
                FakeVariant(
                    passed=True,
                    event_results=[
                        FakeEvent(
                            passed=True,
                            diagnostics={
                                "retrieved": 4,
                                "projected": 3,
                                "redacted": 1,
                                "inherited": 2,
                                "contradictions": 1,
                            },
                        )
                    ],
                    metric_snapshot={"task_success_rate": 1.0},
                ),
                FakeVariant(
                    passed=False,
                    event_results=[
                        FakeEvent(
                            passed=False,
                            diagnostics={
                                "retrieved": 2,
                                "projected": 1,
                                "redacted": 1,
                                "inherited": 0,
                                "contradictions": 0,
                            },
                        )
                    ],
                    metric_snapshot={"task_success_rate": 0.0},
                ),
            ]
        )

        self.assertEqual(snapshot.retrieved_memories, 6)
        self.assertEqual(snapshot.projected_memories, 4)
        self.assertAlmostEqual(snapshot.governed_safe_projection_rate, 0.5)
        self.assertAlmostEqual(snapshot.governed_useful_memory_rate, 0.5)
        self.assertAlmostEqual(snapshot.governed_context_pass_rate, 0.5)
        self.assertAlmostEqual(snapshot.scenario_pass_rate, 0.5)
        self.assertAlmostEqual(snapshot.avg_task_success_rate, 0.5)
        self.assertAlmostEqual(snapshot.redaction_rate, 2 / 6)
        self.assertAlmostEqual(snapshot.inheritance_rate, 0.5)
        self.assertAlmostEqual(snapshot.contradiction_rate, 0.25)


if __name__ == "__main__":
    unittest.main()
