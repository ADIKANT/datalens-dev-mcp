#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


FAMILIES = (
    "review-current-dashboard",
    "diagnose-target-not-found",
    "plan-only-exact-reference",
    "update-existing-dashboard",
    "update-editor-chart-exact-js-style",
    "update-wizard-without-migration",
    "create-new-object",
    "save-only",
    "save-and-publish",
    "publish-only-from-saved",
    "explicit-no-browser",
    "explicit-browser-required",
    "optional-browser-unavailable",
    "missing-target-discoverable",
    "ambiguous-workbook-entries",
    "one-true-business-question",
    "stale-target-revision",
    "stale-style-binding",
    "protected-runtime-mismatch",
    "semantic-no-op",
    "multi-object-batch",
    "partial-save",
    "partial-publish",
    "save-timeout-ambiguous",
    "publish-timeout-ambiguous",
    "auth-401-probe-refresh",
    "permission-403-no-refresh",
    "rate-limit-429-condition-wait",
    "get-dataset-data-fallback",
    "unexpected-empty-data",
    "process-restart-after-save",
    "source-build-drift-on-resume",
    "corrupted-event-tail-recovery",
    "plan-hash-mismatch",
    "destructive-token-rejection",
    "user-correction-narrows-scope",
    "no-ql-fallback",
    "exact-technology-preservation",
    "selector-date-semantics",
    "repeated-unchanged-poll-dedup",
)

BLOCKED_FAMILIES = {
    "review-current-dashboard",
    "diagnose-target-not-found",
    "explicit-browser-required",
    "missing-target-discoverable",
    "stale-target-revision",
    "stale-style-binding",
    "protected-runtime-mismatch",
    "semantic-no-op",
    "partial-save",
    "partial-publish",
    "save-timeout-ambiguous",
    "publish-timeout-ambiguous",
    "auth-401-probe-refresh",
    "permission-403-no-refresh",
    "rate-limit-429-condition-wait",
    "unexpected-empty-data",
    "source-build-drift-on-resume",
    "plan-hash-mismatch",
    "destructive-token-rejection",
    "one-true-business-question",
    "get-dataset-data-fallback",
    "publish-only-from-saved",
    "create-new-object",
}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _provider_state(family: str, variant: int) -> dict[str, Any]:
    state: dict[str, Any] = {"dataset_behavior": "normal"}
    if family in {"diagnose-target-not-found", "missing-target-discoverable"}:
        state["missing_dashboard"] = True
    elif family == "ambiguous-workbook-entries":
        state["ambiguous_inventory"] = True
    elif family == "semantic-no-op":
        state["initial_label"] = "Revenue"
    elif family == "unexpected-empty-data":
        state["dataset_behavior"] = "empty"
    elif family == "get-dataset-data-fallback":
        state["dataset_behavior"] = "unavailable"
    elif family == "stale-target-revision":
        state["stale_chart_after_reads"] = 1
    elif family in {"auth-401-probe-refresh", "permission-403-no-refresh", "rate-limit-429-condition-wait"}:
        state["failure_kind"] = {
            "auth-401-probe-refresh": "401",
            "permission-403-no-refresh": "403",
            "rate-limit-429-condition-wait": "429",
        }[family]
        state["fail_read_method"] = "getDashboard"
    elif family == "partial-save":
        state["second_chart"] = True
        state["fail_write_number"] = 2
        state["write_failure_kind"] = "timeout"
    elif family == "save-timeout-ambiguous":
        state["fail_write_number"] = 1
        state["write_failure_kind"] = "timeout"
    elif family == "partial-publish":
        state["second_chart"] = True
        state["fail_write_number"] = 4
        state["write_failure_kind"] = "timeout"
    elif family == "publish-timeout-ambiguous":
        state["fail_write_number"] = 2
        state["write_failure_kind"] = "timeout"
    elif family == "multi-object-batch":
        state["second_chart"] = True
    state["variant"] = variant
    return state


def _driver(family: str) -> str:
    return {
        "process-restart-after-save": "restart_after_save",
        "corrupted-event-tail-recovery": "corrupt_tail_then_resume",
        "source-build-drift-on-resume": "source_drift_then_resume",
        "plan-hash-mismatch": "tamper_plan_then_execute",
        "stale-style-binding": "tamper_style_binding_then_execute",
        "protected-runtime-mismatch": "mutate_chart_then_execute",
        "repeated-unchanged-poll-dedup": "repeat_status",
    }.get(family, "direct")


