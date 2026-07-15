from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.methods import list_methods
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.proof_levels import with_proof_level
from datalens_dev_mcp.pipeline.safe_apply import readback_artifact_path


def build_validation_evidence_report(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    static_sql = _artifact(
        root,
        "artifacts/editor_sql_lint.json",
        default={
            "ok": False,
            "issues": [
                {
                    "severity": "error",
                    "rule": "missing_static_sql_lint_artifact",
                    "message": "artifacts/editor_sql_lint.json is missing.",
                }
            ],
            "checked_paths": [],
        },
    )
    dashboard_preflight = _artifact(
        root,
        "artifacts/dashboard_payload_preflight.json",
        default={
            "ok": False,
            "issues": [
                {
                    "severity": "error",
                    "rule": "missing_dashboard_payload_preflight_artifact",
                    "message": "artifacts/dashboard_payload_preflight.json is missing.",
                }
            ],
            "checked_paths": [],
        },
    )
    validation = _artifact(root, "artifacts/validation_report.json", default={"status": "not_run", "issues": []})
    safe_apply_plan = _artifact(root, "artifacts/safe_apply_plan.json", default={"ok": False, "actions": []})
    safe_apply_result = _artifact(root, "artifacts/safe_apply_result.json", default={"executed": False, "blocked_reasons": []})
    source_availability = _artifact(root, "artifacts/source_availability_matrix.json", default={"status": "not_run", "sources": {}})
    chart_validation = _artifact(root, "artifacts/dashboard_chart_validation.json", default={"status": "not_run", "charts": []})
    source_budget = _artifact(root, "artifacts/source_performance_budget.json", default={"status": "not_run", "sources": []})
    active_graph = _artifact(root, "artifacts/active_dashboard_graph.json", default={"status": "not_run", "entries": []})
    browser_qa = _artifact(root, "artifacts/browser_qa.json", default={"status": "not_checked", "artifact_paths": []})
    evidence_mode = _artifact(root, "artifacts/evidence_mode_decision.json", default={"evidence_mode": "api_only"})
    workflow_summary = _first_existing_json(
        root,
        [
            "artifacts/project_live_summary.json",
            "reports/datalens_dry_run_summary.json",
            "reports/datalens_apply_summary.json",
        ],
    )
    saved_readback = _artifact(root, str(readback_artifact_path(".", "dashboard", "saved")), default={"status": "not_run"})
    direct_sql = _direct_sql_execution_status()
    engine_probe = _engine_probe_status(root)
    failing_rules = (
        _failing_rules(static_sql)
        + _failing_rules(dashboard_preflight)
        + _coverage_failures(static_sql, checked_key="checked_paths", rule="zero_static_sql_lint_coverage")
        + _coverage_failures(
            dashboard_preflight,
            checked_key="checked_paths",
            rule="zero_dashboard_payload_preflight_coverage",
        )
    )
    ok = not failing_rules and validation.get("status") != "fail"
    confidence = _confidence_level(ok=ok, direct_sql=direct_sql, saved_readback=saved_readback, workflow_summary=workflow_summary)
    proof_levels = _evidence_levels(
        static_sql=static_sql,
        engine_probe=engine_probe,
        saved_readback=saved_readback,
        workflow_summary=workflow_summary,
        browser_qa=browser_qa,
        root=root,
    )
    report = {
        "schema_version": "2026-06-05.validation_evidence.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ok": ok,
        "ok_proof_context": {
            "proof_levels": proof_levels,
            "highest_proof_level": proof_levels[-1] if proof_levels else "source_static",
        },
        "project_root": str(root),
        "static_js_syntax": {"status": "covered_by_check_js_templates", "proof_level": "installed_static"},
        "static_sql_lint": with_proof_level(static_sql, "source_static"),
        "dashboard_payload_preflight": with_proof_level(dashboard_preflight, "source_static"),
        "safe_apply_plan": _safe_apply_summary(safe_apply_plan),
        "evidence_mode_decision": evidence_mode,
        "source_availability_matrix": _source_availability_summary(source_availability),
        "active_dashboard_graph": _active_graph_summary(active_graph),
        "dashboard_chart_validation": _chart_validation_summary(chart_validation),
        "source_performance_budget": _source_budget_summary(source_budget),
        "browser_runtime_qa": _browser_qa_summary(browser_qa),
        "dry_run_summary": _dry_run_summary(workflow_summary),
        "saved_readback": _readback_summary(saved_readback, branch="saved"),
        "published_readback": _published_readback(root, workflow_summary),
        "editor_object_readback": _editor_readback_summary(saved_readback),
        "dashboard_layout_readback": _dashboard_layout_summary(saved_readback),
        "direct_sql_execution": direct_sql,
        "engine_probe": engine_probe,
        "proof_levels": proof_levels,
        "evidence_levels": proof_levels,
        "blocked_reason": "" if ok else "validation evidence contains blocking static/preflight errors",
        "confidence_level": confidence,
        "fallback_evidence": [
            "static_sql_lint",
            "generated query inspection",
            "save/publish acceptance where present",
            "published object readback where present",
        ],
        "remaining_manual_checks": [
            "manual UI smoke for runtime ClickHouse query execution when direct SQL API remains unavailable",
            "manual verification of dashboard interactions that depend on production-only selector state",
        ],
        "failing_rules": failing_rules,
        "safe_apply_result": {
            "executed": bool(safe_apply_result.get("executed")),
            "proof_level": "controlled_live_write" if safe_apply_result.get("executed") else "source_static",
            "blocked_reasons": safe_apply_result.get("blocked_reasons") or [],
        },
    }
    write_json(root / "artifacts" / "validation_evidence_report.json", report)
    return report


def _artifact(root: Path, rel: str, *, default: dict[str, Any]) -> dict[str, Any]:
    value = read_json(root / rel, default=default)
    return value if isinstance(value, dict) else default


def _first_existing_json(root: Path, rels: list[str]) -> dict[str, Any]:
    for rel in rels:
        path = root / rel
        if path.is_file():
            payload = read_json(path, default={})
            if isinstance(payload, dict):
                return {"path": str(path), **payload}
    return {"status": "not_run"}


def _direct_sql_execution_status() -> dict[str, Any]:
    candidates = []
    for method in list_methods(include_guarded_writes=False):
        lowered = f"{method.name} {method.description}".lower()
        if "sql" in lowered and ("query" in lowered or "execute" in lowered or "run" in lowered):
            candidates.append({"method": method.name, "mode": method.mode, "description": method.description})
    if not candidates:
        return {
            "status": "blocked_runtime_sql_execution",
            "proof_level": "source_static",
            "validated_api_method": "",
            "checked_catalog": "config/datalens_api_methods.json",
            "recommended_fallback": [
                "static SQL lint",
                "generated query inspection",
                "save/publish acceptance",
                "published object readback",
                "optional manual UI smoke",
            ],
        }
    return {
        "status": "available_method_requires_explicit_tool_design",
        "proof_level": "installed_static",
        "validated_api_method": candidates[0]["method"],
        "candidates": candidates,
        "recommended_fallback": ["Do not execute until the method contract is designed and tested."],
    }


def _engine_probe_status(root: Path) -> dict[str, Any]:
    evidence_dir = root / "reports" / "data_evidence"
    artifacts = sorted(evidence_dir.glob("*.json")) if evidence_dir.is_dir() else []
    schema_artifacts: list[str] = []
    stage_artifacts: list[str] = []
    blocked_artifacts: list[str] = []
    for artifact in artifacts:
        payload = read_json(artifact, default={})
        evidence = payload.get("evidence") if isinstance(payload, dict) else {}
        if not isinstance(evidence, dict):
            continue
        status = str(payload.get("status") or evidence.get("status") or "")
        operation = str(evidence.get("probe_operation") or evidence.get("evidence_level") or "")
        if status == "PROBE_BLOCKED":
            blocked_artifacts.append(str(artifact))
        if operation in {"table_discovery", "column_list", "bounded_row_count", "bounded_sample", "source_freshness_availability"}:
            schema_artifacts.append(str(artifact))
        if operation == "cte_stage_count":
            stage_artifacts.append(str(artifact))
    if schema_artifacts or stage_artifacts:
        return {
            "status": "ENGINE_PROBE_RECORDED",
            "proof_level": "live_read_only_api",
            "schema_probe_artifacts": schema_artifacts,
            "stage_probe_artifacts": stage_artifacts,
            "blocked_artifacts": blocked_artifacts,
        }
    return {
        "status": "BLOCKED_ENGINE_PROBE",
        "proof_level": "source_static",
        "reason": "No recorded read-only engine schema or stage probe artifact is available.",
        "next_steps": [
            "Use dl_build_data_evidence_probe_plan to prepare bounded probes.",
            "Run probes through an approved read-only metadata/data evidence provider.",
            "Record sanitized results with dl_record_data_evidence.",
        ],
    }


def _evidence_levels(
    *,
    static_sql: dict[str, Any],
    engine_probe: dict[str, Any],
    saved_readback: dict[str, Any],
    workflow_summary: dict[str, Any],
    browser_qa: dict[str, Any],
    root: Path,
) -> list[str]:
    levels = ["source_static", "installed_static"]
    if engine_probe.get("schema_probe_artifacts"):
        levels.append("live_read_only_api")
    if engine_probe.get("stage_probe_artifacts"):
        levels.append("live_read_only_api")
    if saved_readback.get("live_readback") or workflow_summary.get("saved"):
        levels.append("save_readback")
    if workflow_summary.get("published") or (root / "artifacts" / "readback" / "dashboard.published.latest.json").is_file():
        levels.append("publish_readback")
    if browser_qa.get("status") in {"browser_pass", "browser_fail"} and browser_qa.get("artifact_paths"):
        levels.append("browser_rendered")
    elif (root / "artifacts" / "visual-qa").exists() or (root / "artifacts" / "visual_qa").exists():
        levels.append("browser_rendered")
    if not static_sql.get("ok", True):
        levels.append("source_static")
    return list(dict.fromkeys(levels))


def _failing_rules(payload: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    for issue in payload.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if issue.get("severity", "error") == "error":
            rules.append(str(issue.get("rule") or issue.get("message") or "unknown"))
    for result in payload.get("results") or []:
        if isinstance(result, dict):
            rules.extend(_failing_rules(result))
    return rules


def _coverage_failures(payload: dict[str, Any], *, checked_key: str, rule: str) -> list[str]:
    checked = payload.get(checked_key)
    if isinstance(checked, list) and checked:
        return []
    if isinstance(checked, int) and checked > 0:
        return []
    return [rule]


def _confidence_level(
    *,
    ok: bool,
    direct_sql: dict[str, Any],
    saved_readback: dict[str, Any],
    workflow_summary: dict[str, Any],
) -> str:
    if not ok:
        return "blocked"
    if direct_sql.get("status") != "blocked_runtime_sql_execution":
        return "direct_sql_method_unverified"
    if saved_readback.get("live_readback") or workflow_summary.get("published") or workflow_summary.get("saved"):
        return "medium_static_with_readback"
    return "medium_static_only"


def _safe_apply_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(plan.get("ok")),
        "proof_level": "source_static",
        "approved": bool(plan.get("approved")),
        "action_count": len(plan.get("actions") or []),
        "default_mode": plan.get("default_mode") or "save",
    }


def _source_availability_summary(payload: dict[str, Any]) -> dict[str, Any]:
    sources = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
    return {
        "status": "recorded" if sources else payload.get("status", "not_run"),
        "proof_level": "live_read_only_api" if payload.get("generated_from") else "source_static",
        "schema_version": payload.get("schema_version") or "",
        "project": payload.get("project") or "",
        "source_count": len(sources),
        "generated_from": payload.get("generated_from") or "",
    }


def _active_graph_summary(payload: dict[str, Any]) -> dict[str, Any]:
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    return {
        "status": "recorded" if entries else payload.get("status", "not_run"),
        "proof_level": "live_read_only_api" if entries else "source_static",
        "schema_version": payload.get("schema_version") or "",
        "entry_count": len(entries),
        "blocked_reasons": payload.get("blocked_reasons") or [],
    }


def _chart_validation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "status": "recorded" if payload.get("charts") else payload.get("status", "not_run"),
        "proof_level": "live_read_only_api" if payload.get("charts") else "source_static",
        "schema_version": payload.get("schema_version") or "",
        "chart_count": summary.get("chart_count", len(payload.get("charts") or [])),
        "failed_chart_count": summary.get("failed_chart_count", 0),
        "browser_checked_count": summary.get("browser_checked_count", 0),
        "browser_auth_required_count": summary.get("browser_auth_required_count", 0),
    }


