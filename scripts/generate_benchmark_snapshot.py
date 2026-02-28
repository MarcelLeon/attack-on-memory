#!/usr/bin/env python3
"""Generate a reproducible benchmark snapshot from scenario runner output."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "docs" / "benchmarks" / "latest-results.json"
OUT_PATH = ROOT / "docs" / "benchmarks" / "v0.1-benchmark-snapshot.md"


def main() -> int:
    if not RESULT_PATH.exists():
        raise SystemExit(f"Missing results file: {RESULT_PATH}")

    data = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    rows = []
    for item in data:
        m = item["metric_snapshot"]
        rows.append(
            {
                "scenario": item["scenario_id"],
                "variant": item["variant_id"],
                "passed": item["passed"],
                "task_success_rate": m.get("task_success_rate", 0.0),
                "repeat_error_rate": m.get("repeat_error_rate", 0.0),
                "conflict_rate": m.get("conflict_rate", 0.0),
                "contamination_rate": m.get("contamination_rate", 0.0),
                "avg_latency_ms": m.get("avg_latency_ms", 0.0),
                "avg_token_cost": m.get("avg_token_cost", 0.0),
            }
        )

    # Focus comparison on case_01 variants (baseline vs guarded)
    base = next((r for r in rows if r["variant"] == "baseline_permissive"), None)
    guard = next((r for r in rows if r["variant"] == "guarded_selective_disclosure"), None)

    lines = [
        "# v0.1 Benchmark Snapshot (Reproducible)",
        "",
        "Generated from scenario simulation outputs. No fabricated numbers.",
        "",
        "## Reproduce",
        "```bash",
        "PYTHONPATH=src python3 examples/simulation_runner.py --json-output docs/benchmarks/latest-results.json",
        "python3 scripts/generate_benchmark_snapshot.py",
        "```",
        "",
        "## Variant Metrics",
        "| Scenario | Variant | Passed | success | repeat_error | conflict | contamination | latency_ms | token_cost |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for r in rows:
        lines.append(
            f"| {r['scenario']} | {r['variant']} | {str(r['passed']).lower()} | "
            f"{r['task_success_rate']:.2f} | {r['repeat_error_rate']:.2f} | "
            f"{r['conflict_rate']:.2f} | {r['contamination_rate']:.2f} | "
            f"{r['avg_latency_ms']:.2f} | {r['avg_token_cost']:.2f} |"
        )

    if base and guard:
        lines += [
            "",
            "## Key Delta (guarded vs baseline)",
            f"- task_success_rate: {guard['task_success_rate'] - base['task_success_rate']:+.2f}",
            f"- repeat_error_rate: {guard['repeat_error_rate'] - base['repeat_error_rate']:+.2f}",
            f"- conflict_rate: {guard['conflict_rate'] - base['conflict_rate']:+.2f}",
            f"- contamination_rate: {guard['contamination_rate'] - base['contamination_rate']:+.2f}",
            f"- avg_latency_ms: {guard['avg_latency_ms'] - base['avg_latency_ms']:+.2f}",
            f"- avg_token_cost: {guard['avg_token_cost'] - base['avg_token_cost']:+.2f}",
        ]

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
