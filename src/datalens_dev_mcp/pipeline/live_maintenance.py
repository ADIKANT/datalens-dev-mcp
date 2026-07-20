from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request
from datalens_dev_mcp.serialization import serialized_metadata
from datalens_dev_mcp.pipeline.artifacts import ensure_project_dirs, write_json
from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract
from datalens_dev_mcp.pipeline.performance_budget import normalize_editor_source_budget_evidence_v7
from datalens_dev_mcp.pipeline.runtime_gate import (
    build_browser_runtime_smoke,
    build_runtime_gate_evidence,
    final_status_from_runtime_gate,
    runtime_first_status_from_runtime_gate,
    runtime_gate_has_blocking_markers,
    verify_local_artifacts,
)
from datalens_dev_mcp.pipeline.safe_apply import (
    create_safe_apply_plan,
    safe_apply_run_binding,
    safe_apply_run_id,
    validate_safe_apply_plan_exhaustive,
)
from datalens_dev_mcp.pipeline.source_availability import validate_source_availability_consumers


LIVE_MAINTENANCE_SCHEMA_VERSION = "datalens.delta_v7.live_maintenance_run.v1"
FINAL_HANDOFF_SCHEMA_VERSION = "datalens.delta_v7.final_maintenance_handoff.v1"
RUNTIME_FIRST_RUN_SCHEMA_VERSION = "datalens.delta_v8.runtime_first_run.v1"

MAINTENANCE_MODES = {
    "quick_visible_patch",
    "dataset_sql_patch",
    "source_availability_patch",
    "full_audit",
}