def _source_budget_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    return {
        "status": "recorded" if sources else payload.get("status", "not_run"),
        "proof_level": "live_read_only_api" if sources else "source_static",
        "schema_version": payload.get("schema_version") or "",
        "source_count": summary.get("source_count", len(sources)),
        "failed_source_count": summary.get("failed_source_count", 0),
        "unknown_source_count": summary.get("unknown_source_count", 0),
    }


def _browser_qa_summary(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "not_checked")
    artifact_paths = payload.get("artifact_paths") if isinstance(payload.get("artifact_paths"), list) else []
    return {
        "status": status,
        "proof_level": "browser_rendered" if status in {"browser_pass", "browser_fail"} and artifact_paths else "source_static",
        "browser_verified": bool(status == "browser_pass" and artifact_paths),
        "artifact_paths": artifact_paths,
        "blocked_reasons": payload.get("blocked_reasons") or ([] if status == "browser_pass" else [status]),
    }


def _dry_run_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("status") == "not_run":
        return {"status": "not_run", "proof_level": "source_static"}
    return {
        "status": summary.get("status") or "summary_read",
        "proof_level": "source_static",
        "path": summary.get("path") or summary.get("summary_path") or "",
        "workbook_id": summary.get("workbook_id") or "",
        "dashboard_id": summary.get("dashboard_id") or "",
        "changed_object_counts": summary.get("changed_object_counts") or {},
        "evidence_paths": summary.get("evidence_paths") or [],
        "remaining_drift": summary.get("remaining_drift") or [],
    }


