# Scenario Specs

This folder contains executable JSON specs for the Attack on Memory simulation runner.

## Included cases
- `case_01_selective_disclosure_manipulation.json`
- `case_02_scout_inheritance.json`
- `case_03_rumbling_emergency_privilege.json`
- `scenario.schema.json` (spec contract)

## Run

```bash
PYTHONPATH=src python examples/simulation_runner.py
```

Optional JSON report:

```bash
PYTHONPATH=src python examples/simulation_runner.py --json-output /tmp/aom-results.json
```

Validate all scenario files:

```bash
PYTHONPATH=src python examples/validate_scenarios.py
```

Import OpenClaw replay logs into a runnable scenario:

```bash
PYTHONPATH=src python examples/openclaw_replay_to_scenario.py \
  --replay /path/to/replay.jsonl \
  --output /tmp/replay_scenario.json \
  --scenario-id openclaw_replay_demo
```
