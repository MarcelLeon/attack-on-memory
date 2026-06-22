# Replay evidence admission

Every replay dataset must have a sibling `<dataset-stem>.manifest.json`. The
benchmark loader refuses to run without it. This prevents a privacy label or a
hand-written provenance sentence from being treated as sufficient production
evidence.

The manifest binds two independent SHA-256 values:

- `dataset_sha256` covers the exact dataset bytes;
- `label_set_sha256` covers case IDs and relevant, required, and forbidden memory
  labels in canonical JSON.

It also records the evidence class, label protocol/reviewer/lock time, whether
labels were assigned independently of system output, privacy review, source
systems, and the source window. Labels must be locked before manifest registration.

For `privacy=synthetic`, the only accepted class is `synthetic-development` and
the source window must be null. For `privacy=sanitized`, the class must be
`sanitized-execution-derived`, the source must be `production-execution`, the
collection window must be valid, and privacy review must be `approved`.

Run a custom execution-derived replay with:

```bash
PYTHONPATH=src python3 scripts/run_replay_benchmark.py \
  --dataset /secure/replays/incidents-v1.json \
  --results artifacts/incidents-v1-results.json \
  --report artifacts/incidents-v1-report.md
```

The sibling manifest is discovered automatically. A changed dataset, post-hoc
label edit, missing review, duplicate JSON key, mismatched evidence class, or bad
source window fails before evaluation.

This admission protocol establishes provenance and detects relabeling; it does not
create execution evidence. D004 remains incomplete until approved, sanitized
execution-derived incidents are supplied and the paired intervals are rerun.