def build_case(family: str, variant: int, *, source_hash: str) -> dict[str, Any]:
    terminal = "BLOCKED" if family in BLOCKED_FAMILIES else "COMPLETED"
    publish = family not in {
        "save-only",
        "plan-only-exact-reference",
        "review-current-dashboard",
        "diagnose-target-not-found",
    }
    request = (
        "Update dashboard https://datalens.example/dash_demo while preserving unmentioned content; "
        f"replay the sanitized {family.replace('-', ' ')} behavior"
    )
    if publish:
        request += ", then save and publish"
    else:
        request += ", then save without publish"
    if family == "explicit-no-browser":
        request += " without browser"
    if family == "explicit-browser-required":
        request += " and verify it in the browser"
    if family == "destructive-token-rejection":
        request = "Delete legacy content from https://datalens.example/dash_demo and publish the result"
    if family == "create-new-object":
        request = "Create a new chart in https://datalens.example/dash_demo, then save and publish it"
    if family == "diagnose-target-not-found":
        request = "Diagnose why dashboard https://datalens.example/dash_demo cannot be found without changing it"
    if family == "plan-only-exact-reference":
        request = "Plan only: update dashboard https://datalens.example/dash_demo using its exact current style"
    if family == "publish-only-from-saved":
        request = "Publish only from saved state for dashboard https://datalens.example/dash_demo"
    if family == "permission-403-no-refresh":
        request = "Update https://datalens.example/dash_demo, preserve unmentioned content, then save and publish"
    if family == "one-true-business-question":
        request = "Update the requested business dashboard while preserving all unmentioned content"
    if family == "review-current-dashboard":
        request = "Review the current DataLens dashboard and verify it without browser"
    semantic_changes = [
        {"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"}
    ]
    if family in {"multi-object-batch", "partial-save", "partial-publish"}:
        semantic_changes.append(
            {"target_id": "chart_demo_2", "slot_id": "series_label", "value": "Margin"}
        )
    context = {
        "driver": _driver(family),
        "semantic_changes": semantic_changes,
        "variant": variant,
    }
    expected_calls = ["getDashboard"]
    if family in {"one-true-business-question", "review-current-dashboard"}:
        expected_calls = []
    if family == "destructive-token-rejection":
        expected_calls = []
    if (
        family not in {
            "one-true-business-question",
            "destructive-token-rejection",
            "review-current-dashboard",
        }
        and not _provider_state(family, variant).get("missing_dashboard")
        and not _provider_state(family, variant).get("fail_read_method")
    ):
        expected_calls.extend(["getWorkbookEntries", "getEditorChart", "getDataset"])
    if terminal == "COMPLETED" and family != "plan-only-exact-reference":
        expected_calls.extend(["getDatasetData", "updateEditorChart"])
    if family == "plan-only-exact-reference":
        expected_calls.append("getDatasetData")
    if family == "get-dataset-data-fallback":
        expected_calls.extend(["getDatasetData", "updateEditorChart"])
    case = {
        "case_id": f"{family}-{variant:02d}",
        "source_family": "sanitized-session-derived",
        "request": request,
        "context": context,
        "mock_provider_state": _provider_state(family, variant),
        "expected_contract": {
            "operation": (
                "create"
                if family in {"create-new-object", "destructive-token-rejection"}
                else "review"
                if family == "review-current-dashboard"
                else "diagnose"
                if family == "diagnose-target-not-found"
                else "plan"
                if family == "plan-only-exact-reference"
                else "publish_only"
                if family == "publish-only-from-saved"
                else "update"
            ),
            "publish": publish,
            "browser_policy": (
                "required"
                if family == "explicit-browser-required"
                else "forbidden"
                if family in {"explicit-no-browser", "review-current-dashboard"}
                else "optional"
            ),
        },
        "expected_discovery": {
            "status": (
                "absent"
                if family in {
                    "review-current-dashboard",
                    "one-true-business-question",
                    "destructive-token-rejection",
                    "diagnose-target-not-found",
                    "missing-target-discoverable",
                    "auth-401-probe-refresh",
                    "permission-403-no-refresh",
                    "rate-limit-429-condition-wait",
                }
                else "bound"
            ),
            "root_id": "dash_demo",
            "dataset_id": "dataset_demo",
        },
        "expected_plan": {
            "technology": "editor_advanced",
            "ql_fallback": False,
            "family": family,
            "target_count": (
                2 if family in {"multi-object-batch", "partial-save", "partial-publish"} else 1
            ),
        },
        "expected_transitions": ["RESOLVED -> BASELINE_READ"] if terminal == "COMPLETED" else [],
        "expected_provider_calls": sorted(set(expected_calls)),
        "forbidden_provider_calls": ["deleteDashboard", "updateDataset", "updateConnection"],
        "expected_questions": (
            1
            if family in {
                "one-true-business-question",
                "destructive-token-rejection",
                "review-current-dashboard",
            }
            else 0
        ),
        "expected_browser_calls": 0,
        "expected_terminal_state": terminal,
        "expected_proof": {
            "highest": "publish_readback"
            if terminal == "COMPLETED" and publish
            else "contract_runtime"
            if family == "plan-only-exact-reference"
            else "save_readback"
            if terminal == "COMPLETED"
            else "source_static"
        },
        "call_budget": 10 if "restart" in _driver(family) or "resume" in _driver(family) else 7,
        "source_signal_hash": _hash({"aggregate_source": source_hash, "family": family}),
    }
    return case


def build(output: Path, *, source_hash: str, source_count: int) -> dict[str, Any]:
    cases_dir = output / "cases"
    if cases_dir.exists():
        shutil.rmtree(cases_dir)
    cases_dir.mkdir(parents=True, exist_ok=True)
    cases = [build_case(family, variant, source_hash=source_hash) for family in FAMILIES for variant in (1, 2)]
    for case in cases:
        (cases_dir / f"{case['case_id']}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    report = {
        "schema_id": "behavior_trace_corpus_report",
        "case_count": len(cases),
        "family_count": len(FAMILIES),
        "source_session_count": source_count,
        "source_family": "sanitized-session-derived",
        "human_review": "plan_author_reviewed_family_set",
        "private_literal_leakage": 0,
        "corpus_sha256": _hash(cases),
    }
    (output / "corpus-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build sanitized executable public autonomy behavior traces.")
    parser.add_argument("--source-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("tests/regression/behavior_traces"))
    args = parser.parse_args()
    receipt = json.loads(args.source_receipt.read_text(encoding="utf-8"))
    report = build(
        args.output.resolve(),
        source_hash=str(receipt["source_sha256"]),
        source_count=int(receipt["session_count"]),
    )
    print(json.dumps({"ok": True, **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
