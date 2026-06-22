from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from attack_on_memory.application.services import RetrievalService
from attack_on_memory.domain.models import (
    Evidence,
    MemoryAtom,
    MemoryScope,
    Sensitivity,
    TaskIntent,
)
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor
from attack_on_memory.infrastructure.sqlite_store import SQLiteStore
from attack_on_memory.runtime.context import ContextAssembler


NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _atom(atom_id: str, sensitivity: Sensitivity) -> MemoryAtom:
    return MemoryAtom(
        id=atom_id,
        claim=f"private claim for {atom_id}",
        evidence=(Evidence(ref=f"ref:{atom_id}", source="test", captured_at=NOW),),
        source_agent="test",
        confidence=0.9,
        scope=MemoryScope(domain="ops", task="recovery"),
        created_at=NOW - timedelta(hours=1),
        ttl=timedelta(days=30),
        sensitivity=sensitivity,
        tags=("recovery",),
    )


def _governor() -> MemoryGovernor:
    governor = MemoryGovernor()
    governor.register_policy(
        DisclosurePolicy(
            role="executor",
            policy_id="ops-recovery",
            version=7,
            max_sensitivity=Sensitivity.INTERNAL,
            allowed_domains=frozenset({"ops"}),
            allowed_tasks=frozenset({"recovery"}),
            allowed_purposes=frozenset({"incident-mitigation"}),
            require_explicit_purpose=True,
        )
    )
    return governor


class GovernanceAuditTests(unittest.TestCase):
    def test_purpose_binding_denies_without_leaking_decision_details_to_packet(self) -> None:
        with SQLiteStore(":memory:") as store:
            store.upsert_atom(_atom("internal-plan", Sensitivity.INTERNAL))
            store.upsert_atom(_atom("restricted-plan", Sensitivity.RESTRICTED))
            assembler = ContextAssembler(
                RetrievalService(store),
                _governor(),
                governance_audit_sink=store,
            )
            packet = assembler.assemble(
                TaskIntent(
                    request_id="purpose-missing",
                    actor="worker",
                    role="executor",
                    domain="ops",
                    task="recovery",
                    query="recovery plan",
                    as_of=NOW,
                ),
                top_k=10,
            )

            self.assertEqual(packet.memories, ())
            self.assertEqual(packet.governance_audit_id, "purpose-missing")
            self.assertEqual(packet.diagnostics["purpose_denied"], 1)
            self.assertEqual(packet.diagnostics["sensitivity_denied"], 1)
            packet_payload = asdict(packet)
            self.assertNotIn("governance_decisions", packet_payload)
            self.assertNotIn("internal-plan", str(packet_payload))
            self.assertNotIn("restricted-plan", str(packet_payload))

            decisions = store.list_governance_decisions("purpose-missing")
            self.assertEqual(len(decisions), 2)
            self.assertEqual(
                {item.reason_code for item in decisions},
                {"purpose.required", "sensitivity.exceeded"},
            )
            self.assertTrue(all(item.policy_version == 7 for item in decisions))

    def test_allowed_purpose_projects_only_authorized_memory_and_persists_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.db"
            store = SQLiteStore(path)
            store.upsert_atom(_atom("internal-plan", Sensitivity.INTERNAL))
            store.upsert_atom(_atom("restricted-plan", Sensitivity.RESTRICTED))
            assembler = ContextAssembler(
                RetrievalService(store),
                _governor(),
                governance_audit_sink=store,
            )
            packet = assembler.assemble(
                TaskIntent(
                    request_id="purpose-allowed",
                    actor="worker",
                    role="executor",
                    domain="ops",
                    task="recovery",
                    query="recovery plan",
                    purpose="incident-mitigation",
                    as_of=NOW,
                ),
                top_k=10,
            )
            self.assertEqual([item.atom_id for item in packet.memories], ["internal-plan"])
            store.close()

            with SQLiteStore(path) as reopened:
                decisions = reopened.list_governance_decisions("purpose-allowed")
                by_atom = {item.atom_id: item for item in decisions}
                self.assertTrue(by_atom["internal-plan"].allowed)
                self.assertEqual(by_atom["internal-plan"].reason_code, "policy.allowed")
                self.assertFalse(by_atom["restricted-plan"].allowed)
                self.assertEqual(
                    by_atom["restricted-plan"].reason_code,
                    "sensitivity.exceeded",
                )
                self.assertEqual(reopened.verify_integrity()["governance_decisions"], 2)
                with self.assertRaisesRegex(ValueError, "immutable"):
                    reopened.record_governance_decisions(decisions)

    def test_wrong_purpose_has_stable_reason_code(self) -> None:
        with SQLiteStore(":memory:") as store:
            store.upsert_atom(_atom("internal-plan", Sensitivity.INTERNAL))
            assembler = ContextAssembler(
                RetrievalService(store),
                _governor(),
                governance_audit_sink=store,
            )
            packet = assembler.assemble(
                TaskIntent(
                    request_id="purpose-wrong",
                    actor="worker",
                    role="executor",
                    domain="ops",
                    task="recovery",
                    query="recovery plan",
                    purpose="analytics-training",
                    as_of=NOW,
                )
            )
            self.assertEqual(packet.memories, ())
            decision = store.list_governance_decisions("purpose-wrong")[0]
            self.assertEqual(decision.reason_code, "purpose.not_allowed")
            self.assertEqual(decision.purpose, "analytics-training")


if __name__ == "__main__":
    unittest.main()
