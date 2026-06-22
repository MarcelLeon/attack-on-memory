#!/usr/bin/env python3
"""Run scenario demos and print the Attack on Memory north-star report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from attack_on_memory.evals.north_star import build_north_star_snapshot  # noqa: E402
from attack_on_memory.evals.replay_benchmark import (  # noqa: E402
    load_replay_benchmark,
    run_replay_benchmark,
)
from attack_on_memory.scenarios.spec_validation import ensure_valid_scenario_spec  # noqa: E402
from simulation_runner import VariantResult, run_scenario  # noqa: E402

SCENARIO_DIR = ROOT / "examples" / "scenarios"
REPLAY_DATASET = ROOT / "examples" / "replays" / "privacy_safe_incidents.json"


def _scenario_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(
        item
        for item in path.glob("*.json")
        if not item.name.endswith(".schema.json")
    )


def _load_results(path: Path) -> list[VariantResult]:
    results: list[VariantResult] = []
    for scenario_path in _scenario_files(path):
        spec = json.loads(scenario_path.read_text(encoding="utf-8"))
        ensure_valid_scenario_spec(spec)
        results.extend(run_scenario(spec))
    return results


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _print_report(results: list[VariantResult], replay_path: Path) -> None:
    snapshot = build_north_star_snapshot(results)
    replay = run_replay_benchmark(load_replay_benchmark(replay_path))
    governed_context_acceptance = replay["treatment"]["context_acceptance_rate"]

    print("Attack on Memory north-star report")
    print("=" * 36)
    print("Problem: agent memory is easy to retrieve, but hard to trust.")
    print("North star: governed context acceptance rate.")
    print(
        "A labeled replay context passes only when required memories are present, "
        "forbidden memories are absent, and no contradiction is exposed."
    )
    print()
    print(f"Governed context acceptance: {_pct(governed_context_acceptance)}")
    print("Evidence scope: synthetic checked-in replay; production validation pending.")
    print(
        "Governed safe projection proxy (unlabeled scenarios): "
        f"{_pct(snapshot.governed_safe_projection_rate)}"
    )
    print(f"Governed context pass rate:  {_pct(snapshot.governed_context_pass_rate)}")
    print(f"Scenario pass rate:           {_pct(snapshot.scenario_pass_rate)}")
    print(f"Average task success rate:    {_pct(snapshot.avg_task_success_rate)}")
    print()
    print("Memory governance counters")
    print(f"- retrieved candidates: {snapshot.retrieved_memories}")
    print(f"- projected memories:   {snapshot.projected_memories}")
    print(f"- redacted memories:    {snapshot.redacted_memories} ({_pct(snapshot.redaction_rate)})")
    print(f"- inherited memories:   {snapshot.inherited_memories} ({_pct(snapshot.inheritance_rate)})")
    print(f"- conflict flags:       {snapshot.contradiction_flags} ({_pct(snapshot.contradiction_rate)})")
    print()
    print("Scenario proof points")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"- {status} {result.scenario_id}::{result.variant_id}")
        for event in result.event_results:
            diagnostics = event.diagnostics
            print(
                "  "
                f"{event.event_id}: projected={diagnostics.get('projected', 0)} "
                f"redacted={diagnostics.get('redacted', 0)} "
                f"inherited={diagnostics.get('inherited', 0)} "
                f"conflicts={diagnostics.get('contradictions', 0)}"
            )
    print()
    print("Differentiation")
    print("- Vector memory answers what looks similar.")
    print("- Agent runtime memory answers what the agent can keep using.")
    print("- Attack on Memory answers what this role may trust in this branch right now.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the north-star scenario report")
    parser.add_argument(
        "--scenarios",
        default=str(SCENARIO_DIR),
        help="Scenario JSON file or directory. Defaults to examples/scenarios.",
    )
    parser.add_argument(
        "--replay",
        default=str(REPLAY_DATASET),
        help="Labeled replay benchmark used for the north-star metric.",
    )
    args = parser.parse_args(argv)

    results = _load_results(Path(args.scenarios).resolve())
    if not results:
        print("No scenario results produced.")
        return 1

    _print_report(results, Path(args.replay).resolve())
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
