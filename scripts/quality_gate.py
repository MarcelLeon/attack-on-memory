#!/usr/bin/env python3
"""Lightweight local quality gate for contributors and CI parity."""

from __future__ import annotations

import os
import subprocess
import sys


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    env = dict(os.environ)
    src = str((__file__))
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(src)))
    env["PYTHONPATH"] = os.path.join(repo_root, "src")
    subprocess.run(cmd, check=True, env=env, cwd=repo_root)


def main() -> int:
    python = sys.executable
    run([python, "scripts/project_status.py", "--check"])
    run([python, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([python, "examples/validate_scenarios.py"])
    run([python, "scripts/policy_check.py"])
    run([python, "scripts/north_star_report.py"])
    run([python, "scripts/run_replay_benchmark.py", "--check"])
    run([python, "scripts/check_runtime_qualification.py"])
    print("\n✅ quality-gate passed", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n❌ quality-gate failed: {exc}")
        raise SystemExit(exc.returncode)
