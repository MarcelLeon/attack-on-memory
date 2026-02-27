"""Validate scenario specs before simulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attack_on_memory.scenarios.spec_validation import validate_scenario_spec


def _iter_scenario_files(paths: list[str], scenarios_dir: str) -> list[Path]:
    if paths:
        return [Path(path).resolve() for path in paths]
    return sorted(
        path
        for path in Path(scenarios_dir).resolve().glob("*.json")
        if not path.name.endswith(".schema.json")
    )


def _validate_with_jsonschema(spec: dict, schema: dict) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema package is not installed; skip --jsonschema-check or install it"]

    validator = Draft202012Validator(schema)
    issues = []
    for error in validator.iter_errors(spec):
        location = ".".join(str(item) for item in error.absolute_path)
        location = location or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Attack on Memory scenario specs")
    parser.add_argument("scenarios", nargs="*", help="Optional scenario files")
    parser.add_argument(
        "--scenarios-dir",
        default=str(Path(__file__).resolve().parent / "scenarios"),
        help="Directory with scenario files when no positional files are provided",
    )
    parser.add_argument(
        "--jsonschema-check",
        action="store_true",
        help="Also validate against scenario.schema.json using jsonschema package",
    )
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).resolve().parent / "scenarios" / "scenario.schema.json"),
        help="Path to JSON schema file used with --jsonschema-check",
    )
    args = parser.parse_args(argv)

    scenario_files = _iter_scenario_files(args.scenarios, args.scenarios_dir)
    if not scenario_files:
        print("No scenario files found.")
        return 1

    schema = None
    if args.jsonschema_check:
        schema = json.loads(Path(args.schema).resolve().read_text(encoding="utf-8"))

    total_errors = 0
    for path in scenario_files:
        spec = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_scenario_spec(spec)
        if schema is not None:
            errors.extend(_validate_with_jsonschema(spec, schema))

        if errors:
            total_errors += len(errors)
            print(f"[FAIL] {path}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"[PASS] {path}")

    print(f"\nValidation finished with {total_errors} error(s)")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
