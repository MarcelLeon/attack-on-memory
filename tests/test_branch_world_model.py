from __future__ import annotations

import unittest

from attack_on_memory.application.branch_world_model import BranchEvaluation, BranchWorldModelService
from attack_on_memory.domain.models import BranchStatus
from attack_on_memory.infrastructure.in_memory import InMemoryStore


class BranchWorldModelTests(unittest.TestCase):
    def test_branch_lifecycle_and_ranking(self) -> None:
        store = InMemoryStore()
        service = BranchWorldModelService(store)

        branch_a = service.create_branch(
            branch_id="a",
            name="A",
            hypothesis="先限流后扩容",
            parent_id="main",
        )
        self.assertEqual(branch_a.status, BranchStatus.ACTIVE)

        updated = service.update_status("a", BranchStatus.MERGED)
        self.assertEqual(updated.status, BranchStatus.MERGED)

        ranks = service.rank_branches(
            [
                BranchEvaluation(branch_id="a", success_rate=0.8, risk_score=0.3, cost_score=0.2),
                BranchEvaluation(branch_id="b", success_rate=0.75, risk_score=0.2, cost_score=0.5),
            ]
        )
        self.assertEqual(ranks[0].branch_id, "a")
        self.assertGreater(ranks[0].utility, ranks[1].utility)


if __name__ == "__main__":
    unittest.main()
