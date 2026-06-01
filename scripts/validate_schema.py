#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from jsonschema import Draft202012Validator
except Exception as exc:  # pragma: no cover - dependency guard for local runs
    raise SystemExit("jsonschema is required. Install with: python3 -m pip install jsonschema") from exc


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "manse-output.schema.json"
SAMPLE_OUTPUT = ROOT / "examples" / "sample-output.json"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_calculator(args: List[str]) -> Dict[str, Any]:
    cp = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "calculate_manse.py"), *args, "--format", "json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if not cp.stdout.strip():
        raise RuntimeError(f"calculator produced no JSON for {args}: {cp.stderr}")
    return json.loads(cp.stdout)


def validate_case(name: str, data: Dict[str, Any], validator: Draft202012Validator) -> None:
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    if errors:
        lines = [f"{name}: schema validation failed"]
        for error in errors[:20]:
            path = ".".join(str(part) for part in error.path) or "$"
            lines.append(f"- {path}: {error.message}")
        raise AssertionError("\n".join(lines))


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    cases = {
        "examples/sample-output.json": load_json(SAMPLE_OUTPUT),
        "solar_ok": run_calculator(["--date", "1990-01-01", "--time", "23:30"]),
        "solar_unknown_time": run_calculator(["--date", "2015-08-15", "--time", "unknown"]),
        "lunar_regular_ok": run_calculator(["--calendar", "lunar", "--date", "2001-08-14", "--lunar-leap", "false", "--time", "12:00"]),
        "lunar_leap_ok": run_calculator(["--calendar", "lunar", "--date", "2020-04-01", "--lunar-leap", "true", "--time", "12:00"]),
        "lunar_ambiguous_error": run_calculator(["--calendar", "lunar", "--date", "2020-04-01", "--lunar-leap", "auto", "--time", "12:00"]),
        "year_out_of_range_error": run_calculator(["--date", "2031-01-01", "--time", "10:00"]),
    }
    for name, data in cases.items():
        validate_case(name, data, validator)
    print(f"schema ok ({len(cases)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
