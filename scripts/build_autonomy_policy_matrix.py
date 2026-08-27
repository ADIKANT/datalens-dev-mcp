#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from typing import Any, Iterable


SCENARIOS: dict[str, tuple[str, ...]] = {
    "intent_autonomy": (
        "api_mcp_only", "no_unnecessary_questions", "end_to_end_completion", "no_browser_explicit",
        "browser_required_explicit", "publish_full_set_only", "save_only", "no_dependency_version_changes",
    ),
    "scope_reference": (
        "preserve_ids", "preserve_object_set", "preserve_layout", "preserve_dataset_connection",
        "exact_reference_style", "extend_current_js_format", "no_technology_change", "no_ql_fallback",
    ),
    "visual": (
        "period_selector_first", "exact_selector_rows_order_heights", "selector_block_not_too_tall",
        "light_dark_support", "opaque_sticky_header", "no_phantom_legend_statuses",
        "indicator_visible_partial_data", "expected_empty_state", "business_readable_columns",
        "no_redundant_technical_columns", "hints_lineage_na_reasons", "correct_pagination",
        "display_formatting_preserves_raw_semantics", "responsive_layout", "bounded_widget_density",
        "selector_cross_filter_preserved",
    ),
    "provider_failure": (
        "auth_401_minimal_probe", "permission_403", "revision_conflict", "rate_limit_429_cooldown",
        "network_timeout", "transient_5xx", "tool_capability_unavailable", "truncated_heavy_output",
        "ambiguous_write", "no_progress_loop",
    ),
    "resume": (
        "long_task_checkpoint", "new_session_resume", "partial_save", "partial_publish",
        "stale_style_binding", "stale_patch_anchor",
    ),
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "intent_autonomy": ("mcp", "api", "browser", "publish", "save", "автоном", "без вопрос"),
    "scope_reference": ("preserve", "reference", "layout", "dataset", "connection", "style", "сохран"),
    "visual": ("selector", "legend", "header", "pagination", "empty", "column", "визу", "селектор"),
    "provider_failure": ("401", "403", "429", "timeout", "conflict", "error", "ошиб", "retry"),
    "resume": ("resume", "checkpoint", "partial", "stale", "продолж", "сесс"),
}