def run_live_maintenance_update(
    *,
    project_root: str = ".",
    workbook_id: str = "",
    dashboard_id: str = "",
    target_tab_id: str = "",
    target_object_ids: list[str] | None = None,
    intent: str = "fix_existing",
    maintenance_mode: str = "quick_visible_patch",
    approved: bool = False,
    publish: bool = True,
    browser_runtime_required: bool = True,
    non_rendering_exemption: str = "",
    baseline_snapshot_path: str = "",
    metadata_evidence_paths: list[str] | None = None,
    source_availability_artifact: str = "",
    changed_objects: list[dict[str, Any]] | None = None,
    allow_create: bool = False,
    create_necessity_proof: dict[str, Any] | None = None,
    cleanup_mode: str = "plan_only",
    safe_apply_actions: list[dict[str, Any]] | None = None,
    guarded_requests: list[dict[str, Any]] | None = None,
    baseline_dashboard: dict[str, Any] | None = None,
    proposed_dashboard: dict[str, Any] | None = None,
    source_budget_evidence: dict[str, Any] | list[dict[str, Any]] | None = None,
    runtime_gate_evidence: dict[str, Any] | None = None,
    saved_runtime_gate_evidence: dict[str, Any] | None = None,
    published_runtime_gate_evidence: dict[str, Any] | None = None,
    safe_apply_execution_evidence: dict[str, Any] | None = None,
    saved_readback_evidence: dict[str, Any] | None = None,
    publish_from_saved_evidence: dict[str, Any] | None = None,
    published_readback_evidence: dict[str, Any] | None = None,
    target_url: str = "",
) -> dict[str, Any]:
    started = monotonic()
    root = ensure_project_dirs(project_root)
    run_id = _run_id()
    phases: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    if runtime_gate_evidence is not None:
        warnings.append(
            "runtime_gate_evidence is deprecated; interpreted as published_runtime_gate_evidence"
        )
    mode = _normalize_maintenance_mode(maintenance_mode, intent=intent)
    rendering_scope = _resolve_rendering_scope(
        root,
        runtime_gate_evidence=(
            published_runtime_gate_evidence
            or saved_runtime_gate_evidence
            or runtime_gate_evidence
        ),
        target_url=target_url,
        target_tab_id=target_tab_id,
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
    )
    target_url = rendering_scope["target_url"]
    target_tab_id = rendering_scope["target_tab_id"]
    blockers.extend(rendering_scope["blocked_reasons"])
    target = {
        "workbook_id": workbook_id,
        "dashboard_id": dashboard_id,
        "target_tab_id": target_tab_id,
        "tab_id": target_tab_id,
        "target_object_ids": [str(item) for item in target_object_ids or [] if str(item)],
        "object_ids": [str(item) for item in target_object_ids or [] if str(item)],
    }
    action_object_ids = list(
        dict.fromkeys(
            [str(item) for item in target.get("target_object_ids") or [] if str(item)]
            + [
                str(item.get("object_id") or item.get("id") or "")
                for item in changed_objects or []
                if isinstance(item, dict) and (item.get("object_id") or item.get("id"))
            ]
            + [
                _action_target_object_id(item)
                for item in safe_apply_actions or []
                if isinstance(item, dict) and _action_target_object_id(item)
            ]
        )
    )
    if not action_object_ids and dashboard_id:
        action_object_ids = [dashboard_id]
    browser_scope_object_ids = list(
        dict.fromkeys([*action_object_ids, *([dashboard_id] if dashboard_id else [])])
    )
    expected_runtime_titles = _expected_runtime_titles(
        changed_objects=changed_objects or [],
        proposed_dashboard=proposed_dashboard or {},
        safe_apply_actions=safe_apply_actions or [],
        required_object_ids=action_object_ids,
        target_tab_id=target_tab_id,
    )

    if not workbook_id:
        blockers.append("missing_target_workbook_id")
    if publish and not (dashboard_id or target.get("target_object_ids")):
        blockers.append("missing_target_object_ids_for_live_publish")
    exemption_issue = _non_rendering_exemption_issue(
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
        dashboard_id=dashboard_id,
        target_object_ids=target.get("target_object_ids") or [],
    )
    if exemption_issue:
        blockers.append(exemption_issue)
        non_rendering_exemption = ""
    phases.append(_phase("target_resolution", "blocked" if blockers else "passed"))

    baseline_result = _baseline_phase(
        dashboard_id=dashboard_id,
        workbook_id=workbook_id,
        baseline_snapshot_path=baseline_snapshot_path,
        baseline_dashboard=baseline_dashboard,
        proposed_dashboard=proposed_dashboard,
        changed_objects=changed_objects or [],
        allow_create=allow_create,
        create_necessity_proof=create_necessity_proof or {},
    )
    phases.append(baseline_result["phase"])
    blockers.extend(baseline_result["blocked_reasons"])

    request_phase = _guarded_request_phase(guarded_requests or [], workbook_id=workbook_id)
    phases.append(request_phase["phase"])
    blockers.extend(request_phase["blocked_reasons"])

    source_phase = _source_availability_phase(source_availability_artifact, strict_publish_gate=publish)
    phases.append(source_phase["phase"])
    blockers.extend(source_phase["blocked_reasons"])

    budget_phase = _source_budget_phase(source_budget_evidence)
    phases.append(budget_phase["phase"])
    blockers.extend(budget_phase["blocked_reasons"])

    publish_action_blockers = _publish_action_scope_issues(safe_apply_actions or [], publish=publish)
    blockers.extend(publish_action_blockers)
    safe_apply_phase = _safe_apply_phase(
        root,
        safe_apply_actions or [],
        approved=approved,
        baseline_dashboard=baseline_result.get("baseline_dashboard") or {},
        dashboard_id=dashboard_id,
        workbook_id=workbook_id,
        changed_objects=changed_objects or [],
        baseline_snapshot_path=baseline_snapshot_path,
    )
    phases.append(safe_apply_phase["phase"])
    blockers.extend(safe_apply_phase["blocked_reasons"])

    completion_evidence = _completion_evidence_phase(
        root,
        approved=approved,
        publish=publish,
        safe_apply_actions=safe_apply_actions or [],
        safe_apply_execution_evidence=safe_apply_execution_evidence,
        saved_readback_evidence=saved_readback_evidence,
        publish_from_saved_evidence=publish_from_saved_evidence,
        published_readback_evidence=published_readback_evidence,
        safe_apply_plan=safe_apply_phase.get("plan") or {},
        required_object_ids=action_object_ids,
    )
    phases.append(completion_evidence["phase"])
    blockers.extend(completion_evidence["blocked_reasons"])

    blockers_before_runtime = list(blockers)
    saved_runtime_input = saved_runtime_gate_evidence
    published_runtime_input = published_runtime_gate_evidence
    if runtime_gate_evidence and not published_runtime_input:
        published_runtime_input = runtime_gate_evidence
    saved_runtime_gate = _runtime_gate_phase(
        root,
        run_id=run_id,
        phase_name="saved_runtime_gate",
        delivery_stage="saved_runtime",
        runtime_gate_evidence=saved_runtime_input,
        target_url=target_url,
        target_tab_id=target_tab_id,
        required_object_ids=browser_scope_object_ids,
        required_branch="saved",
        required_object_revisions=(completion_evidence.get("saved_readback") or {}).get("object_revisions") or {},
        expected_titles=expected_runtime_titles,
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
    )
    phases.append(saved_runtime_gate["phase"])
    if (
        runtime_gate_has_blocking_markers(saved_runtime_gate["evidence"])
        or saved_runtime_gate["evidence"].get("status") == "failed"
    ):
        blockers.append("saved_runtime_gate_failed")
        blockers.append("runtime_gate_failed")

    visible_change = bool(
        browser_runtime_required and not str(non_rendering_exemption or "").strip()
    )
    saved_runtime_passed = bool(
        saved_runtime_gate["evidence"].get("status") == "passed"
        or (not browser_runtime_required and str(non_rendering_exemption or "").strip())
    )
    publish_allowed = bool(
        (completion_evidence.get("saved_readback") or {}).get("verified")
        and (
            not visible_change
            or (
                saved_runtime_passed
                and not runtime_gate_has_blocking_markers(saved_runtime_gate["evidence"])
            )
        )
    )
    publish_evidence_supplied = bool(
        (completion_evidence.get("publish_from_saved") or {}).get("supplied")
        or (completion_evidence.get("published_readback") or {}).get("supplied")
    )
    if publish_evidence_supplied and not publish_allowed:
        blockers.append("publish_attempted_without_saved_runtime_gate")

    published_runtime_gate = _runtime_gate_phase(
        root,
        run_id=run_id,
        phase_name="published_runtime_gate",
        delivery_stage="published_runtime",
        runtime_gate_evidence=published_runtime_input,
        target_url=target_url,
        target_tab_id=target_tab_id,
        required_object_ids=browser_scope_object_ids,
        required_branch="published",
        required_object_revisions=(completion_evidence.get("published_readback") or {}).get("object_revisions") or {},
        expected_titles=expected_runtime_titles,
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
    )
    phases.append(published_runtime_gate["phase"])
    if (publish or runtime_gate_evidence is not None) and (
        runtime_gate_has_blocking_markers(published_runtime_gate["evidence"])
        or published_runtime_gate["evidence"].get("status") == "failed"
    ):
        blockers.append("published_runtime_gate_failed")
        blockers.append("runtime_gate_failed")

    runtime_gate = (
        published_runtime_gate
        if publish or runtime_gate_evidence is not None
        else saved_runtime_gate
    )
    runtime_gates = {
        "saved": saved_runtime_gate["evidence"],
        "published": published_runtime_gate["evidence"],
    }
    delivery_stage = _delivery_stage(
        completion_evidence=completion_evidence,
        saved_runtime_gate=saved_runtime_gate["evidence"],
        published_runtime_gate=published_runtime_gate["evidence"],
        publish_allowed=publish_allowed,
    )

    cleanup_plan = _cleanup_plan(
        changed_objects=changed_objects or [],
        cleanup_mode=cleanup_mode,
        safe_apply_blocked=bool(safe_apply_phase["blocked_reasons"]),
    )
    phases.append(_phase("cleanup", cleanup_plan["status"], cleanup_plan.get("artifact_paths", [])))
    blockers.extend(cleanup_plan.get("blocked_reasons") or [])

    final_status = _final_status(
        blockers=blockers,
        approved=approved,
        runtime_gate=runtime_gate["evidence"],
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
        completion_ready=bool(completion_evidence["completion_ready"]),
    )
    runtime_first_status = _runtime_first_status(
        blockers_before_runtime=blockers_before_runtime,
        approved=approved,
        runtime_gate=runtime_gate["evidence"],
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
        completion_ready=bool(completion_evidence["completion_ready"]),
    )
    validation_budget = _validation_budget(
        mode=mode,
        publish=publish,
        elapsed_seconds=monotonic() - started,
    )
    runtime_first_run = {
        "schema_version": RUNTIME_FIRST_RUN_SCHEMA_VERSION,
        "target": target,
        "mode": mode,
        "status": runtime_first_status,
        "validation_budget": validation_budget,
        "runtime_smoke": runtime_gate["runtime_smoke"],
        "artifact_paths": [
            path
            for path in [
                saved_runtime_gate.get("artifact_path", ""),
                published_runtime_gate.get("artifact_path", ""),
                cleanup_plan.get("artifact_path", ""),
            ]
            if path
        ],
    }
    runtime_first_path = root / "artifacts" / "live_maintenance" / f"{run_id}.runtime_first.json"
    write_json(runtime_first_path, runtime_first_run)
    handoff = _handoff(
        status=final_status,
        runtime_first_status=runtime_first_status,
        validation_budget=validation_budget,
        runtime_smoke=runtime_gate["runtime_smoke"],
        target=target,
        changed_objects=changed_objects or [],
        runtime_gate_path=runtime_gate.get("artifact_path", ""),
        metadata_evidence_paths=metadata_evidence_paths or [],
        cleanup_report_path=cleanup_plan.get("artifact_path", ""),
        completion_evidence=completion_evidence,
        limitations=_limitations(
            final_status,
            blockers,
            browser_runtime_required,
            non_rendering_exemption,
            completion_evidence=completion_evidence,
        ),
    )
    handoff_path = root / "artifacts" / "live_maintenance" / f"{run_id}.handoff.json"
    write_json(handoff_path, handoff)
    phases.append(_phase("handoff", final_status, [str(handoff_path)]))

    run = {
        "schema_version": LIVE_MAINTENANCE_SCHEMA_VERSION,
        "run_id": run_id,
        "target": target,
        "intent": intent,
        "maintenance_mode": mode,
        "status": final_status,
        "runtime_first_status": runtime_first_status,
        "validation_budget": validation_budget,
        "runtime_first_run": runtime_first_run,
        "approved": approved,
        "execution_performed": False,
        "tool_role": "plan_and_validate_supplied_evidence",
        "publish_requested": bool(publish),
        "publish_allowed": publish_allowed,
        "delivery_stage": delivery_stage,
        "warnings": warnings,
        "phases": phases,
        "blocked_reasons": blockers,
        "runtime_gate": runtime_gate["evidence"],
        "runtime_gates": runtime_gates,
        "runtime_smoke": runtime_gate["runtime_smoke"],
        "completion_evidence": completion_evidence,
        "cleanup_plan": cleanup_plan,
        "handoff": handoff,
        "metadata_evidence_paths": [str(path) for path in metadata_evidence_paths or [] if str(path)],
    }
    run_path = root / "artifacts" / "live_maintenance" / f"{run_id}.json"
    write_json(run_path, run)
    return {
        "ok": final_status not in {"blocked", "rolled_back"},
        "schema_version": LIVE_MAINTENANCE_SCHEMA_VERSION,
        "run_id": run_id,
        "status": final_status,
        "execution_performed": False,
        "tool_role": "plan_and_validate_supplied_evidence",
        "execution_note": (
            "This tool does not call DataLens writes or a browser; it validates supplied evidence "
            "and writes local artifacts."
        ),
        "runtime_first_status": runtime_first_status,
        "validation_budget": validation_budget,
        "runtime_first_run_path": str(runtime_first_path),
        "target": target,
        "phase_statuses": [{"name": item["name"], "status": item["status"]} for item in phases],
        "blocked_reasons": blockers,
        "warnings": warnings,
        "artifact_path": str(run_path),
        "handoff_path": str(handoff_path),
        "runtime_gate_status": runtime_gate["evidence"]["status"],
        "saved_runtime_gate_status": saved_runtime_gate["evidence"]["status"],
        "published_runtime_gate_status": published_runtime_gate["evidence"]["status"],
        "publish_allowed": publish_allowed,
        "delivery_stage": delivery_stage,
        "browser_runtime_smoke_status": runtime_gate["runtime_smoke"]["status"],
        "completion_evidence_status": completion_evidence["phase"]["status"],
        "cleanup_status": cleanup_plan["status"],
    }


