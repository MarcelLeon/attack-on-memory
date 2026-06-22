from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from attack_on_memory.governance.policies import GovernanceDecision
from attack_on_memory.governance.signed_audit import (
    Ed25519AuditSigner,
    Ed25519AuditVerifier,
    HMACSHA256AuditSigner,
    create_signed_audit_bundle,
    verify_signed_audit_bundle,
)
from attack_on_memory.infrastructure.sqlite_store import SQLiteStore


NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def _decisions() -> tuple[GovernanceDecision, ...]:
    return (
        GovernanceDecision(
            request_id="request-1",
            atom_id="memory-a",
            allowed=True,
            reason_code="policy.allowed",
            policy_id="ops-policy",
            policy_version=7,
            role="executor",
            purpose="incident-mitigation",
            decided_at=NOW,
        ),
        GovernanceDecision(
            request_id="request-1",
            atom_id="memory-b",
            allowed=False,
            reason_code="sensitivity.exceeded",
            policy_id="ops-policy",
            policy_version=7,
            role="executor",
            purpose="incident-mitigation",
            decided_at=NOW + timedelta(microseconds=1),
        ),
    )


class SignedAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = bytes(range(32))
        self.signer = HMACSHA256AuditSigner(self.key, key_id="audit-key-2026-01")
        self.bundle = create_signed_audit_bundle(
            _decisions(),
            signer=self.signer,
            exported_at=NOW + timedelta(hours=1),
        )

    def test_hmac_bundle_is_deterministic_verifiable_and_contains_no_key(self) -> None:
        repeated = create_signed_audit_bundle(
            _decisions(),
            signer=self.signer,
            exported_at=NOW + timedelta(hours=1),
        )
        self.assertEqual(repeated, self.bundle)
        self.assertEqual(
            verify_signed_audit_bundle(self.bundle, verifier=self.signer),
            _decisions(),
        )
        self.assertNotIn(base64.b64encode(self.key).decode("ascii"), self.bundle)

    def test_detects_record_tampering(self) -> None:
        parsed = json.loads(self.bundle)
        parsed["records"][0]["decision"]["reason_code"] = "policy.tampered"
        with self.assertRaisesRegex(ValueError, "record hash"):
            verify_signed_audit_bundle(json.dumps(parsed), verifier=self.signer)

    def test_detects_reordering_and_truncation(self) -> None:
        reordered = json.loads(self.bundle)
        reordered["records"].reverse()
        with self.assertRaisesRegex(ValueError, "chain order"):
            verify_signed_audit_bundle(json.dumps(reordered), verifier=self.signer)

        truncated = json.loads(self.bundle)
        truncated["records"].pop()
        with self.assertRaisesRegex(ValueError, "record count"):
            verify_signed_audit_bundle(json.dumps(truncated), verifier=self.signer)

    def test_rejects_duplicate_json_keys(self) -> None:
        duplicate = '{"manifest":null,' + self.bundle.lstrip()[1:]
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            verify_signed_audit_bundle(duplicate, verifier=self.signer)

    def test_wrong_key_and_key_id_fail(self) -> None:
        wrong_key = HMACSHA256AuditSigner(b"x" * 32, key_id=self.signer.key_id)
        with self.assertRaisesRegex(ValueError, "signature verification"):
            verify_signed_audit_bundle(self.bundle, verifier=wrong_key)
        wrong_id = HMACSHA256AuditSigner(self.key, key_id="retired-key")
        with self.assertRaisesRegex(ValueError, "key_id"):
            verify_signed_audit_bundle(self.bundle, verifier=wrong_id)

    def test_ed25519_public_verifier_round_trip_and_wrong_public_key(self) -> None:
        signer = Ed25519AuditSigner.generate(key_id="external-audit-2026")
        verifier = signer.public_verifier()
        bundle = create_signed_audit_bundle(
            _decisions(),
            signer=signer,
            exported_at=NOW,
        )
        public_copy = Ed25519AuditVerifier.from_public_bytes(
            verifier.public_bytes(),
            key_id=verifier.key_id,
        )
        private_copy = Ed25519AuditSigner.from_private_bytes(
            signer.private_bytes(),
            key_id=signer.key_id,
        )
        self.assertEqual(
            verify_signed_audit_bundle(bundle, verifier=public_copy),
            _decisions(),
        )
        self.assertTrue(private_copy.verify(b"payload", private_copy.sign(b"payload")))

        wrong = Ed25519AuditSigner.generate(key_id=signer.key_id).public_verifier()
        with self.assertRaisesRegex(ValueError, "signature verification"):
            verify_signed_audit_bundle(bundle, verifier=wrong)

    def test_sqlite_restart_export_remains_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.db"
            with SQLiteStore(path) as store:
                store.record_governance_decisions(_decisions())
            with SQLiteStore(path) as reopened:
                bundle = create_signed_audit_bundle(
                    reopened.list_governance_decisions(),
                    signer=self.signer,
                    exported_at=NOW,
                )
            self.assertEqual(
                verify_signed_audit_bundle(bundle, verifier=self.signer),
                _decisions(),
            )

    def test_cli_exports_and_verifies_with_environment_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "audit.db"
            bundle = root / "audit.json"
            with SQLiteStore(database) as store:
                store.record_governance_decisions(_decisions())
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            environment["AOM_AUDIT_HMAC_KEY_B64"] = base64.b64encode(
                self.key
            ).decode("ascii")
            export = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "audit_bundle.py"),
                    "export",
                    "--database",
                    str(database),
                    "--output",
                    str(bundle),
                    "--key-id",
                    self.signer.key_id,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(export.returncode, 0, export.stderr)
            verify = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "audit_bundle.py"),
                    "verify",
                    "--bundle",
                    str(bundle),
                    "--key-id",
                    self.signer.key_id,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertIn("Verified 2 governance decision(s)", verify.stdout)


if __name__ == "__main__":
    unittest.main()
