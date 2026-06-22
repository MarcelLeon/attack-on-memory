#!/usr/bin/env python3
"""Export or verify signed governance audits without command-line key exposure."""

from __future__ import annotations

import argparse
import base64
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attack_on_memory.governance.signed_audit import (  # noqa: E402
    HMACSHA256AuditSigner,
    create_signed_audit_bundle,
    verify_signed_audit_bundle,
)
from attack_on_memory.infrastructure.sqlite_store import SQLiteStore  # noqa: E402


def _signer(environment_name: str, key_id: str) -> HMACSHA256AuditSigner:
    encoded = os.environ.get(environment_name)
    if encoded is None:
        raise ValueError(f"missing audit key environment variable: {environment_name}")
    try:
        key = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError(f"{environment_name} must contain base64 key bytes") from exc
    return HMACSHA256AuditSigner(key, key_id=key_id)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signed governance audit bundles")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--database", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--request-id")
    export.add_argument("--key-id", required=True)
    export.add_argument("--key-env", default="AOM_AUDIT_HMAC_KEY_B64")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle", required=True)
    verify.add_argument("--key-id", required=True)
    verify.add_argument("--key-env", default="AOM_AUDIT_HMAC_KEY_B64")

    args = parser.parse_args(argv)
    try:
        signer = _signer(args.key_env, args.key_id)
        if args.command == "export":
            with SQLiteStore(args.database) as store:
                decisions = store.list_governance_decisions(args.request_id)
            bundle = create_signed_audit_bundle(
                decisions,
                signer=signer,
                exported_at=datetime.now(timezone.utc),
            )
            _atomic_write(Path(args.output), bundle)
            print(f"Exported {len(decisions)} signed governance decision(s).")
            return 0

        bundle = Path(args.bundle).read_bytes()
        decisions = verify_signed_audit_bundle(bundle, verifier=signer)
        print(f"Verified {len(decisions)} governance decision(s).")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Audit bundle error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
