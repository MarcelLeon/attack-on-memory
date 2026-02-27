"""CLI: convert OpenClaw replay logs into scenario spec JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attack_on_memory.scenarios.replay_converter import (
    build_scenario_from_replay,
    load_memory_catalog,
    load_replay_records,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert OpenClaw replay logs to scenario spec")
    parser.add_argument("--replay", required=True, help="Replay log file (JSON/JSONL)")
    parser.add_argument("--output", required=True, help="Output scenario JSON path")
    parser.add_argument("--scenario-id", required=True, help="Scenario id")
    parser.add_argument("--title", default="OpenClaw Replay Scenario", help="Scenario title")
    parser.add_argument(
        "--description",
        default="Imported from OpenClaw replay logs.",
        help="Scenario description",
    )
    parser.add_argument("--variant-id", default="replay_import", help="Variant id")
    parser.add_argument(
        "--memory-catalog",
        default="",
        help="Optional memory catalog JSON for enriching imported memory placeholders",
    )
    parser.add_argument(
        "--assert-from-context",
        action="store_true",
        help="Use replay projected memory ids to auto-generate strict must_include assertions",
    )
    args = parser.parse_args(argv)

    records = load_replay_records(args.replay)
    catalog = load_memory_catalog(args.memory_catalog) if args.memory_catalog else None
    scenario = build_scenario_from_replay(
        records,
        scenario_id=args.scenario_id,
        title=args.title,
        description=args.description,
        variant_id=args.variant_id,
        memory_catalog=catalog,
        assert_from_context=args.assert_from_context,
    )

    output_path = Path(args.output).resolve()
    output_path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    print(f"Scenario spec written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
