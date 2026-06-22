# Signed Governance Audit

SQLite immutability is an application invariant, not a defense against a database
administrator. Signed audit bundles add an offline tamper-evidence boundary.

## Format

Each canonical governance decision includes only request/atom IDs, allow/deny,
reason code, policy identity/version, role, purpose, and time. Records form a
SHA-256 chain. The manifest commits to schema version, algorithm, key ID, export
time, count, and final root hash, then signs that canonical manifest.

Verification rejects:

- changed record content
- record reordering or truncation
- duplicate request/atom keys
- root/count mismatch
- wrong algorithm, key ID, HMAC key, or Ed25519 public key

Private/shared keys are never included in the bundle.

## HMAC CLI

HMAC is suitable for verification within one trust domain. Supply a base64 key
through the environment, never a command-line argument:

```bash
export AOM_AUDIT_HMAC_KEY_B64="$(openssl rand -base64 32)"
python3 scripts/audit_bundle.py export \
  --database memory.db \
  --output audit-2026-06-19.json \
  --key-id org-audit-2026-01

python3 scripts/audit_bundle.py verify \
  --bundle audit-2026-06-19.json \
  --key-id org-audit-2026-01
```

Rotate keys by changing `key_id`; retain the corresponding verifier material for
the full audit-retention period.

## Ed25519 API

Install `attack-on-memory[provenance]` and use `Ed25519AuditSigner` for public-key
verification. Distribute only `Ed25519AuditVerifier.public_bytes()` to external
auditors. HMAC does not provide public verifiability or non-repudiation.

## Remaining production boundary

Export bundles to independently controlled append-only/WORM storage. This project
does not manage HSM/KMS custody, key revocation, retention policy, or external
timestamping; those controls must be qualified in the deployment environment.
