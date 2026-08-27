#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "src/datalens_dev_mcp/assets/schemas/session-regression-case.schema.json").read_text())
REQUIRED_SCENARIOS = {
    "no_browser_explicit", "browser_required_explicit", "exact_reference_style", "extend_current_js_format",
    "no_technology_change", "no_ql_fallback", "opaque_sticky_header", "no_phantom_legend_statuses",
    "indicator_visible_partial_data", "expected_empty_state", "business_readable_columns",
    "no_redundant_technical_columns", "hints_lineage_na_reasons", "correct_pagination",
    "display_formatting_preserves_raw_semantics", "auth_401_minimal_probe", "permission_403",
    "revision_conflict", "rate_limit_429_cooldown", "network_timeout", "transient_5xx",
    "tool_capability_unavailable", "truncated_heavy_output", "ambiguous_write", "no_progress_loop",
    "long_task_checkpoint", "new_session_resume", "partial_save", "partial_publish", "stale_style_binding",
    "stale_patch_anchor",
}
PRIVATE_PATTERNS = {
    "absolute_user_path": re.compile(r"/Users/|[A-Za-z]:\\\\Users\\\\"),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    "raw_sql": re.compile(r"\b(select|insert|update|delete)\s+.+\b(from|into|set)\b", re.I | re.S),
    "credential": re.compile(r"(?i)(authorization\s*:|bearer\s+[A-Za-z0-9]|iam[_-]?token\s*=)"),
}


def validate_corpus(root: Path) -> dict[str, Any]:
    validator = Draft202012Validator(SCHEMA)
    issues: list[dict[str, str]] = []
    cases: list[dict[str, Any]] = []
    for path in sorted((root / "cases").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for rule, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(text):
                issues.append({"case": path.name, "rule": rule})
        try:
            case = json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append({"case": path.name, "rule": f"invalid_json_line_{exc.lineno}"})
            continue
        for error in validator.iter_errors(case):
            issues.append({"case": path.name, "rule": "schema", "detail": error.message[:180]})
        cases.append(case)
    scenarios = {str(case.get("scenario")) for case in cases}
    missing = sorted(REQUIRED_SCENARIOS - scenarios)
    if len(cases) < 80:
        issues.append({"case": "corpus", "rule": "scenario_count_below_80"})
    if missing:
        issues.append({"case": "corpus", "rule": "missing_required_scenarios", "detail": ",".join(missing)})
    no_browser = [case for case in cases if case.get("scenario") == "no_browser_explicit"]
    if any(case.get("expected_calls", {}).get("browser") != 0 for case in no_browser):
        issues.append({"case": "corpus", "rule": "no_browser_call_budget"})
    exact_style = [case for case in cases if case.get("scenario") == "exact_reference_style"]
    if any("protected_runtime_hash_unchanged" not in case.get("expected_invariants", []) for case in exact_style):
        issues.append({"case": "corpus", "rule": "exact_style_protected_hash"})
    category_coverage: dict[str, int] = {}
    for case in cases:
        category = str(case.get("category") or "unknown")
        category_coverage[category] = category_coverage.get(category, 0) + 1
    report = {
        "ok": not issues,
        "schema_id": "autonomy_policy_matrix_validation_report",
        "scenario_count": len(cases),
        "category_coverage": dict(sorted(category_coverage.items())),
        "expected_question_count": sum(int(case.get("expected_calls", {}).get("questions", 0)) for case in cases),
        "expected_browser_call_count": sum(int(case.get("expected_calls", {}).get("browser", 0)) for case in cases),
        "expected_high_level_call_budget": sum(
            int(case.get("expected_calls", {}).get("high_level_budget", 0)) for case in cases
        ),
        "private_literal_leakage": sum(issue.get("rule") in PRIVATE_PATTERNS for issue in issues),
        "issues": issues,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the static sanitized autonomy policy matrix.")
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    report = validate_corpus(args.corpus.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
