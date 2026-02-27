# Release Notes — v0.1.0

## Highlights
- Introduced docs-first modular memory framework for multi-agent systems.
- Added core model: `MemoryAtom`, `MemoryEdge`, `Branch`, `TaskIntent`.
- Implemented retrieval pipeline with time-window + graph-neighbor boosting.
- Implemented governance layer for selective disclosure by role and sensitivity.
- Added OpenClaw adapter for context build + outcome feedback loop.
- Added scenario contract + validator + replay converter.

## Engineering & OSS Baseline
- CI workflow across Python 3.11 / 3.12 / 3.13.
- OSSF Scorecard workflow.
- Dependabot for GitHub Actions + pip.
- Contributing/PR/Issue templates, security policy, code of conduct.
- Local quality gate (`make quality-gate`).

## Validation
- Unit tests: 8 passing.
- Scenario validation: 3/3 passing.

## Known limitations
- In-memory backend only (v0.1 scope).
- Rule-based token overlap retrieval (no vector DB yet).
- No hosted benchmark dashboard yet.

## Next
- v0.2: vector index + graph DB adapter (interface-compatible).
- v0.2: replay-driven benchmark publication.
- v0.2: stronger anti-poisoning governance policies.