def _baseline_phase(
    *,
    dashboard_id: str,
    workbook_id: str,
    baseline_snapshot_path: str,
    baseline_dashboard: dict[str, Any] | None,
    proposed_dashboard: dict[str, Any] | None,
    changed_objects: list[dict[str, Any]],
    allow_create: bool,
    create_necessity_proof: dict[str, Any],
) -> dict[str, Any]:
    blocked: list[str] = []
    artifacts: list[str] = []
    contract: dict[str, Any] = {}
    baseline = baseline_dashboard or _read_json_if_file(baseline_snapshot_path)
    if baseline_snapshot_path:
        artifacts.append(baseline_snapshot_path)
    if dashboard_id and changed_objects and not baseline:
        blocked.append("baseline_required_for_dashboard_maintenance")
    if baseline and proposed_dashboard:
        contract = build_baseline_diff_contract(
            dashboard_id=dashboard_id,
            workbook_id=workbook_id,
            baseline_source={"kind": "snapshot", "path": baseline_snapshot_path},
            baseline_dashboard=baseline,
            proposed_dashboard=proposed_dashboard,
            changed_objects=changed_objects,
        )
        blocked.extend(str(reason) for reason in contract.get("blocked_reasons") or [])
    for item in changed_objects:
        change_type = str(item.get("change_type") or item.get("action") or "").lower()
        if change_type in {"create", "append"} and not allow_create:
            blocked.append("create_or_append_requires_allow_create")
        if change_type == "create" and not _create_proof_sufficient(create_necessity_proof or item):
            blocked.append("create_requires_necessity_proof")
        if change_type in {"remove", "replace", "delete"} and not item.get("explicit_user_intent"):
            blocked.append("object_removal_or_replacement_requires_explicit_user_intent")
    return {
        "phase": _phase("baseline_preservation", "blocked" if blocked else "passed", artifacts),
        "blocked_reasons": blocked,
        "baseline_dashboard": baseline,
        "baseline_diff_contract": contract,
    }


def _guarded_request_phase(requests: list[dict[str, Any]], *, workbook_id: str) -> dict[str, Any]:
    blocked: list[str] = []
    compiled: list[dict[str, Any]] = []
    for item in requests:
        result = compile_guarded_rpc_request(
            str(item.get("method") or ""),
            item.get("payload") if isinstance(item.get("payload"), dict) else item,
            object_type=str(item.get("object_type") or ""),
            object_id=str(item.get("object_id") or ""),
            workbook_id=str(item.get("workbook_id") or workbook_id or ""),
            mode=str(item.get("mode") or "save"),
            base_revision=str(item.get("base_revision") or ""),
            changed_sections=[str(section) for section in item.get("changed_sections") or []],
        )
        compiled.append(result)
        blocked.extend(str(reason) for reason in result.get("blocked_reasons") or [])
    return {
        "phase": _phase(
            "guarded_request_compile",
            "blocked" if blocked else "passed" if compiled else "not_applicable",
        ),
        "blocked_reasons": blocked,
        "compiled_requests": compiled,
    }


def _source_availability_phase(source_availability_artifact: str, *, strict_publish_gate: bool) -> dict[str, Any]:
    if not source_availability_artifact:
        return {"phase": _phase("source_availability", "not_supplied"), "blocked_reasons": []}
    matrix = _read_json_if_file(source_availability_artifact)
    if not matrix:
        return {
            "phase": _phase("source_availability", "blocked", [source_availability_artifact]),
            "blocked_reasons": ["source_availability_artifact_unreadable"],
        }
    validation = validate_source_availability_consumers(matrix=matrix, strict_publish_gate=strict_publish_gate)
    return {
        "phase": _phase(
            "source_availability",
            "blocked" if not validation["ok"] else "passed",
            [source_availability_artifact],
        ),
        "blocked_reasons": list(validation.get("blocked_reasons") or []),
    }


