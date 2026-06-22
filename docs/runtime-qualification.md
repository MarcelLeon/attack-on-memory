# Runtime qualification

`scripts/qualify_runtime.py` turns the remaining durability-and-scale claims into
an executable target-environment gate. It measures concurrent committed writes,
point reads, p50/p95 latency, online backup, integrity verification, and atomic
restore. When a hosted semantic model is configured, it also measures latency,
dimension stability, and paraphrase-vs-unrelated similarity margins on checked-in
English and Chinese probes. Storage and embedding are measured separately so remote
model latency is not accidentally presented as SQLite write throughput.

The generated JSON records the runtime fingerprint, exact thresholds, observations,
individual pass/fail checks, live/restored object counts, backup SHA-256, provider
identity without credentials, and claim scope.

The checked-in `docs/benchmarks/runtime-development-v0.1.json` is a 500-write,
four-writer development snapshot. `make check-runtime-qualification` validates its
schema and recomputes its pass/fail conclusions. It intentionally says
`semantic_embedding.status=not_run` and `production_claim_eligible=false`.

## Development storage run

This produces useful local evidence but can never authorize a production claim:

```bash
make qualify-runtime \
  WORKDIR=/tmp/aom-qualification-local \
  OUTPUT=/tmp/aom-qualification-local.json \
  PROFILE=developer-mac \
  ENVIRONMENT=development
```

Qualification work directories are intentionally single-use. Reusing one fails
closed so an old database or backup cannot contaminate a later measurement.

## Target production run

Use an HTTPS embedding endpoint compatible with the `POST /embeddings` JSON shape.
The credential is resolved from the named environment variable at request time and
is never included in the adapter identity or report.

```bash
export AOM_EMBEDDING_API_KEY='resolved-by-your-secret-manager'

make qualify-runtime \
  WORKDIR=/var/tmp/aom-qualification-2026-06-19 \
  OUTPUT=artifacts/aom-qualification-prod.json \
  PROFILE=prod-cn-east-1-sqlite-v1 \
  ENVIRONMENT=production \
  QUALIFY_ARGS='--sample-count 10000 --writers 8 \
    --embedding-endpoint https://embedding.example.com/v1/embeddings \
    --embedding-model multilingual-semantic-v3 \
    --embedding-dimensions 1024 \
    --backup-retention-ref s3://compliance/retention-proof.json \
    --backup-retention-sha256 <64-lowercase-hex-digest>'
```

`production_claim_eligible` is true only if all of these are true:

1. `environment` is exactly `production`;
2. every configured storage and recovery threshold passes;
3. a named semantic provider passes every probe and latency threshold;
4. backup-retention evidence has a reference and a SHA-256 digest.

The evidence reference should identify an independently retained, access-controlled
artifact showing scheduled backups, retention duration, restore drill outcome, and
target deployment identity. The harness validates the binding fields; the external
system remains responsible for custody and retention enforcement.

## Interpretation boundary

A development or staging report remains `non-production-evidence`, even when every
measurement passes. A production report covers only its named profile, workload,
thresholds, model, and point in time. It does not prove geo-replication, arbitrary
future load, or the quality of an untested model version.
