#!/usr/bin/env python3
"""Lint every checked-in scenario policy before it reaches simulation/runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attack_on_memory.domain.models import Sensitivity  # noqa: E402
from attack_on_memory.governance.analysis import lint_policy_set  # noqa: E402
from attack_on_memory.governance.policies import DisclosurePolicy  # noqa: E402

SCENARIO_DIR = ROOT / "examples" / "scenarios"


def _policy(raw: dict) -> DisclosurePolicy:
    return DisclosurePolicy(
        role=raw["role"],
        policy_id=raw.get("policy_id", "default-disclosure"),
        version=int(raw.get("version", 1)),
        max_sensitivity=Sensitivity(raw.get("max_sensitivity", "internal")),
        allowed_domains=frozenset(raw.get("allowed_domains", ())),
        allowed_tasks=frozenset(raw.get("allowed_tasks", ())),
        allowed_purposes=frozenset(raw.get("allowed_purposes", ())),
        require_explicit_purpose=bool(raw.get("require_explicit_purpose", False)),
        min_confidence=float(raw.get("min_confidence", 0.0)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint scenario disclosure policies")
    parser.add_argument("--scenarios", default=str(SCENARIO_DIR))
    parser.add_argument("--strict", action="store_true", help="Fail on warnings too")
    args = parser.parse_args(argv)

    root = Path(args.scenarios)
    paths = [root] if root.is_file() else sorted(root.glob("case_*.json"))
    errors = 0
    warnings = 0
    for path in paths:
        spec = json.loads(path.read_text(encoding="utf-8"))
        for variant in spec.get("variants", []):
            findings = lint_policy_set(_policy(item) for item in variant.get("policies", []))
            for finding in findings:
                label = f"{path.name}::{variant['variant_id']}"
                print(
                    f"[{finding.severity.upper()}] {label} "
                    f"{finding.policy_id}@{finding.policy_version} "
                    f"{finding.code}: {finding.message}"
                )
                if finding.severity == "error":
                    errors += 1
                else:
                    warnings += 1
    print(f"Policy lint finished: {errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