def _readback_summary(readback: dict[str, Any], *, branch: str) -> dict[str, Any]:
    live = bool(readback.get("live_readback"))
    if branch == "published" and live:
        proof_level = "publish_readback"
    elif branch == "saved" and live:
        proof_level = "save_readback"
    else:
        proof_level = "source_static"
    return {
        "status": readback.get("status") or ("read" if readback.get("live_readback") else "not_run"),
        "proof_level": proof_level,
        "branch": readback.get("branch") or branch,
        "live_readback": bool(readback.get("live_readback")),
        "mode": readback.get("mode") or "",
    }


def _published_readback(root: Path, workflow_summary: dict[str, Any]) -> dict[str, Any]:
    published_path = root / "artifacts" / "readback" / "dashboard.published.latest.json"
    if published_path.is_file():
        return _readback_summary(read_json(published_path, default={}), branch="published")
    return {
        "status": "published" if workflow_summary.get("published") else "not_run",
        "proof_level": "publish_readback" if workflow_summary.get("published") else "source_static",
        "branch": "published",
    }


def _editor_readback_summary(readback: dict[str, Any]) -> dict[str, Any]:
    charts = readback.get("charts") or []
    return {
        "status": "read" if charts else "not_run",
        "proof_level": "save_readback" if charts else "source_static",
        "chart_count": len(charts) if isinstance(charts, list) else 0,
        "checked_tabs": ["sources", "prepare", "config"],
    }


def _dashboard_layout_summary(readback: dict[str, Any]) -> dict[str, Any]:
    dashboard = readback.get("dashboard") if isinstance(readback.get("dashboard"), dict) else {}
    return {
        "status": "read" if dashboard else "not_run",
        "proof_level": "save_readback" if dashboard else "source_static",
        "dashboard_keys": sorted(dashboard.keys()) if dashboard else [],
        "checks": [
            "block title",
            "widget tabs",
            "chart ids",
            "default tab",
            "native title/hint",
            "selector defaults",
            "source availability defaults",
        ],
    }
