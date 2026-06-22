#!/usr/bin/env python3
"""Print and validate the project's goal-to-delivery ledger."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attack_on_memory.evals.project_state import (  # noqa: E402
    load_project_state,
    render_project_status,
    validate_project_state,
)

DEFAULT_STATE = ROOT / "docs" / "project-state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the live project delivery ledger")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    state = load_project_state(Path(args.state))
    failures = validate_project_state(state, ROOT)
    if failures:
        print("Project state is invalid:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    if not args.check:
        print(render_project_status(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
