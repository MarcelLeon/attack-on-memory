#!/usr/bin/env python3
"""Validate the checked-in runtime qualification evidence artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from attack_on_memory.evals.runtime_qualification import (
    validate_runtime_qualification_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "benchmarks" / "runtime-development-v0.1.json"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REPORT
    if len(sys.argv) > 2:
        raise ValueError("usage: check_runtime_qualification.py [report.json]")
    report = json.loads(path.read_text(encoding="utf-8"))
    validate_runtime_qualification_report(report)
    print(
        f"Runtime qualification artifact valid: {report['profile_id']} "
        f"({report['claim_scope']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
