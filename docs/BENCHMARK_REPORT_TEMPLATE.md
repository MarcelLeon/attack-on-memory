# Benchmark Report Template

## 1. Summary
- Date:
- Commit:
- Dataset / Replay source:
- Owner:

## 2. Experiment Design
- Control: recent-context only
- Treatment: Attack on Memory (retrieval + governance + feedback)
- Traffic split / sample size:
- Evaluation window:

## 3. Commands
```bash
PYTHONPATH=src python3 examples/validate_scenarios.py
PYTHONPATH=src python3 examples/simulation_runner.py --json-output /tmp/aom-results.json
```

## 4. Metrics
| Metric | Control | Treatment | Delta |
|---|---:|---:|---:|
| hit_rate |  |  |  |
| task_success_rate |  |  |  |
| repeat_error_rate |  |  |  |
| conflict_rate |  |  |  |
| contamination_rate |  |  |  |
| avg_latency_ms |  |  |  |
| avg_token_cost |  |  |  |

## 5. Key Findings
1.
2.
3.

## 6. Failure Analysis
- Top failure signatures:
- Memory poisoning patterns:
- Governance misses:

## 7. Action Items
- [ ] Policy tuning
- [ ] Additional scenario cases
- [ ] Retrieval weight calibration
- [ ] Rollback guard improvements