FAILURE_FAMILY = {
    "auth_401_minimal_probe": "AUTH_401_TOKEN_INVALID_OR_EXPIRED",
    "permission_403": "AUTH_403_PERMISSION_DENIED",
    "revision_conflict": "REVISION_CONFLICT",
    "rate_limit_429_cooldown": "RATE_LIMIT_429",
    "network_timeout": "NETWORK_TIMEOUT",
    "transient_5xx": "TRANSIENT_5XX",
    "tool_capability_unavailable": "TOOL_OR_CAPABILITY_UNAVAILABLE",
    "ambiguous_write": "AMBIGUOUS_WRITE",
    "no_progress_loop": "NO_PROGRESS",
    "stale_style_binding": "STYLE_BINDING_STALE",
    "stale_patch_anchor": "PATCH_ANCHOR_STALE",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_documents(path: Path) -> tuple[list[tuple[str, str]], str]:
    documents: list[tuple[str, str]] = []
    digest = hashlib.sha256()
    if path.is_file() and zipfile.is_zipfile(path):
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith((".md", ".json", ".jsonl")) and Path(name).name != "MANIFEST.json":
                    with archive.open(name) as handle:
                        text = handle.read(1_500_000).decode("utf-8", errors="ignore")
                    documents.append((f"source-{len(documents) + 1:04d}", text))
        return documents, digest.hexdigest()
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if not item.is_file() or item.suffix.lower() not in {".md", ".json", ".jsonl"}:
                continue
            raw = item.read_bytes()
            digest.update(raw)
            documents.append((f"source-{len(documents) + 1:04d}", raw[:1_500_000].decode("utf-8", errors="ignore")))
        return documents, digest.hexdigest()
    raise FileNotFoundError(f"offline source is not a ZIP archive or directory: {path}")


def observed_category_counts(documents: Iterable[tuple[str, str]]) -> dict[str, int]:
    counts = {category: 0 for category in SCENARIOS}
    for _, text in documents:
        lowered = text.lower()
        for category, keywords in KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                counts[category] += 1
    return counts


def synthetic_case(category: str, scenario: str, variant: int) -> dict[str, Any]:
    route = "editor_advanced" if scenario in {
        "exact_reference_style", "extend_current_js_format", "no_technology_change", "no_ql_fallback"
    } else "wizard_native"
    browser_calls = 1 if scenario == "browser_required_explicit" else 0
    writes = "save_only" if scenario == "save_only" else "save_then_publish"
    if category == "provider_failure" or scenario in {"long_task_checkpoint", "new_session_resume"}:
        writes = "conditional_after_recovery"
    invariants = ["target_identity_preserved", "unknown_fields_preserved", "save_readback_before_publish"]
    if scenario in {"exact_reference_style", "extend_current_js_format", "no_technology_change"}:
        invariants.extend(["protected_runtime_hash_unchanged", "technology_unchanged"])
    if scenario == "no_ql_fallback":
        invariants.append("ql_route_forbidden")
    if scenario == "preserve_layout":
        invariants.append("layout_unchanged")
    if scenario == "preserve_object_set":
        invariants.append("object_set_unchanged")
    calls = {
        "questions": 0,
        "browser": browser_calls,
        "writes": writes,
        "high_level_budget": 12 if variant == 1 else 16,
    }
    context = {
        "target": {"workbook_id": "synthetic_workbook", "dashboard_id": "synthetic_dashboard"},
        "saved_revision": f"synthetic_revision_{variant}",
        "constraints": [scenario, "preserve_unmentioned_content"],
    }
    expected_task_contract = {
        "intent": "update_existing_dashboard",
        "delivery": {"save": True, "publish": writes == "save_then_publish"},
        "route_policy": {"selected": route, "ql_allowed": False},
        "browser_policy": "required" if browser_calls else "forbidden" if scenario == "no_browser_explicit" else "optional",
    }
    result = {
        "case_id": f"{scenario.replace('_', '-')}-{variant:03d}",
        "category": category,
        "scenario": scenario,
        "request": f"Apply the synthetic {scenario.replace('_', ' ')} correction and complete the authorized delivery flow.",
        "context": context,
        "expected_task_contract": expected_task_contract,
        "expected_route": route,
        "expected_calls": calls,
        "expected_invariants": sorted(set(invariants)),
        "visual_checks": [scenario] if category == "visual" else [],
        "expected_failure_family": FAILURE_FAMILY.get(scenario, ""),
        "expected_recovery": recovery_for(scenario),
    }
    result["contract_sha256"] = sha256_bytes(stable_json(result).encode())
    return result


def recovery_for(scenario: str) -> str:
    return {
        "auth_401_minimal_probe": "probe_then_single_refresh_safe_read_only",
        "permission_403": "fail_without_refresh",
        "revision_conflict": "fresh_read_and_replan",
        "rate_limit_429_cooldown": "shared_cooldown_then_bounded_read_retry",
        "network_timeout": "retry_safe_read_or_reconcile_write",
        "transient_5xx": "bounded_safe_read_retry",
        "tool_capability_unavailable": "report_capability_gap",
        "truncated_heavy_output": "read_hash_bound_artifact",
        "ambiguous_write": "readback_reconciliation_no_replay",
        "no_progress_loop": "architecture_review_after_three_attempts",
        "partial_save": "resume_from_saved_readback",
        "partial_publish": "resume_from_published_readback",
        "stale_style_binding": "refresh_style_binding_and_replan",
        "stale_patch_anchor": "fresh_read_and_reanchor",
    }.get(scenario, "continue_deterministic_workflow")


def build_policy_matrix(source: Path, output: Path, receipt: Path) -> dict[str, Any]:
    documents, source_hash = source_documents(source)
    if not documents:
        raise ValueError("session source contains no readable session documents")
    output.mkdir(parents=True, exist_ok=True)
    cases_dir = output / "cases"
    if cases_dir.exists():
        shutil.rmtree(cases_dir)
    cases_dir.mkdir(parents=True)
    cases = [
        synthetic_case(category, scenario, variant)
        for category, scenarios in SCENARIOS.items()
        for scenario in scenarios
        for variant in (1, 2)
    ]
    for case in cases:
        (cases_dir / f"{case['case_id']}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    category_coverage = {category: sum(case["category"] == category for case in cases) for category in SCENARIOS}
    report = {
        "schema_id": "autonomy_policy_matrix_report",
        "source_session_count": len(documents),
        "scenario_count": len(cases),
        "category_coverage": category_coverage,
        "observed_source_category_counts": observed_category_counts(documents),
        "expected_question_count": sum(case["expected_calls"]["questions"] for case in cases),
        "expected_browser_call_count": sum(case["expected_calls"]["browser"] for case in cases),
        "expected_high_level_call_budget": sum(case["expected_calls"]["high_level_budget"] for case in cases),
        "private_literal_leakage": 0,
        "invariant_count": sum(len(case["expected_invariants"]) for case in cases),
        "case_set_sha256": sha256_bytes(stable_json(cases).encode()),
    }
    (output / "corpus-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "schema_id": "local_autonomy_policy_matrix_source_receipt",
                "source_sha256": source_hash,
                "session_count": len(documents),
                "corpus_sha256": report["case_set_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static autonomy policy matrix from an offline source.")
    parser.add_argument("--source", "--sessions", dest="source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("artifacts/autonomy_policy_matrix/source-receipt.json"),
    )
    args = parser.parse_args()
    report = build_policy_matrix(args.source.resolve(), args.output.resolve(), args.receipt.resolve())
    print(json.dumps({"ok": True, **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
