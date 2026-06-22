from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from attack_on_memory.domain.models import (
    Evidence,
    MemoryAtom,
    MemoryScope,
    RetrievedMemory,
    Sensitivity,
    TaskIntent,
)
from attack_on_memory.governance.analysis import (
    PolicyDecisionSample,
    assert_no_permission_expansion,
    compare_policy_change,
    lint_policy,
    lint_policy_set,
)
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor


NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _policy(*, version: int, sensitivity: Sensitivity) -> DisclosurePolicy:
    return DisclosurePolicy(
        role="executor",
        policy_id="ops-policy",
        version=version,
        max_sensitivity=sensitivity,
        allowed_domains=frozenset({"ops"}),
        allowed_tasks=frozenset({"recovery"}),
        allowed_purposes=frozenset({"incident-mitigation"}),
        require_explicit_purpose=True,
        min_confidence=0.5,
    )


def _sample(atom_id: str, sensitivity: Sensitivity) -> PolicyDecisionSample:
    atom = MemoryAtom(
        id=atom_id,
        claim="highly sensitive claim that must not enter a change report",
        evidence=(Evidence(ref=f"ref:{atom_id}", source="test", captured_at=NOW),),
        source_agent="test",
        confidence=0.9,
        scope=MemoryScope(domain="ops", task="recovery"),
        created_at=NOW - timedelta(hours=1),
        ttl=timedelta(days=30),
        sensitivity=sensitivity,
    )
    return PolicyDecisionSample(
        item=RetrievedMemory(atom=atom, score=0.8, reason="test"),
        intent=TaskIntent(
            request_id=f"request-{atom_id}",
            actor="worker",
            role="executor",
            domain="ops",
            task="recovery",
            query="recovery",
            purpose="incident-mitigation",
            as_of=NOW,
        ),
    )


class PolicyAnalysisTests(unittest.TestCase):
    def test_lint_flags_explicit_purpose_without_allowlist_as_error(self) -> None:
        policy = DisclosurePolicy(
            role="executor",
            policy_id="broken",
            allowed_domains=frozenset({"ops"}),
            allowed_tasks=frozenset({"recovery"}),
            require_explicit_purpose=True,
        )
        findings = lint_policy(policy)
        self.assertTrue(
            any(
                item.severity == "error"
                and item.code == "purpose.explicit_without_allowlist"
                for item in findings
            )
        )

    def test_lint_detects_duplicate_role_and_identity(self) -> None:
        first = _policy(version=1, sensitivity=Sensitivity.INTERNAL)
        duplicate = DisclosurePolicy(
            **{
                **first.__dict__,
                "role": "executor",
            }
        )
        findings = lint_policy_set((first, duplicate))
        codes = {item.code for item in findings if item.severity == "error"}
        self.assertEqual(
            codes,
            {"registration.duplicate_role", "identity.duplicate_version"},
        )

    def test_what_if_reports_and_blocks_new_sensitive_disclosure(self) -> None:
        current = _policy(version=1, sensitivity=Sensitivity.INTERNAL)
        candidate = _policy(version=2, sensitivity=Sensitivity.RESTRICTED)
        samples = (
            _sample("internal", Sensitivity.INTERNAL),
            _sample("restricted", Sensitivity.RESTRICTED),
        )

        report = compare_policy_change(current, candidate, samples)

        self.assertEqual(len(report.newly_allowed), 1)
        self.assertEqual(report.newly_allowed[0].atom_id, "restricted")
        self.assertNotIn("highly sensitive claim", str(report))
        with self.assertRaisesRegex(PermissionError, "expands disclosure"):
            assert_no_permission_expansion(report)

    def test_policy_registry_requires_explicit_next_version_update(self) -> None:
        governor = MemoryGovernor()
        current = _policy(version=1, sensitivity=Sensitivity.INTERNAL)
        governor.register_policy(current)
        with self.assertRaisesRegex(ValueError, "already registered"):
            governor.register_policy(_policy(version=2, sensitivity=Sensitivity.INTERNAL))
        with self.assertRaisesRegex(ValueError, "increment by exactly one"):
            governor.update_policy(
                _policy(version=3, sensitivity=Sensitivity.INTERNAL),
                expected_policy_id="ops-policy",
                expected_version=1,
            )
        updated = _policy(version=2, sensitivity=Sensitivity.INTERNAL)
        governor.update_policy(
            updated,
            expected_policy_id="ops-policy",
            expected_version=1,
        )
        self.assertEqual(governor.policy_for("executor"), updated)


if __name__ == "__main__":
    unittest.main()