def _source_budget_phase(source_budget_evidence: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
    if not source_budget_evidence:
        return {"phase": _phase("source_budget", "not_supplied"), "blocked_reasons": []}
    evidence = normalize_editor_source_budget_evidence_v7(source_budget_evidence)
    blocked = [
        (
            f"source_budget:{row.get('entry_id') or '<unknown>'}:"
            f"{row.get('source_key') or '<unknown>'}:{row.get('decision')}"
        )
        for row in evidence
        if str(row.get("decision") or "") in {"block", "insufficient_evidence"}
    ]
    return {"phase": _phase("source_budget", "blocked" if blocked else "passed"), "blocked_reasons": blocked}


def _safe_apply_phase(
    root: Path,
    actions: list[dict[str, Any]],
    *,
    approved: bool,
    baseline_dashboard: dict[str, Any] | None = None,
    dashboard_id: str = "",
    workbook_id: str = "",
    changed_objects: list[dict[str, Any]] | None = None,
    baseline_snapshot_path: str = "",
) -> dict[str, Any]:
    if not actions:
        return {"phase": _phase("safe_apply", "not_applicable"), "blocked_reasons": []}
    prepared_actions: list[dict[str, Any]] = []
    for action in actions:
        prepared = dict(action)
        if _is_dashboard_action_record(prepared) and baseline_dashboard:
            prepared.setdefault("current_dashboard", baseline_dashboard)
            prepared.setdefault("baseline_dashboard", baseline_dashboard)
            action_dashboard_id = _action_target_object_id(prepared) or dashboard_id
            payload = prepared.get("payload") if isinstance(prepared.get("payload"), dict) else {}
            contract = build_baseline_diff_contract(
                dashboard_id=action_dashboard_id,
                workbook_id=workbook_id,
                baseline_source={"kind": "snapshot", "path": baseline_snapshot_path},
                baseline_dashboard=baseline_dashboard,
                proposed_dashboard=payload,
                changed_objects=changed_objects or [],
            )
            prepared["baseline_diff_contract"] = contract
        prepared_actions.append(prepared)
    plan = create_safe_apply_plan(project_root=str(root), actions=prepared_actions, approved=approved)
    preflight = validate_safe_apply_plan_exhaustive(plan)
    path = root / "artifacts" / "live_maintenance" / "safe_apply_plan.delta_v7.json"
    write_json(path, plan)
    return {
        "phase": _phase("safe_apply", "blocked" if not preflight["ok"] else "planned", [str(path)]),
        "blocked_reasons": list(preflight.get("issues") or []),
        "plan": plan,
    }


def _completion_evidence_phase(
    root: Path,
    *,
    approved: bool,
    publish: bool,
    safe_apply_actions: list[dict[str, Any]],
    safe_apply_execution_evidence: dict[str, Any] | None,
    saved_readback_evidence: dict[str, Any] | None,
    publish_from_saved_evidence: dict[str, Any] | None,
    published_readback_evidence: dict[str, Any] | None,
    safe_apply_plan: dict[str, Any],
    required_object_ids: list[str],
) -> dict[str, Any]:
    required_ids = list(dict.fromkeys(str(item).strip() for item in required_object_ids if str(item).strip()))
    execution = _validate_execution_evidence(
        root,
        evidence=safe_apply_execution_evidence,
        safe_apply_plan=safe_apply_plan,
        required_object_ids=required_ids,
    )
    saved = _validate_readback_evidence(
        root,
        evidence=saved_readback_evidence,
        expected_branch="saved",
        required_object_ids=required_ids,
    )
    publish_from_saved = _validate_publish_from_saved_evidence(
        root,
        evidence=publish_from_saved_evidence,
        required_object_ids=required_ids,
        saved_readback_result=saved,
    )
    published = _validate_readback_evidence(
        root,
        evidence=published_readback_evidence,
        expected_branch="published",
        required_object_ids=required_ids,
    )

    missing: list[str] = []
    if not approved:
        missing.append("approved_safe_apply")
    if not safe_apply_actions:
        missing.append("safe_apply_actions")
    if not execution["supplied"]:
        missing.append("safe_apply_execution_evidence")
    if not saved["supplied"]:
        missing.append("saved_readback_evidence")
    if publish and not publish_from_saved["supplied"]:
        missing.append("publish_from_saved_evidence")
    if publish and not published["supplied"]:
        missing.append("published_readback_evidence")

    blocked: list[str] = []
    for label, result in (
        ("safe_apply_execution", execution),
        ("saved_readback", saved),
        ("publish_from_saved", publish_from_saved),
        ("published_readback", published),
    ):
        if result["supplied"] and not result["verified"]:
            blocked.extend(f"{label}:{issue}" for issue in result["issues"])
    if execution["verified"] and saved["verified"]:
        blocked.extend(_revision_binding_issues("saved", execution, saved, required_ids))
    if publish and publish_from_saved["verified"] and published["verified"]:
        blocked.extend(
            _revision_binding_issues("published", publish_from_saved, published, required_ids)
        )
    if safe_apply_execution_evidence and not approved:
        blocked.append("safe_apply_execution:evidence cannot satisfy an unapproved maintenance run")

    completion_ready = bool(
        approved
        and safe_apply_actions
        and execution["verified"]
        and saved["verified"]
        and (not publish or (publish_from_saved["verified"] and published["verified"]))
        and not blocked
    )
    if blocked:
        status = "blocked"
    elif completion_ready:
        status = "verified"
    elif safe_apply_actions or any(
        item is not None
        for item in (
            safe_apply_execution_evidence,
            saved_readback_evidence,
            publish_from_saved_evidence,
            published_readback_evidence,
        )
    ):
        status = "planned"
    else:
        status = "not_supplied"
    artifact_paths = list(
        dict.fromkeys(
            path
            for result in (execution, saved, publish_from_saved, published)
            for path in result.get("artifact_paths") or []
            if path
        )
    )
    return {
        "phase": _phase("completion_evidence", status, artifact_paths),
        "completion_ready": completion_ready,
        "missing_evidence": missing,
        "blocked_reasons": blocked,
        "required_object_ids": required_ids,
        "safe_apply_execution": execution,
        "saved_readback": saved,
        "publish_from_saved": publish_from_saved,
        "published_readback": published,
        "artifact_paths": artifact_paths,
    }


def _revision_binding_issues(
    branch: str,
    execution: dict[str, Any],
    readback: dict[str, Any],
    object_ids: list[str],
) -> list[str]:
    executed_revisions = execution.get("object_revisions") or {}
    readback_revisions = readback.get("object_revisions") or {}
    return [
        f"{branch}_readback_revision_mismatch:{object_id}"
        for object_id in object_ids
        if str(executed_revisions.get(object_id) or "")
        != str(readback_revisions.get(object_id) or "")
    ]


def _validate_execution_evidence(
    root: Path,
    *,
    evidence: dict[str, Any] | None,
    safe_apply_plan: dict[str, Any],
    required_object_ids: list[str],
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or not evidence:
        return _evidence_result(supplied=False)
    return _validate_execution_manifest(
        root,
        evidence=evidence,
        expected_plan=safe_apply_plan,
        required_object_ids=required_object_ids,
        expected_mode="save",
    )


def _validate_readback_evidence(
    root: Path,
    *,
    evidence: dict[str, Any] | None,
    expected_branch: str,
    required_object_ids: list[str],
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or not evidence:
        return _evidence_result(supplied=False)
    artifact_items = _top_level_artifact_items(evidence)
    artifact_validation = verify_local_artifacts(artifact_items, artifact_root=root)
    issues = [str(item["message"]) for item in artifact_validation["issues"]]
    documents, json_issues = _verified_json_documents(artifact_validation)
    issues.extend(json_issues)
    if not documents:
        issues.append(f"{expected_branch} readback requires a parsed JSON artifact")
    branches = [str(item.get("branch") or "").strip().lower() for item in documents]
    if not branches or any(branch != expected_branch for branch in branches):
        issues.append(f"readback evidence must bind branch={expected_branch}")
    if not documents or any(item.get("live_readback") is not True for item in documents):
        issues.append("readback evidence must record live_readback=true")
    observed_ids = _collect_object_ids(documents)
    revisions = _collect_object_revisions(documents)
    missing_ids = [item for item in required_object_ids if item not in set(observed_ids)]
    if missing_ids:
        issues.append(f"{expected_branch} readback omits required objects: " + ", ".join(missing_ids))
    missing_revisions = [item for item in required_object_ids if not revisions.get(item)]
    if missing_revisions:
        issues.append(f"{expected_branch} readback omits required revisions: " + ", ".join(missing_revisions))
    if not artifact_validation["verified_artifacts"]:
        issues.append(f"{expected_branch} readback requires a verified local artifact")
    return _evidence_result(
        supplied=True,
        verified=not issues,
        issues=issues,
        artifact_validation=artifact_validation,
        object_ids=observed_ids,
        object_revisions=revisions,
        branch=expected_branch,
    )


def _validate_publish_from_saved_evidence(
    root: Path,
    *,
    evidence: dict[str, Any] | None,
    required_object_ids: list[str],
    saved_readback_result: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or not evidence:
        return _evidence_result(supplied=False)
    result = _validate_execution_manifest(
        root,
        evidence=evidence,
        expected_plan=None,
        required_object_ids=required_object_ids,
        expected_mode="publish",
    )
    issues = list(result["issues"])
    saved_metadata = {
        str(Path(str(item.get("resolved_path") or "")).resolve()): item
        for item in saved_readback_result.get("artifact_metadata") or []
        if item.get("resolved_path")
    }
    saved_revisions = saved_readback_result.get("object_revisions") or {}
    manifest = result.get("manifest") if isinstance(result.get("manifest"), dict) else {}
    for action in manifest.get("actions") or []:
        if not isinstance(action, dict):
            continue
        source = action.get("saved_source") if isinstance(action.get("saved_source"), dict) else {}
        source_path = Path(str(source.get("path") or ""))
        if not source_path.is_absolute():
            source_path = root / source_path
        source_meta = saved_metadata.get(str(source_path.resolve()))
        object_id = str(source.get("object_id") or "")
        if not _saved_source_matches_publish_action(action, source):
            issues.append(f"publish action {action.get('index')} saved_source.object_id mismatch")
        if str(source.get("source_branch") or "").lower() != "saved":
            issues.append(f"publish action {action.get('index')} must bind source_branch=saved")
        if not source_meta:
            issues.append(f"publish action {action.get('index')} is not bound to the verified saved readback path")
        elif str(source.get("sha256") or "") != str(source_meta.get("sha256") or ""):
            issues.append(f"publish action {action.get('index')} saved readback hash mismatch")
        if not object_id or str(source.get("revision_id") or "") != str(saved_revisions.get(object_id) or ""):
            issues.append(f"publish action {action.get('index')} saved readback revision mismatch")
    result["issues"] = list(dict.fromkeys(issues))
    result["verified"] = not result["issues"]
    result["branch"] = "saved"
    return result


def _saved_source_matches_publish_action(action: dict[str, Any], saved_source: dict[str, Any]) -> bool:
    action_object_id = str(action.get("object_id") or "").strip()
    source_object_id = str(saved_source.get("object_id") or "").strip()
    return bool(action_object_id and source_object_id and action_object_id == source_object_id)


def _validate_execution_manifest(
    root: Path,
    *,
    evidence: dict[str, Any],
    expected_plan: dict[str, Any] | None,
    required_object_ids: list[str],
    expected_mode: str,
) -> dict[str, Any]:
    issues: list[str] = []
    manifest_item = _execution_manifest_item(evidence)
    artifact_validation = verify_local_artifacts([manifest_item] if manifest_item else [], artifact_root=root)
    issues.extend(str(item["message"]) for item in artifact_validation["issues"])
    documents, json_issues = _verified_json_documents(artifact_validation)
    issues.extend(json_issues)
    manifest = documents[0] if len(documents) == 1 else {}
    if len(documents) != 1:
        issues.append("execution evidence requires exactly one parsed JSON execution manifest")
    if manifest.get("schema_version") != "datalens.safe_apply_execution_evidence.v1":
        issues.append("execution manifest has an unsupported schema_version")
    if str(manifest.get("status") or "") != "completed":
        issues.append("execution manifest status must be completed")
    actions = [item for item in manifest.get("actions") or [] if isinstance(item, dict)]
    run_binding = manifest.get("run_binding") if isinstance(manifest.get("run_binding"), dict) else {}
    run_id = "safe_apply_" + serialized_metadata(run_binding)["sha256"][:12] if run_binding else ""
    if not run_binding or str(manifest.get("run_id") or "") != run_id:
        issues.append("execution manifest run_id does not match its canonical run binding")
    binding_root = Path(str(run_binding.get("project_root") or ""))
    if (
        not str(run_binding.get("project_root") or "").strip()
        or binding_root.resolve() != root.resolve()
        or str(manifest.get("project_root") or "") != str(run_binding.get("project_root") or "")
    ):
        issues.append("execution manifest project_root does not match the maintenance project")
    approval = (
        run_binding.get("approval_provenance")
        if isinstance(run_binding.get("approval_provenance"), dict)
        else {}
    )
    if run_binding.get("approved") is not True or approval.get("approved") is not True:
        issues.append("execution manifest must bind approved safe-apply provenance")
    if not str(run_binding.get("target_lock_hash") or "").strip():
        issues.append("execution manifest must bind a target lock")
    binding_actions = run_binding.get("actions") if isinstance(run_binding.get("actions"), list) else []
    projected_actions = [_manifest_action_binding(item) for item in actions]
    if binding_actions != projected_actions or int(run_binding.get("action_count") or -1) != len(actions):
        issues.append("execution manifest actions do not match its canonical run binding")
    if expected_plan:
        expected_binding = safe_apply_run_binding(expected_plan)
        if run_binding != expected_binding or str(manifest.get("run_id") or "") != safe_apply_run_id(expected_plan):
            issues.append("execution manifest does not bind to the approved safe-apply plan")
    if not actions or any(item.get("executed") is not True or item.get("status") != "executed" for item in actions):
        issues.append("every execution manifest action must be executed")
    modes = {str(item.get("mode") or "").strip().lower() for item in actions}
    if modes != {expected_mode}:
        issues.append(f"execution manifest actions must use mode={expected_mode}")
    expected_readback_branch = "published" if expected_mode == "publish" else "saved"
    if any(str(item.get("readback_branch") or "").lower() != expected_readback_branch for item in actions):
        issues.append(f"execution manifest actions must bind readback_branch={expected_readback_branch}")

    nested_items: list[dict[str, Any]] = []
    observed_ids: list[str] = []
    revisions: dict[str, str] = {}
    for action in actions:
        object_id = str(action.get("object_id") or "").strip()
        if object_id:
            observed_ids.append(object_id)
        for label in ("write_result", "readback"):
            bound = action.get(label) if isinstance(action.get(label), dict) else {}
            if not bound.get("path") or not bound.get("sha256"):
                issues.append(f"execution action {action.get('index')} lacks bound {label} artifact")
            else:
                nested_items.append(bound)
        readback = action.get("readback") if isinstance(action.get("readback"), dict) else {}
        if str(readback.get("branch") or "").lower() != str(action.get("readback_branch") or "").lower():
            issues.append(f"execution action {action.get('index')} readback branch mismatch")
        if object_id and str(readback.get("object_id") or "") != object_id:
            issues.append(f"execution action {action.get('index')} readback object mismatch")
        revision = str(readback.get("revision_id") or "").strip()
        if object_id and not revision:
            issues.append(f"execution action {action.get('index')} lacks a readback revision")
        if object_id and revision:
            revisions[object_id] = revision
            readback_validation = verify_local_artifacts([readback], artifact_root=root)
            readback_documents, readback_json_issues = _verified_json_documents(readback_validation)
            issues.extend(readback_json_issues)
            parsed_revisions = _collect_object_revisions(readback_documents)
            if parsed_revisions.get(object_id) != revision:
                issues.append(f"execution action {action.get('index')} readback artifact identity/revision mismatch")
    nested_validation = verify_local_artifacts(nested_items, artifact_root=root)
    issues.extend(str(item["message"]) for item in nested_validation["issues"])
    nested_documents, nested_json_issues = _verified_json_documents(nested_validation)
    issues.extend(nested_json_issues)
    if len(nested_documents) != len(nested_items):
        issues.append("execution artifacts must all be parsed JSON documents")
    observed_ids = list(dict.fromkeys(observed_ids))
    missing_ids = [item for item in required_object_ids if item not in set(observed_ids)]
    if missing_ids:
        issues.append("execution manifest omits required objects: " + ", ".join(missing_ids))
    combined_validation = {
        "verified_artifacts": [
            *artifact_validation.get("verified_artifacts", []),
            *nested_validation.get("verified_artifacts", []),
        ],
        "issues": [*artifact_validation.get("issues", []), *nested_validation.get("issues", [])],
    }
    result = _evidence_result(
        supplied=True,
        verified=not issues,
        issues=list(dict.fromkeys(issues)),
        artifact_validation=combined_validation,
        object_ids=observed_ids,
        object_revisions=revisions,
    )
    result["run_id"] = str(manifest.get("run_id") or "")
    result["manifest"] = manifest
    return result


def _evidence_result(
    *,
    supplied: bool,
    verified: bool = False,
    issues: list[str] | None = None,
    artifact_validation: dict[str, Any] | None = None,
    object_ids: list[str] | None = None,
    object_revisions: dict[str, str] | None = None,
    branch: str = "",
) -> dict[str, Any]:
    validation = artifact_validation or {"verified_artifacts": [], "issues": []}
    return {
        "supplied": supplied,
        "verified": verified,
        "issues": issues or [],
        "branch": branch,
        "object_ids": object_ids or [],
        "object_revisions": object_revisions or {},
        "artifact_paths": [
            str(item.get("resolved_path") or item.get("path") or "")
            for item in validation.get("verified_artifacts") or []
            if item.get("resolved_path") or item.get("path")
        ],
        "artifact_metadata": validation.get("verified_artifacts") or [],
    }


def _top_level_artifact_items(*values: dict[str, Any]) -> list[str | dict[str, Any]]:
    items: list[str | dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        metadata = value.get("artifact_metadata")
        if isinstance(metadata, list):
            items.extend(item for item in metadata if isinstance(item, dict))
        for key in (
            "artifact_path",
            "saved_readback_path",
            "published_readback_path",
        ):
            if value.get(key):
                items.append(str(value[key]))
        if isinstance(value.get("artifact_paths"), list):
            items.extend(str(item) for item in value["artifact_paths"] if str(item))
    return items


def _verified_json_documents(validation: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    documents: list[dict[str, Any]] = []
    issues: list[str] = []
    for item in validation.get("verified_artifacts") or []:
        path = Path(str(item.get("resolved_path") or ""))
        if not path.is_file():
            continue
        if path.suffix.lower() != ".json":
            issues.append(f"evidence artifact must be JSON: {path}")
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append(f"evidence artifact is not valid JSON: {path}")
            continue
        if isinstance(value, dict):
            documents.append(value)
        else:
            issues.append(f"evidence artifact must contain one JSON object: {path}")
    return documents, issues


def _execution_manifest_item(evidence: dict[str, Any]) -> str | dict[str, Any] | None:
    artifact = evidence.get("execution_artifact")
    if isinstance(artifact, dict) and artifact.get("path"):
        return artifact
    for key in ("execution_artifact_path", "artifact_path"):
        if str(evidence.get(key) or "").strip():
            return str(evidence[key])
    return None


def _manifest_action_binding(action: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "index",
        "action",
        "method",
        "object_id",
        "transaction_group_id",
        "change_scope",
        "semantic_role",
        "shared_object_key",
        "mode",
        "expected_revision",
        "payload_sha256",
        "desired_overlay_sha256",
        "readback_branch",
        "target_lock_hash",
        "approval_provenance",
        "saved_source",
    )
    return {key: action[key] for key in keys if key in action}


def _collect_object_revisions(values: list[dict[str, Any]]) -> dict[str, str]:
    revisions: dict[str, str] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            explicit = value.get("object_revisions")
            if isinstance(explicit, dict):
                for object_id, revision in explicit.items():
                    if str(object_id).strip() and str(revision or "").strip():
                        revisions.setdefault(str(object_id).strip(), str(revision).strip())
            ids = []
            for key in ("object_id", "objectId", "entryId", "dashboardId", "chartId", "datasetId", "connectionId"):
                item = value.get(key)
                if not isinstance(item, (dict, list)) and str(item or "").strip():
                    ids.append(str(item).strip())
            if isinstance(value.get("object_ids"), list):
                ids.extend(str(item).strip() for item in value["object_ids"] if str(item).strip())
            revision = str(
                value.get("revId")
                or value.get("rev_id")
                or value.get("revisionId")
                or value.get("revision_id")
                or ""
            ).strip()
            if revision:
                for object_id in ids:
                    revisions.setdefault(object_id, revision)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for value in values:
        walk(value)
    return revisions


def _collect_object_ids(values: list[dict[str, Any]]) -> list[str]:
    scalar_keys = {
        "object_id",
        "objectId",
        "entryId",
        "dashboardId",
        "chartId",
        "datasetId",
        "connectionId",
        "target_dashboard_id",
        "target_chart_id",
    }
    list_keys = {"object_ids", "changed_object_ids", "chart_ids", "target_object_ids"}
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in scalar_keys and not isinstance(item, (dict, list)) and str(item).strip():
                    found.append(str(item).strip())
                elif key in list_keys and isinstance(item, list):
                    found.extend(str(element).strip() for element in item if str(element).strip())
                elif key == "object_revisions" and isinstance(item, dict):
                    found.extend(str(element).strip() for element in item if str(element).strip())
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for value in values:
        walk(value)
    return list(dict.fromkeys(found))


def _runtime_gate_phase(
    root: Path,
    *,
    run_id: str,
    phase_name: str,
    delivery_stage: str,
    runtime_gate_evidence: dict[str, Any] | None,
    target_url: str,
    target_tab_id: str,
    required_object_ids: list[str],
    required_branch: str,
    required_object_revisions: dict[str, str],
    expected_titles: list[str],
    browser_runtime_required: bool,
    non_rendering_exemption: str,
) -> dict[str, Any]:
    supplied = runtime_gate_evidence if isinstance(runtime_gate_evidence, dict) else {}
    required_changed_ids = list(
        dict.fromkeys(str(item).strip() for item in required_object_ids if str(item).strip())
    )
    required_titles = list(
        dict.fromkeys(
            [str(item) for item in expected_titles if str(item).strip()]
            + [str(item) for item in supplied.get("expected_titles") or [] if str(item).strip()]
        )
    )
    evidence = build_runtime_gate_evidence(
        status=str(supplied.get("status") or "not_run"),
        target_url=str(supplied.get("target_url") or ""),
        tab_id=str(supplied.get("tab_id") or ""),
        changed_object_ids=[
            str(item)
            for item in supplied.get("changed_object_ids") or supplied.get("changed_chart_ids") or []
        ],
        required_changed_object_ids=required_changed_ids,
        required_target_url=target_url,
        required_tab_id=target_tab_id,
        branch=str(supplied.get("branch") or ""),
        revision_id=str(supplied.get("revision_id") or ""),
        object_revisions=(
            supplied.get("object_revisions") if isinstance(supplied.get("object_revisions"), dict) else {}
        ),
        required_branch=required_branch,
        required_revision_id=str(supplied.get("required_revision_id") or ""),
        required_object_revisions=required_object_revisions,
        delivery_stage=delivery_stage,
        checked_selectors=(
            supplied.get("checked_selectors") if isinstance(supplied.get("checked_selectors"), list) else []
        ),
        visible_widget_titles=(
            supplied.get("visible_widget_titles") if isinstance(supplied.get("visible_widget_titles"), list) else []
        ),
        expected_titles=required_titles,
        body_text_excerpt=str(supplied.get("body_text_excerpt") or ""),
        console_messages=supplied.get("console_messages") if isinstance(supplied.get("console_messages"), list) else [],
        dom_error_texts=supplied.get("dom_error_texts") if isinstance(supplied.get("dom_error_texts"), list) else [],
        marker_counts=supplied.get("marker_counts") if isinstance(supplied.get("marker_counts"), dict) else {},
        console_error_count=(
            supplied.get("console_error_count")
            if isinstance(supplied.get("console_error_count"), int)
            else None
        ),
        extracted_error_details=(
            supplied.get("extracted_error_details")
            if isinstance(supplied.get("extracted_error_details"), list)
            else []
        ),
        screenshot_artifacts=(
            supplied.get("screenshot_artifacts") if isinstance(supplied.get("screenshot_artifacts"), list) else []
        ),
        proof_artifacts=supplied.get("proof_artifacts") if isinstance(supplied.get("proof_artifacts"), list) else [],
        proof_artifact_metadata=(
            supplied.get("proof_artifact_metadata")
            if isinstance(supplied.get("proof_artifact_metadata"), list)
            else []
        ),
        browser_capture_artifact=str(supplied.get("browser_capture_artifact") or ""),
        browser_capture_artifact_metadata=(
            supplied.get("browser_capture_artifact_metadata")
            if isinstance(supplied.get("browser_capture_artifact_metadata"), dict)
            else None
        ),
        artifact_root=root,
        non_rendering_exemption=(
            non_rendering_exemption if not browser_runtime_required and str(non_rendering_exemption).strip() else ""
        ),
        blocked_reason=str(supplied.get("blocked_reason") or ""),
    )
    runtime_smoke = build_browser_runtime_smoke(
        status=str(evidence.get("status") or "not_run"),
        target_url=str(evidence.get("target_url") or ""),
        tab_id=str(evidence.get("tab_id") or ""),
        changed_chart_ids=[str(item) for item in evidence.get("changed_object_ids") or [] if str(item)],
        required_changed_chart_ids=required_changed_ids,
        required_target_url=target_url,
        required_tab_id=target_tab_id,
        branch=str(evidence.get("branch") or ""),
        revision_id=str(evidence.get("revision_id") or ""),
        object_revisions=(
            evidence.get("object_revisions") if isinstance(evidence.get("object_revisions"), dict) else {}
        ),
        required_branch=required_branch,
        required_revision_id=str(evidence.get("required_revision_id") or ""),
        required_object_revisions=required_object_revisions,
        delivery_stage=delivery_stage,
        checked_selectors=(
            evidence.get("checked_selectors") if isinstance(evidence.get("checked_selectors"), list) else []
        ),
        visible_widget_titles=(
            evidence.get("visible_widget_titles") if isinstance(evidence.get("visible_widget_titles"), list) else []
        ),
        expected_titles=[str(item) for item in evidence.get("expected_titles") or []],
        body_text_excerpt=str(evidence.get("body_text_excerpt") or ""),
        console_messages=evidence.get("console_messages") if isinstance(evidence.get("console_messages"), list) else [],
        dom_error_texts=evidence.get("dom_error_texts") if isinstance(evidence.get("dom_error_texts"), list) else [],
        marker_counts=evidence.get("marker_counts") if isinstance(evidence.get("marker_counts"), dict) else {},
        console_error_count=(
            evidence.get("console_error_count")
            if isinstance(evidence.get("console_error_count"), int)
            else None
        ),
        extracted_error_details=(
            evidence.get("extracted_error_details")
            if isinstance(evidence.get("extracted_error_details"), list)
            else []
        ),
        screenshot_artifacts=(
            evidence.get("screenshot_artifacts")
            if isinstance(evidence.get("screenshot_artifacts"), list)
            else []
        ),
        proof_artifacts=evidence.get("proof_artifacts") if isinstance(evidence.get("proof_artifacts"), list) else [],
        proof_artifact_metadata=(
            evidence.get("proof_artifact_metadata")
            if isinstance(evidence.get("proof_artifact_metadata"), list)
            else []
        ),
        browser_capture_artifact=str(evidence.get("browser_capture_artifact") or ""),
        browser_capture_artifact_metadata=(
            next(
                (
                    item
                    for item in evidence.get("proof_artifact_metadata") or []
                    if str(item.get("resolved_path") or item.get("path") or "")
                    == str(evidence.get("browser_capture_artifact") or "")
                ),
                None,
            )
        ),
        artifact_root=root,
        non_rendering_exemption=str(evidence.get("non_rendering_exemption") or ""),
        blocked_reason=str(evidence.get("blocked_reason") or ""),
    )
    artifact_path = root / "artifacts" / "live_maintenance" / f"{run_id}.{delivery_stage}.json"
    write_json(artifact_path, runtime_smoke)
    return {
        "phase": _phase(phase_name, evidence.get("status") or "not_run", [str(artifact_path)]),
        "evidence": evidence,
        "runtime_smoke": runtime_smoke,
        "artifact_path": str(artifact_path),
    }


def _cleanup_plan(
    *,
    changed_objects: list[dict[str, Any]],
    cleanup_mode: str,
    safe_apply_blocked: bool,
) -> dict[str, Any]:
    created = [
        item
        for item in changed_objects
        if str(item.get("change_type") or item.get("action") or "").lower() in {"create", "append"}
    ]
    blocked = []
    for item in changed_objects:
        if item.get("cleanup_requested") and item.get("active_in_saved_or_published_graph"):
            blocked.append("cleanup_refuses_active_saved_or_published_graph_object")
    return {
        "schema_version": "datalens.delta_v7.cleanup_plan.v1",
        "mode": cleanup_mode,
        "status": "blocked" if blocked else "plan_only" if created or safe_apply_blocked else "not_required",
        "created_object_count": len(created),
        "blocked_reasons": blocked,
        "created_objects": created,
    }


def _delivery_stage(
    *,
    completion_evidence: dict[str, Any],
    saved_runtime_gate: dict[str, Any],
    published_runtime_gate: dict[str, Any],
    publish_allowed: bool,
) -> str:
    saved = completion_evidence.get("saved_readback") or {}
    publish_from_saved = completion_evidence.get("publish_from_saved") or {}
    published = completion_evidence.get("published_readback") or {}
    stage = "planned"
    if saved.get("verified"):
        stage = "saved"
    if stage == "saved" and saved_runtime_gate.get("status") == "passed":
        stage = "saved_runtime_passed"
    if publish_allowed and publish_from_saved.get("verified") and published.get("verified"):
        stage = "published"
    if stage == "published" and published_runtime_gate.get("status") == "passed":
        stage = "published_runtime_passed"
    return stage


def _handoff(
    *,
    status: str,
    runtime_first_status: str,
    validation_budget: dict[str, Any],
    runtime_smoke: dict[str, Any],
    target: dict[str, Any],
    changed_objects: list[dict[str, Any]],
    runtime_gate_path: str,
    metadata_evidence_paths: list[str],
    cleanup_report_path: str,
    completion_evidence: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    api_readback_paths = list(
        dict.fromkeys(
            path
            for key in ("saved_readback", "published_readback")
            for path in (completion_evidence.get(key) or {}).get("artifact_paths") or []
            if path
        )
    )
    return {
        "schema_version": FINAL_HANDOFF_SCHEMA_VERSION,
        "status": status,
        "runtime_first_status": runtime_first_status,
        "target": target,
        "validation_budget": validation_budget,
        "runtime_smoke": runtime_smoke,
        "changed_objects": changed_objects,
        "proof": {
            "api_readback_paths": api_readback_paths,
            "safe_apply_execution_paths": (
                completion_evidence.get("safe_apply_execution") or {}
            ).get("artifact_paths")
            or [],
            "publish_from_saved_paths": (
                completion_evidence.get("publish_from_saved") or {}
            ).get("artifact_paths")
            or [],
            "runtime_gate_path": runtime_gate_path,
            "metadata_evidence_paths": [str(path) for path in metadata_evidence_paths if str(path)],
            "cleanup_report_path": cleanup_report_path,
        },
        "limitations": limitations,
    }


def _final_status(
    *,
    blockers: list[str],
    approved: bool,
    runtime_gate: dict[str, Any],
    browser_runtime_required: bool,
    non_rendering_exemption: str,
    completion_ready: bool,
) -> str:
    if blockers:
        return "blocked"
    if not approved:
        return "planned"
    runtime_status = final_status_from_runtime_gate(
        runtime_gate,
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
    )
    if runtime_status != "done":
        return runtime_status
    return "done" if completion_ready else "planned"


def _runtime_first_status(
    *,
    blockers_before_runtime: list[str],
    approved: bool,
    runtime_gate: dict[str, Any],
    browser_runtime_required: bool,
    non_rendering_exemption: str,
    completion_ready: bool,
) -> str:
    if blockers_before_runtime:
        return "blocked_before_write"
    if not approved:
        return "structural_ok_runtime_not_checked"
    runtime_status = runtime_first_status_from_runtime_gate(
        runtime_gate,
        browser_runtime_required=browser_runtime_required,
        non_rendering_exemption=non_rendering_exemption,
    )
    if runtime_status == "runtime_passed" and not completion_ready:
        return "runtime_not_verified"
    return runtime_status


def _limitations(
    status: str,
    blockers: list[str],
    browser_runtime_required: bool,
    non_rendering_exemption: str,
    *,
    completion_evidence: dict[str, Any],
) -> list[str]:
    if blockers:
        return blockers[:20]
    if status == "runtime_not_verified":
        return ["browser/runtime proof is missing or blocked"]
    if status == "planned" and completion_evidence.get("missing_evidence"):
        return [
            "maintenance remains plan-only; missing completion evidence: "
            + ", ".join(str(item) for item in completion_evidence["missing_evidence"])
        ]
    if not browser_runtime_required and non_rendering_exemption:
        return [f"runtime gate exempted: {non_rendering_exemption}"]
    return []


def _create_proof_sufficient(value: dict[str, Any]) -> bool:
    proof = value.get("create_necessity_proof") if isinstance(value.get("create_necessity_proof"), dict) else value
    if not isinstance(proof, dict):
        return False
    reason = str(proof.get("update_insufficient_reason") or proof.get("reason") or "").strip()
    checked = bool(proof.get("existing_readback_checked") or proof.get("object_reuse_checked"))
    return bool(reason and checked)


def _publish_action_scope_issues(actions: list[dict[str, Any]], *, publish: bool) -> list[str]:
    if publish:
        return []
    issues: list[str] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        mode = str(payload.get("mode") or action.get("mode") or "save").strip().lower()
        if mode == "publish" or action.get("publish") is True:
            issues.append(f"safe_apply_action_{index}:publish_action_requires_top_level_publish_true")
    return issues


def _expected_runtime_titles(
    *,
    changed_objects: list[dict[str, Any]],
    proposed_dashboard: dict[str, Any],
    safe_apply_actions: list[dict[str, Any]],
    required_object_ids: list[str],
    target_tab_id: str,
) -> list[str]:
    titles: list[str] = []
    title_keys = ("title", "display_title", "displayTitle", "displayKey", "native_title")
    required = {str(item).strip() for item in required_object_ids if str(item).strip()}

    def add_from(value: Any) -> None:
        if not isinstance(value, dict):
            return
        for key in title_keys:
            if str(value.get(key) or "").strip():
                titles.append(str(value[key]).strip())

    for item in changed_objects:
        object_id = str(item.get("object_id") or item.get("id") or "").strip()
        item_tab_id = str(item.get("tab_id") or item.get("tabId") or "").strip()
        if object_id in required or (target_tab_id and item_tab_id == target_tab_id):
            add_from(item)
    for action in safe_apply_actions:
        if not isinstance(action, dict):
            continue
        if _action_target_object_id(action) not in required:
            continue
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        if _is_dashboard_action_record(action):
            _append_target_tab_titles(payload, target_tab_id=target_tab_id, required_object_ids=required, add=add_from)
        else:
            add_from(payload)
            add_from(entry)
            add_from(data)

    _append_target_tab_titles(
        proposed_dashboard,
        target_tab_id=target_tab_id,
        required_object_ids=required,
        add=add_from,
    )
    return list(dict.fromkeys(title for title in titles if title))


def _append_target_tab_titles(
    dashboard: dict[str, Any],
    *,
    target_tab_id: str,
    required_object_ids: set[str],
    add: Any,
) -> None:
    if not target_tab_id:
        return
    for tab in _dashboard_tabs(dashboard):
        if not isinstance(tab, dict):
            continue
        tab_id = str(tab.get("id") or tab.get("tabId") or tab.get("tab_id") or "").strip()
        if tab_id != target_tab_id:
            continue
        add(tab)

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if _value_references_target(value, required_object_ids):
                    add(value)
                    if isinstance(value.get("data"), dict):
                        add(value["data"])
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(tab)


def _value_references_target(value: Any, required_object_ids: set[str]) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "object_id",
                "objectId",
                "entryId",
                "chartId",
                "dashboardId",
                "datasetId",
                "connectionId",
            } and str(item or "").strip() in required_object_ids:
                return True
            if _value_references_target(item, required_object_ids):
                return True
    elif isinstance(value, list):
        return any(_value_references_target(item, required_object_ids) for item in value)
    return False


def _dashboard_tabs(value: dict[str, Any]) -> list[Any]:
    entry = value.get("entry") if isinstance(value.get("entry"), dict) else {}
    entry_data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    data = value.get("data") if isinstance(value.get("data"), dict) else {}
    for candidate in (entry_data.get("tabs"), data.get("tabs"), value.get("tabs")):
        if isinstance(candidate, list):
            return candidate
    return []


def _action_target_object_id(action: dict[str, Any]) -> str:
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    fresh_payload = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    return str(
        action.get("object_id")
        or entry.get("entryId")
        or payload.get("dashboardId")
        or payload.get("chartId")
        or fresh_payload.get("dashboardId")
        or fresh_payload.get("chartId")
        or ""
    ).strip()


def _is_dashboard_action_record(action: dict[str, Any]) -> bool:
    return "dashboard" in str(action.get("method") or "").lower()


def _resolve_rendering_scope(
    root: Path,
    *,
    runtime_gate_evidence: dict[str, Any] | None,
    target_url: str,
    target_tab_id: str,
    browser_runtime_required: bool,
    non_rendering_exemption: str,
) -> dict[str, Any]:
    resolved_url = str(target_url or "").strip()
    resolved_tab_id = str(target_tab_id or "").strip()
    evidence = runtime_gate_evidence if isinstance(runtime_gate_evidence, dict) else {}
    status = str(evidence.get("status") or "").strip().lower()
    rendering_claimed = status in {"passed", "pass", "ok", "browser_pass"}
    if browser_runtime_required and rendering_claimed and not str(non_rendering_exemption or "").strip():
        capture_path = Path(str(evidence.get("browser_capture_artifact") or ""))
        if str(capture_path) not in {"", "."}:
            if not capture_path.is_absolute():
                capture_path = root / capture_path
            capture = _read_json_if_file(str(capture_path))
            resolved_url = resolved_url or str(capture.get("target_url") or "").strip()
            resolved_tab_id = resolved_tab_id or str(capture.get("tab_id") or "").strip()
    blocked: list[str] = []
    if browser_runtime_required and rendering_claimed and not str(non_rendering_exemption or "").strip():
        if not resolved_url:
            blocked.append("rendering_run_requires_target_url")
        if not resolved_tab_id:
            blocked.append("rendering_run_requires_target_tab_id")
    return {
        "target_url": resolved_url,
        "target_tab_id": resolved_tab_id,
        "blocked_reasons": blocked,
    }


def _non_rendering_exemption_issue(
    *,
    browser_runtime_required: bool,
    non_rendering_exemption: str,
    dashboard_id: str,
    target_object_ids: list[str],
) -> str:
    exemption = str(non_rendering_exemption or "").strip()
    if not exemption:
        return ""
    if browser_runtime_required:
        return "non_rendering_exemption_requires_browser_runtime_required_false"
    if not str(dashboard_id or "").strip() and not any(str(item).strip() for item in target_object_ids):
        return "non_rendering_exemption_requires_scoped_dashboard_or_object_target"
    return ""


def _normalize_maintenance_mode(value: str, *, intent: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in MAINTENANCE_MODES:
        return normalized
    lowered_intent = str(intent or "").lower()
    if "source" in lowered_intent or "availability" in lowered_intent:
        return "source_availability_patch"
    if "dataset" in lowered_intent or "sql" in lowered_intent:
        return "dataset_sql_patch"
    if "audit" in lowered_intent:
        return "full_audit"
    return "quick_visible_patch"


def _validation_budget(*, mode: str, publish: bool, elapsed_seconds: float) -> dict[str, Any]:
    required_by_mode = {
        "quick_visible_patch": [
            "fresh_read_target_object_and_touched_tab",
            "baseline_diff_touched_scope",
            "patch_existing_object",
            "save",
            "publish" if publish else "save_only",
            "browser_runtime_smoke",
            "final_handoff",
        ],
        "dataset_sql_patch": [
            "fresh_read_dataset_and_affected_chart",
            "validateDataset_schema_hint",
            "sql_runtime_reality_check",
            "patch_existing_dataset_or_chart",
            "save",
            "publish" if publish else "save_only",
            "browser_runtime_smoke",
            "final_handoff",
        ],
        "source_availability_patch": [
            "fresh_read_touched_source_consumers",
            "source_availability_runtime_matrix",
            "patch_existing_source_consumer",
            "save",
            "publish" if publish else "save_only",
            "browser_runtime_smoke",
            "final_handoff",
        ],
        "full_audit": [
            "fresh_read_full_target_graph",
            "full_dashboard_audit",
            "full_workbook_inventory_if_needed",
            "safe_apply",
            "save",
            "publish" if publish else "save_only",
            "browser_runtime_smoke",
            "final_handoff",
        ],
    }
    skipped_by_mode = {
        "quick_visible_patch": [
            (
                "validateDataset",
                "dataset schema/source SQL was not declared as changed",
                True,
            ),
            ("full_workbook_inventory", "single visible target patch only needs touched graph", True),
            ("full_dashboard_audit", "default patch scope is touched tab/object", True),
            ("repeated_no_diff_dry_runs", "readback parity did not catch logged runtime failures", True),
            ("readback_parity_as_acceptance", "API parity is structural evidence only", True),
        ],
        "dataset_sql_patch": [
            ("full_workbook_inventory", "dataset SQL patch uses affected object graph only", True),
            ("full_dashboard_audit", "runtime smoke is decisive for changed visible targets", True),
            ("readback_parity_as_acceptance", "readback cannot prove ClickHouse/browser runtime", True),
        ],
        "source_availability_patch": [
            ("validateDataset", "source matrix conflict resolution is not a dataset compile check", True),
            ("full_workbook_inventory", "source patch uses declared consumers and touched graph", True),
            ("readback_parity_as_acceptance", "consumer availability conflicts require runtime matrix", True),
        ],
        "full_audit": [],
    }
    skipped_gates = [
        {
            "gate": gate,
            "skip_reason": reason,
            "would_not_catch_runtime_failure": would_not_catch,
        }
        for gate, reason, would_not_catch in skipped_by_mode.get(mode, [])
    ]
    return {
        "mode": mode,
        "required_gates": required_by_mode.get(mode, required_by_mode["quick_visible_patch"]),
        "skipped_gates": skipped_gates,
        "elapsed_seconds": round(max(elapsed_seconds, 0.0), 3),
        "acceptance_hierarchy": [
            "browser_runtime_smoke",
            "runtime_error_details",
            "targeted_source_evidence",
            "saved_published_readback_structure",
            "validateDataset_schema_hint",
        ],
    }


def _read_json_if_file(path: str) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _phase(name: str, status: str, artifact_paths: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "artifact_paths": [str(path) for path in artifact_paths or [] if str(path)]}


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("delta_v7_%Y%m%dT%H%M%SZ")
