# Attack on Memory

> Memory governance for multi-agent systems.

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![CI](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/ci.yml)
[![Scorecard](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/scorecard.yml/badge.svg)](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/scorecard.yml)

## Why this project

As agents move from single-turn chat to long-running collaboration, the bottleneck shifts from model size to **memory quality**:
- **Trustworthy** memory (verifiable, traceable)
- **Controllable** memory (role-aware disclosure, revocable)
- **Evolvable** memory (inheritance, rollback, branch comparison)

Attack on Memory is a protocol-oriented memory layer for multi-agent systems:
**Graph Retrieval + Time-window Retrieval + Governance + BranchWorldModel**.

## 3-minute quickstart

```bash
# 1) unit tests
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 2) scenario validation
PYTHONPATH=src python3 examples/validate_scenarios.py

# 3) simulation demo
PYTHONPATH=src python3 examples/simulation_runner.py
```

## What you get in v0.1

- Domain model and runtime memory packet design
- Governance policies (selective disclosure, emergency controls)
- Scenario-driven simulation and validation
- OpenClaw adapter for context injection + writeback
- CI + Scorecard + Dependabot + contribution governance

## Reproducible benchmark snapshots

- Baseline report: `docs/benchmarks/v0.1-baseline.md`
- Snapshot report: `docs/benchmarks/v0.1-benchmark-snapshot.md`
- Raw latest results: `docs/benchmarks/latest-results.json`
- Snapshot generator: `scripts/generate_benchmark_snapshot.py`

## Architecture & docs

- Architecture: `docs/architecture.md`
- Scenario spec: `docs/scenario-spec.md`
- Experiments and value: `docs/experiments-and-value.md`
- OpenClaw integration: `docs/openclaw-integration.md`
- Threat model: `docs/threat-model.md`
- FAQ: `docs/FAQ.md`
- Starter contribution walkthrough: `docs/STARTER_PR_WALKTHROUGH.md`

## Project structure

- `src/attack_on_memory/domain/` – core models
- `src/attack_on_memory/application/` – retrieval and orchestration
- `src/attack_on_memory/governance/` – policy layer
- `src/attack_on_memory/runtime/` – runtime adapters and context
- `src/attack_on_memory/infrastructure/` – in-memory and backend adapters
- `examples/` – scenarios, validation, simulation runner
- `tests/` – unit tests and adapter wiring tests

## Security and governance

- Security policy: [`SECURITY.md`](./SECURITY.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- Contribution guide: [`CONTRIBUTING.md`](./CONTRIBUTING.md)

## Roadmap (next)

- Replay-derived benchmark (beyond scenario-derived baseline)
- Pluggable vector index adapter
- Pluggable graph backend adapters
- Stronger anti-poisoning governance and observability

## License

MIT
