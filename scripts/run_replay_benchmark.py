#!/usr/bin/env python3
"""Generate or verify the checked-in paired replay benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attack_on_memory.evals.replay_benchmark import (  # noqa: E402
    load_replay_benchmark,
    render_replay_report,
    run_replay_benchmark,
)

DATASET = ROOT / "examples" / "replays" / "privacy_safe_incidents.json"
RESULTS = ROOT / "docs" / "benchmarks" / "replay-v0.2-results.json"
REPORT = ROOT / "docs" / "benchmarks" / "replay-v0.2-report.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run paired replay benchmark")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--results", default=str(RESULTS))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    result = run_replay_benchmark(load_replay_benchmark(Path(args.dataset)))
    result_text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    report_text = render_replay_report(result)
    outputs = ((Path(args.results), result_text), (Path(args.report), report_text))

    if args.check:
        stale = [path for path, content in outputs if not path.exists() or path.read_text(encoding="utf-8") != content]
        if stale:
            print("Replay benchmark artifacts are stale:")
            for path in stale:
                print(f"- {path}")
            return 1
        print("Replay benchmark artifacts are reproducible and current.")
        return 0

    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
