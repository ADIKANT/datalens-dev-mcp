#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "behavior-trace-case.schema.json").read_text(encoding="utf-8"))
PRIVATE_PATTERNS = {
    "absolute_user_path": re.compile(r"/Users/|[A-Za-z]:\\\\Users\\\\"),
    "credential": re.compile(r"(?i)(authorization\s*:|bearer\s+[A-Za-z0-9]|iam[_-]?token\s*=)"),
    "raw_private_url": re.compile(r"https?://(?!datalens\.example(?:/|\b))[^\s\"]+", re.I),
}


def validate(root: Path) -> dict[str, Any]:
    validator = Draft202012Validator(SCHEMA)
    issues: list[dict[str, str]] = []
    cases: list[dict[str, Any]] = []
    for path in sorted((root / "cases").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for name, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(text):
                issues.append({"case": path.name, "rule": name})
        try:
            case = json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append({"case": path.name, "rule": f"invalid_json_line_{exc.lineno}"})
            continue
        issues.extend(
            {"case": path.name, "rule": "schema", "detail": error.message[:180]}
            for error in validator.iter_errors(case)
        )
        cases.append(case)
    families = {str(case.get("expected_plan", {}).get("family") or "") for case in cases}
    if len(cases) < 80:
        issues.append({"case": "corpus", "rule": "case_count_below_80"})
    if len(families) < 30:
        issues.append({"case": "corpus", "rule": "family_count_below_30"})
    if len({case.get("case_id") for case in cases}) != len(cases):
        issues.append({"case": "corpus", "rule": "duplicate_case_id"})
    if any(case.get("expected_questions") not in {0, 1} for case in cases):
        issues.append({"case": "corpus", "rule": "question_budget"})
    if any(case.get("call_budget", 99) > 12 for case in cases):
        issues.append({"case": "corpus", "rule": "public_call_budget"})
    report_path = root / "corpus-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    if report.get("case_count") != len(cases) or report.get("family_count") != len(families):
        issues.append({"case": "corpus-report.json", "rule": "aggregate_count_mismatch"})
    if "source_path" in report or "source_sha256" in report:
        issues.append({"case": "corpus-report.json", "rule": "private_source_provenance_leak"})
    return {
        "ok": not issues,
        "schema_id": "behavior_trace_validation_report",
        "case_count": len(cases),
        "family_count": len(families),
        "executable_case_count": len(cases),
        "private_literal_leakage": sum(item["rule"] in PRIVATE_PATTERNS for item in issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate sanitized executable public behavior traces.")
    parser.add_argument("corpus", nargs="?", type=Path, default=Path("tests/regression/behavior_traces"))
    args = parser.parse_args()
    report = validate(args.corpus.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
