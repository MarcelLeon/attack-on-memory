"""Tamper-evident, signed export format for governance decision audits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Protocol

from attack_on_memory.governance.policies import GovernanceDecision


BUNDLE_SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64
DECISION_FIELDS = frozenset(
    {
        "request_id",
        "atom_id",
        "allowed",
        "reason_code",
        "policy_id",
        "policy_version",
        "role",
        "purpose",
        "decided_at",
    }
)


class AuditVerifier(Protocol):
    algorithm: str
    key_id: str

    def verify(self, payload: bytes, signature: bytes) -> bool: ...


class AuditSigner(AuditVerifier, Protocol):
    def sign(self, payload: bytes) -> bytes: ...


class HMACSHA256AuditSigner:
    """Shared-key signer for organization-internal audit verification."""

    algorithm = "hmac-sha256"

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if len(key) < 32:
            raise ValueError("HMAC audit key must contain at least 32 bytes")
        if not key_id.strip():
            raise ValueError("audit key_id cannot be empty")
        self._key = bytes(key)
        self.key_id = key_id

    def sign(self, payload: bytes) -> bytes:
        return hmac.digest(self._key, payload, "sha256")

    def verify(self, payload: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)


class Ed25519AuditSigner:
    """Optional public-key signer backed by the `cryptography` extra."""

    algorithm = "ed25519"

    def __init__(self, private_key: Any, *, key_id: str) -> None:
        if not key_id.strip():
            raise ValueError("audit key_id cannot be empty")
        self._private_key = private_key
        self.key_id = key_id

    @classmethod
    def generate(cls, *, key_id: str) -> Ed25519AuditSigner:
        Ed25519PrivateKey, _ = _ed25519_types()
        return cls(Ed25519PrivateKey.generate(), key_id=key_id)

    @classmethod
    def from_private_bytes(
        cls,
        private_key: bytes,
        *,
        key_id: str,
    ) -> Ed25519AuditSigner:
        Ed25519PrivateKey, _ = _ed25519_types()
        return cls(Ed25519PrivateKey.from_private_bytes(private_key), key_id=key_id)

    def private_bytes(self) -> bytes:
        try:
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install attack-on-memory[provenance]") from exc
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_verifier(self) -> Ed25519AuditVerifier:
        return Ed25519AuditVerifier(
            self._private_key.public_key(),
            key_id=self.key_id,
        )

    def sign(self, payload: bytes) -> bytes:
        return self._private_key.sign(payload)

    def verify(self, payload: bytes, signature: bytes) -> bool:
        return self.public_verifier().verify(payload, signature)


class Ed25519AuditVerifier:
    """Public-key-only verifier for externally checkable audit bundles."""

    algorithm = "ed25519"

    def __init__(self, public_key: Any, *, key_id: str) -> None:
        if not key_id.strip():
            raise ValueError("audit key_id cannot be empty")
        self._public_key = public_key
        self.key_id = key_id

    @classmethod
    def from_public_bytes(
        cls,
        public_key: bytes,
        *,
        key_id: str,
    ) -> Ed25519AuditVerifier:
        _, Ed25519PublicKey = _ed25519_types()
        return cls(Ed25519PublicKey.from_public_bytes(public_key), key_id=key_id)

    def public_bytes(self) -> bytes:
        try:
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install attack-on-memory[provenance]") from exc
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def verify(self, payload: bytes, signature: bytes) -> bool:
        try:
            from cryptography.exceptions import InvalidSignature
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install attack-on-memory[provenance]") from exc
        try:
            self._public_key.verify(signature, payload)
        except InvalidSignature:
            return False
        return True


def create_signed_audit_bundle(
    decisions: Iterable[GovernanceDecision],
    *,
    signer: AuditSigner,
    exported_at: datetime,
) -> str:
    """Create a deterministic JSON bundle with a signed hash-chain root."""
    _require_aware(exported_at, "exported_at")
    items = tuple(decisions)
    keys = [(item.request_id, item.atom_id) for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError("audit export contains duplicate request/atom keys")

    records: list[dict[str, Any]] = []
    previous_hash = GENESIS_HASH
    for decision in items:
        payload = _decision_to_dict(decision)
        record_hash = hashlib.sha256(
            bytes.fromhex(previous_hash) + _canonical_json(payload)
        ).hexdigest()
        records.append(
            {
                "decision": payload,
                "previous_hash": previous_hash,
                "record_hash": record_hash,
            }
        )
        previous_hash = record_hash

    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "algorithm": signer.algorithm,
        "key_id": signer.key_id,
        "exported_at": exported_at.isoformat(),
        "record_count": len(records),
        "root_hash": previous_hash,
    }
    signature = signer.sign(_canonical_json(manifest))
    signed_manifest = {
        **manifest,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return json.dumps(
        {"manifest": signed_manifest, "records": records},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def verify_signed_audit_bundle(
    bundle: str | bytes,
    *,
    verifier: AuditVerifier,
) -> tuple[GovernanceDecision, ...]:
    """Verify format, identity, signature, chain order, count, and root hash."""
    try:
        parsed = json.loads(bundle, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError("audit bundle is not valid JSON") from exc
    if not isinstance(parsed, Mapping) or set(parsed) != {"manifest", "records"}:
        raise ValueError("audit bundle must contain only manifest and records")
    manifest = parsed["manifest"]
    records = parsed["records"]
    if not isinstance(manifest, Mapping) or not isinstance(records, list):
        raise ValueError("audit bundle manifest/records have invalid types")
    expected_manifest_fields = {
        "schema_version",
        "algorithm",
        "key_id",
        "exported_at",
        "record_count",
        "root_hash",
        "signature",
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("audit manifest fields are invalid")
    if (
        not isinstance(manifest["schema_version"], int)
        or isinstance(manifest["schema_version"], bool)
        or manifest["schema_version"] != BUNDLE_SCHEMA_VERSION
    ):
        raise ValueError("unsupported audit bundle schema version")
    for field in ("algorithm", "key_id", "exported_at", "root_hash", "signature"):
        if not isinstance(manifest[field], str) or not manifest[field]:
            raise ValueError(f"audit manifest {field} must be a non-empty string")
    if (
        not isinstance(manifest["record_count"], int)
        or isinstance(manifest["record_count"], bool)
        or manifest["record_count"] < 0
    ):
        raise ValueError("audit manifest record_count must be a non-negative integer")
    if not _is_sha256(manifest["root_hash"]):
        raise ValueError("audit manifest root_hash is invalid")
    if manifest["algorithm"] != verifier.algorithm or manifest["key_id"] != verifier.key_id:
        raise ValueError("audit signature algorithm or key_id does not match verifier")
    exported_at = datetime.fromisoformat(str(manifest["exported_at"]))
    _require_aware(exported_at, "manifest.exported_at")
    try:
        signature = base64.b64decode(manifest["signature"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("audit manifest signature is invalid base64") from exc
    unsigned_manifest = dict(manifest)
    unsigned_manifest.pop("signature")
    if not verifier.verify(_canonical_json(unsigned_manifest), signature):
        raise ValueError("audit manifest signature verification failed")
    if manifest["record_count"] != len(records):
        raise ValueError("audit record count does not match manifest")

    decisions: list[GovernanceDecision] = []
    keys: set[tuple[str, str]] = set()
    previous_hash = GENESIS_HASH
    for raw_record in records:
        if not isinstance(raw_record, Mapping) or set(raw_record) != {
            "decision",
            "previous_hash",
            "record_hash",
        }:
            raise ValueError("audit record fields are invalid")
        if not _is_sha256(raw_record["previous_hash"]) or not _is_sha256(
            raw_record["record_hash"]
        ):
            raise ValueError("audit record hashes are invalid")
        if raw_record["previous_hash"] != previous_hash:
            raise ValueError("audit hash chain order is invalid")
        decision_payload = raw_record["decision"]
        decision = _decision_from_dict(decision_payload)
        expected_hash = hashlib.sha256(
            bytes.fromhex(previous_hash) + _canonical_json(decision_payload)
        ).hexdigest()
        if not hmac.compare_digest(str(raw_record["record_hash"]), expected_hash):
            raise ValueError("audit record hash verification failed")
        key = (decision.request_id, decision.atom_id)
        if key in keys:
            raise ValueError("audit bundle contains duplicate request/atom keys")
        keys.add(key)
        decisions.append(decision)
        previous_hash = expected_hash
    if not hmac.compare_digest(str(manifest["root_hash"]), previous_hash):
        raise ValueError("audit root hash does not match record chain")
    return tuple(decisions)


def _decision_to_dict(decision: GovernanceDecision) -> dict[str, Any]:
    _require_aware(decision.decided_at, "GovernanceDecision.decided_at")
    return {
        "request_id": decision.request_id,
        "atom_id": decision.atom_id,
        "allowed": decision.allowed,
        "reason_code": decision.reason_code,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "role": decision.role,
        "purpose": decision.purpose,
        "decided_at": decision.decided_at.isoformat(),
    }


def _decision_from_dict(value: object) -> GovernanceDecision:
    if not isinstance(value, Mapping) or set(value) != DECISION_FIELDS:
        raise ValueError("audit decision fields are invalid")
    if not isinstance(value["allowed"], bool):
        raise ValueError("audit decision allowed must be boolean")
    if not isinstance(value["policy_version"], int) or isinstance(
        value["policy_version"], bool
    ):
        raise ValueError("audit policy_version must be integer")
    decided_at = datetime.fromisoformat(str(value["decided_at"]))
    _require_aware(decided_at, "decision.decided_at")
    text_fields = DECISION_FIELDS - {"allowed", "policy_version", "decided_at"}
    if any(
        not isinstance(value[field], str) or not value[field]
        for field in text_fields
    ):
        raise ValueError("audit decision text fields must be non-empty")
    return GovernanceDecision(
        request_id=value["request_id"],
        atom_id=value["atom_id"],
        allowed=value["allowed"],
        reason_code=value["reason_code"],
        policy_id=value["policy_id"],
        policy_version=value["policy_version"],
        role=value["role"],
        purpose=value["purpose"],
        decided_at=decided_at,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"audit bundle contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _ed25519_types() -> tuple[Any, Any]:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install attack-on-memory[provenance]") from exc
    return Ed25519PrivateKey, Ed25519PublicKey
