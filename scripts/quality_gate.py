#!/usr/bin/env python3
"""Lightweight local quality gate for contributors and CI parity."""

from __future__ import annotations

import os
import subprocess


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    env = dict(os.environ)
    src = str((__file__))
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(src)))
    env["PYTHONPATH"] = os.path.join(repo_root, "src")
    subprocess.run(cmd, check=True, env=env, cwd=repo_root)


def main() -> int:
    run(["python3", "-m", "unittest", "discover", "-s", "tests", "-v"])
    run(["python3", "examples/validate_scenarios.py"])
    print("\n✅ quality-gate passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n❌ quality-gate failed: {exc}")
        raise SystemExit(exc.returncode)
