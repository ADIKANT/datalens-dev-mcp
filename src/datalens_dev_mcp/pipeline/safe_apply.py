from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.api.methods import is_write_method
from datalens_dev_mcp.api.request_compiler import validate_method_request
from datalens_dev_mcp.serialization import sanitize_response, serialized_metadata, stable_json_text
from datalens_dev_mcp.pipeline.proof_levels import proof_level_for_readback_branch
from datalens_dev_mcp.pipeline.readback import normalize_readback_mode
from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract, create_necessity_proof
from datalens_dev_mcp.pipeline.reconciliation import (
    reconcile_partial_creates,
    validate_entries_reconciliation_evidence,
)
from datalens_dev_mcp.pipeline.sql_performance import validate_payload_sql_performance
from datalens_dev_mcp.pipeline.user_request import normalize_user_request
from datalens_dev_mcp.pipeline.wizard_contracts import (
    validate_wizard_field_binding_against_dataset_readback,
    validate_wizard_visual_dataset_contract,
)
from datalens_dev_mcp.pipeline.route_registry import is_supported_wizard_visualization
from datalens_dev_mcp.validators.route_validator import ValidationResult
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.datalens_names import find_unsafe_internal_names, format_unsafe_internal_name_issues
from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload
from datalens_dev_mcp.validators.redaction import redact_text

DESTRUCTIVE_TERMS = ("delete", "remove", "move", "permission", "accessBinding")
READBACK_BRANCHES = {"saved", "published"}
SAFE_APPLY_DEBUG_INLINE_CHAR_CAP = 2_000
SAFE_APPLY_CREATE_INVENTORY_MAX_PAGES = 25
SAFE_APPLY_CREATE_INVENTORY_MAX_ENTRIES = 10_000
REQUEST_CONTROL_IDENTITY_KEYS = (
    "mode",
    "entryId",
    "chartId",
    "dashboardId",
    "datasetId",
    "connectionId",
    "workbookId",
    "template",
    "annotation",
)
PUBLISH_OBJECT_METHODS: dict[str, dict[str, str]] = {
    "dashboard": {"read": "getDashboard", "write": "updateDashboard", "id_key": "dashboardId"},
    "editor_chart": {"read": "getEditorChart", "write": "updateEditorChart", "id_key": "chartId"},
    "advanced_editor_chart": {"read": "getEditorChart", "write": "updateEditorChart", "id_key": "chartId"},
    "wizard_chart": {"read": "getWizardChart", "write": "updateWizardChart", "id_key": "chartId"},
    "ql_chart": {"read": "getQLChart", "write": "updateQLChart", "id_key": "chartId"},
}
EDITOR_PUBLISH_ALIASES = {
    "chart",
    "editor",
    "editor_chart",
    "advanced_editor",
    "advanced_editor_chart",
    "table",
    "table_node",
    "control",
    "control_node",
    "markdown",
    "markdown_node",
    "d3",
    "d3_node",
}
CREATE_READBACK_ID_KEYS: dict[str, str] = {
    "getConnection": "connectionId",
    "getDashboard": "dashboardId",
    "getDataset": "datasetId",
    "getEditorChart": "chartId",
    "getQLChart": "chartId",
    "getReport": "reportId",
    "getWizardChart": "chartId",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_safe_apply_plan(
    *,
    project_root: str,
    actions: list[dict[str, Any]],
    approved: bool = False,
    approval_note: str = "",
    user_request_text: str = "",
) -> dict[str, Any]:
    normalized_actions = []
    created_at = now_utc()
    request_intent = _request_intent_binding(user_request_text, approved=approved)
    approval_source = (
        "current_user_request"
        if approved and user_request_text
        else "legacy_approved_plan"
        if approved
        else "not_authorized"
    )
    default_target_lock = _default_action_target_lock(actions)
    for action in actions:
        item = dict(action)
        saved_source_path = str(item.get("saved_readback_path") or "").strip()
        if saved_source_path and not Path(saved_source_path).is_absolute():
            item["saved_readback_path"] = str(Path(project_root) / saved_source_path)
        item.setdefault("mode", "save")
        item.setdefault("transaction_group_id", "delivery")
        item.setdefault("requires_fresh_read", True)
        item.setdefault("preserve_unknown_fields", True)
        item["readback_mode"] = normalize_readback_mode(item.get("readback_mode"))
        item.setdefault("readback_required", item["readback_mode"] != "none")
        payload = _payload_for_action(item)
        desired_overlay = item.get("desired_overlay")
        item["desired_overlay"] = deepcopy(desired_overlay if isinstance(desired_overlay, dict) else payload)
        item.setdefault("action_type", _action_type(item, payload))
        if _is_dashboard_action(item):
            item.setdefault("change_scope", "content")
        else:
            item.setdefault("change_scope", "content")
        item["publish_required"] = bool(
            item.get("publish_required") or _saved_published_identity_diverges(item, payload)
        )
        if item["action_type"] == "create":
            item["creation_necessity_proof"] = create_necessity_proof(action=item, payload=payload)
        item.setdefault("target_lock_hash", default_target_lock["lock_hash"])
        item["source_owner"] = _source_owner_contract(item)
        item["payload_contract"] = _payload_contract(item, payload)
        item["fresh_read_contract"] = _fresh_read_contract(item)
        item["readback_contract"] = _readback_contract(item, payload)
        item["revision_guard"] = _revision_guard(item, payload)
        item["stale_revision_retry_policy"] = _stale_revision_retry_policy(item, payload)
        item["branch_semantics"] = _branch_semantics(item, payload)
        item["approval_provenance"] = _approval_provenance(
            approved=approved,
            approval_note=approval_note,
            approved_at=created_at,
            approval_source=approval_source,
            request_digest=request_intent["request_sha256"],
        )
        item["revision_preservation"] = {
            "requires_fresh_read": bool(item.get("requires_fresh_read")),
            "expected_revision": _expected_revision(item, payload),
            "stale_revision_blocks_write": True,
            "unknown_fields_preserved": bool(item.get("preserve_unknown_fields", True)),
            "blocked_policy": str(item.get("unknown_field_policy_block") or ""),
        }
        normalized_actions.append(item)
    return {
        "schema_version": "2026-05-25.safe_apply_plan.v1",
        "created_at": created_at,
        "project_root": project_root,
        "read_only_default": True,
        "write_requires_env": "DATALENS_MCP_ENABLE_WRITES=1",
        "expert_rpc_requires_env": "DATALENS_MCP_ENABLE_EXPERT_RPC=1",
        "default_mode": "save",
        "approved": approved,
        "approval_note": approval_note,
        "approval_provenance": _approval_provenance(
            approved=approved,
            approval_note=approval_note,
            approved_at=created_at,
            approval_source=approval_source,
            request_digest=request_intent["request_sha256"],
        ),
        "request_intent": request_intent,
        "target_lock": default_target_lock,
        "branch_semantics": {
            "default_write_mode": "save",
            "save_readback_branch": "saved",
            "publish_source_branch": "saved",
            "publish_readback_branch": "published",
        },
        "transaction_policy": {
            "no_partial_publish": True,
            "publish_requires_completed_save_actions_in_group": True,
            "unknown_write_outcome_blocks_resume": True,
        },
        "result_contract": {
            "action_stage_result_shapes": ["inline", "artifact"],
            "full_rpc_envelopes": "artifact_backed",
            "downstream_reader": "load_safe_apply_stage_value",
            "partial_create_retry_requires_reconciliation": True,
        },
        "actions": normalized_actions,
    }


def _default_action_target_lock(actions: list[dict[str, Any]]) -> dict[str, Any]:
    targets: list[dict[str, str]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        payload = _payload_for_action(action)
        if _action_type(action, payload) not in {"update", "publish"}:
            continue
        targets.append(
            {
                "method": str(action.get("method") or ""),
                "object_id": _action_object_id(action, payload),
            }
        )
    targets.sort(key=lambda item: (item["method"], item["object_id"]))
    lock_hash = serialized_metadata({"targets": targets})["sha256"]
    target_ids = [item["object_id"] for item in targets if item["object_id"]]
    all_targets_known = bool(targets) and len(target_ids) == len(targets)
    single_method = targets[0]["method"] if len(targets) == 1 else ""
    single_object_id = target_ids[0] if len(target_ids) == 1 else ""
    return {
        "target_source": "manual",
        "target_workbook_id": "",
        "target_dashboard_id": single_object_id if "Dashboard" in single_method else "",
        "target_chart_id": single_object_id if "Chart" in single_method else "",
        "target_object_type": "safe_apply_action_set",
        "target_object_key": ",".join(target_ids),
        "target_objects": targets,
        "target_url": "",
        "lock_hash": lock_hash,
        "status": "locked" if all_targets_known else "missing",
        "evidence": [
            f"action_target:{item['method']}:{item['object_id']}"
            for item in targets
            if item["object_id"]
        ],
    }


def _target_action_set_issues(
    target_lock: dict[str, Any],
    actions: list[dict[str, Any]],
) -> list[str]:
    expected_raw = target_lock.get("target_objects")
    if not isinstance(expected_raw, list) or not expected_raw:
        return []
    expected: list[tuple[str, str]] = []
    issues: list[str] = []
    for item in expected_raw:
        if not isinstance(item, dict):
            issues.append("target_lock.target_objects must contain objects")
            continue
        method = str(item.get("method") or "").strip()
        object_id = str(item.get("object_id") or "").strip()
        if not method or not object_id:
            issues.append("target_lock.target_objects require method and object_id")
            continue
        expected.append((method, object_id))
    actual: list[tuple[str, str]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        payload = _payload_for_action(action)
        if _action_type(action, payload) not in {"update", "publish"}:
            continue
        actual.append(
            (
                str(action.get("method") or "").strip(),
                _action_object_id(action, payload),
            )
        )
    if len(set(expected)) != len(expected):
        issues.append("target_lock.target_objects contain duplicate targets")
    if len(set(actual)) != len(actual):
        issues.append("safe apply actions contain duplicate locked targets")
    if sorted(set(expected)) != sorted(set(actual)):
        issues.append("safe apply actions do not exactly match target_lock.target_objects")
    if str(target_lock.get("status") or "").strip().lower() != "locked":
        issues.append("action-set target_lock status must be locked")
    return issues


def load_safe_apply_stage_value(
    action_result: dict[str, Any],
    label: str,
    *,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    """Load an action stage value whether it was returned inline or artifact-backed."""

    for container_name in ("inline_results", "results", "responses"):
        container = action_result.get(container_name)
        if isinstance(container, dict) and isinstance(container.get(label), dict):
            return {"ok": True, "source": "inline", "label": label, "value": container[label]}
    inline = action_result.get(label)
    if isinstance(inline, dict):
        return {"ok": True, "source": "inline", "label": label, "value": inline}
    artifact = (action_result.get("artifacts") or {}).get(label)
    if not isinstance(artifact, dict):
        return _error("missing_stage_result", f"action result has no inline or artifact-backed `{label}` value")
    artifact_path = str(artifact.get("path") or "").strip()
    if not artifact_path:
        return _error("missing_stage_artifact_path", f"action result artifact for `{label}` has no path")
    path = Path(artifact_path)
    if not path.is_absolute():
        path = Path(project_root) / path
    if not path.is_file():
        return _error("missing_stage_artifact", f"action result artifact does not exist: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _error("invalid_stage_artifact", f"action result artifact is not valid JSON: {exc.__class__.__name__}")
    expected_sha = str(artifact.get("sha256") or "").strip()
    if expected_sha and serialized_metadata(loaded)["sha256"] != expected_sha:
        return _error("stage_artifact_hash_mismatch", f"action result artifact hash mismatch for `{label}`")
    return {"ok": True, "source": "artifact", "label": label, "value": loaded, "artifact": artifact}


def readback_artifact_name(target: str, branch: str) -> str:
    normalized_branch = _normalize_readback_branch(branch)
    normalized_target = str(target or "dashboard").strip() or "dashboard"
    return f"{normalized_target}.{normalized_branch}.latest.json"


def readback_artifact_path(project_root: str | Path, target: str, branch: str) -> Path:
    return Path(project_root) / "artifacts" / "readback" / readback_artifact_name(target, branch)


def create_publish_safe_apply_plan(
    *,
    project_root: str,
    target: str,
    object_type: str,
    object_id: str = "",
    object_ids: list[str] | None = None,
    saved_readback_path: str = "",
    approved: bool = False,
    readback_mode: str = "minimal",
    user_request_text: str = "",
) -> dict[str, Any]:
    root = Path(project_root)
    normalized_type = _normalize_publish_object_type(object_type)
    method_spec = PUBLISH_OBJECT_METHODS.get(normalized_type)
    if not method_spec:
        return _publish_plan_error("unsupported_object_type", f"publish is not supported for object_type `{object_type}`")
    source_path = Path(saved_readback_path) if saved_readback_path else readback_artifact_path(root, target, "saved")
    if not source_path.is_absolute():
        source_path = root / source_path
    if not source_path.is_file():
        return _publish_plan_error("missing_saved_readback", f"saved readback artifact is required: {source_path}")
    saved_readback = json.loads(source_path.read_text(encoding="utf-8"))
    source_branch = str(saved_readback.get("branch") or "").strip().lower()
    if source_branch != "saved":
        return _publish_plan_error(
            "invalid_saved_readback",
            f"publish must be built from saved branch readback, got {source_branch or 'unknown'}",
        )
    requested_ids = [str(item).strip() for item in (object_ids or []) if str(item).strip()]
    if object_id:
        requested_ids.append(str(object_id).strip())
    requested_ids = list(dict.fromkeys(requested_ids))
    if not requested_ids:
        inferred = _saved_readback_identity(saved_readback, object_id="")
        if inferred.get("ambiguous"):
            return _publish_plan_error(
                "ambiguous_saved_readback",
                "object_id or object_ids is required when saved readback contains multiple objects",
            )
        if inferred.get("duplicate"):
            return _publish_plan_error("duplicate_saved_readback", "saved readback contains duplicate object entries")
        if inferred.get("object_id"):
            requested_ids = [inferred["object_id"]]
    if not requested_ids:
        return _publish_plan_error("missing_object_id", "object_id, object_ids, or saved readback entry id is required")

    actions: list[dict[str, Any]] = []
    publish_sources: list[dict[str, Any]] = []
    for requested_id in requested_ids:
        built = _publish_action_from_saved_readback(
            saved_readback=saved_readback,
            object_id=requested_id,
            source_path=source_path,
            method_spec=method_spec,
            readback_mode=readback_mode,
        )
        if not built["ok"]:
            return _publish_plan_error(built["error"]["category"], built["error"]["message"])
        actions.append(built["action"])
        publish_sources.append(built["publish_source"])

    plan = create_safe_apply_plan(
        project_root=str(root),
        actions=actions,
        approved=approved,
        user_request_text=user_request_text,
    )
    plan["ok"] = True
    plan["status"] = "publish_plan_created"
    plan["publish_sources"] = publish_sources
    plan["publish_source"] = publish_sources[0] if len(publish_sources) == 1 else {}
    plan["object_count"] = len(actions)
    return plan


def validate_safe_apply_plan(plan: dict[str, Any]) -> ValidationResult:
    preflight = validate_safe_apply_plan_exhaustive(plan)
    return ValidationResult(ok=preflight["ok"], issues=preflight["issues"])


def validate_safe_apply_plan_exhaustive(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    action_checks: list[dict[str, Any]] = []
    target_lock = plan.get("target_lock") if isinstance(plan.get("target_lock"), dict) else {}
    plan_target_lock_hash = str(target_lock.get("lock_hash") or "").strip()
    if not plan.get("approved"):
        issues.append("safe apply plan is not approved")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        issues.append("safe apply plan requires non-empty actions")
        return {"ok": False, "issues": issues, "actions": action_checks}
    if all(
        action.get("changed") is False and not action.get("publish_required")
        for action in actions
        if isinstance(action, dict)
    ):
        issues.append("safe apply plan has no changed actions")
    issues.extend(_transaction_group_issues(actions))
    issues.extend(_target_action_set_issues(target_lock, actions))
    for index, action in enumerate(actions):
        action_issues: list[str] = []
        payload = _payload_for_action(action)
        text = " ".join(str(action.get(key, "")) for key in ("action", "method")).lower()
        if any(term.lower() in text for term in DESTRUCTIVE_TERMS):
            action_issues.append(f"action {index} is destructive or permission-changing")
        if action.get("mode", "save") != "save":
            action_issues.append(f"action {index} top-level mode must remain save; payload carries save/publish")
        method = str(action.get("method") or "")
        if method and not is_write_method(method):
            action_issues.append(f"action {index} method is not a curated write method: {method}")
        if method:
            request_validation = validate_method_request(method, payload)
            if not request_validation["ok"]:
                action_issues.extend(
                    f"action {index} {method} request {issue}" for issue in request_validation["issues"]
                )
        action_issues.extend(_contract_issues(action=action, payload=payload, index=index))
        action_type = _action_type(action, payload)
        if action_type in {"update", "publish"}:
            object_id = _action_object_id(action, payload)
            if not object_id:
                action_issues.append(f"action {index} update/publish requires a known target object_id")
            action_target_lock_hash = str(action.get("target_lock_hash") or "").strip()
            if not plan_target_lock_hash:
                action_issues.append(f"action {index} update/publish requires a plan target_lock hash")
            elif action_target_lock_hash != plan_target_lock_hash:
                action_issues.append(f"action {index} target_lock_hash does not match the plan target_lock")
            target_lock_status = str(target_lock.get("status") or "").strip().lower()
            if target_lock_status in {"ambiguous", "mismatch"}:
                action_issues.append(
                    f"action {index} update/publish target_lock status must not be {target_lock_status}"
                )
            if not target_lock.get("target_objects"):
                locked_chart_id = str(target_lock.get("target_chart_id") or "").strip()
                locked_dashboard_id = str(target_lock.get("target_dashboard_id") or "").strip()
                if locked_chart_id and object_id and object_id != locked_chart_id:
                    action_issues.append(
                        f"action {index} target object_id {object_id} does not match locked chart {locked_chart_id}"
                    )
                if locked_dashboard_id and _is_dashboard_action(action) and object_id and object_id != locked_dashboard_id:
                    action_issues.append(
                        f"action {index} target object_id {object_id} does not match locked dashboard {locked_dashboard_id}"
                    )
        payload_mode = str(payload.get("mode") or action.get("mode", "save"))
        if payload_mode == "publish":
            action_issues.extend(_publish_source_issues(root=Path(str(plan.get("project_root") or ".")), action=action, index=index))
        elif payload_mode != "save":
            action_issues.append(f"action {index} payload mode must be save or guarded publish")
        if not action.get("requires_fresh_read", False):
            action_issues.append(f"action {index} is a blind write; fresh read is required")
        fresh_method = action.get("read_method") or action.get("fresh_read_method")
        if action.get("requires_fresh_read", False) and not fresh_method:
            action_issues.append(f"action {index} requires fresh_read_method/read_method")
        try:
            readback_mode = normalize_readback_mode(action.get("readback_mode"))
        except ValueError as exc:
            action_issues.append(f"action {index}: {exc}")
            readback_mode = "minimal"
        if readback_mode == "none" and not action.get("readback_justification"):
            action_issues.append(f"action {index} disables readback without readback_justification")
        if action_type == "create" and readback_mode == "none":
            action_issues.append(
                f"action {index} create requires an exact post-write object readback"
            )
        if readback_mode != "none" and not action.get("readback_required", False):
            action_issues.append(f"action {index} readback_required must be true unless readback_mode is none")
        readback_method = action.get("readback_method") or fresh_method
        if readback_mode != "none" and not readback_method:
            action_issues.append(f"action {index} readback requires readback_method or fresh_read_method")
        unsafe_names = find_unsafe_internal_names(payload)
        if unsafe_names:
            action_issues.append(
                f"action {index} has unsafe DataLens internal names: "
                + format_unsafe_internal_name_issues(unsafe_names)
            )
        if _is_dashboard_action(action):
            change_scope = str(action.get("change_scope") or "content").strip().lower()
            if change_scope not in {"content", "layout", "redesign"}:
                action_issues.append(f"action {index} change_scope must be content, layout, or redesign")
            action_issues.extend(_geometry_scope_contract_issues(action, index=index))
            current_dashboard = action.get("current_dashboard")
            if not isinstance(current_dashboard, dict):
                current_dashboard = action.get("baseline_dashboard")
            if _action_type(action, payload) != "create":
                action_issues.extend(
                    _dashboard_baseline_contract_issues(
                        action=action,
                        payload=payload,
                        current_dashboard=current_dashboard,
                        index=index,
                    )
                )
            dashboard_preflight = validate_dashboard_payload(
                payload,
                current_dashboard=current_dashboard if isinstance(current_dashboard, dict) else None,
            )
            for issue in dashboard_preflight.issues:
                if issue.severity == "error":
                    action_issues.append(
                        f"action {index} dashboard payload preflight {issue.rule}: {issue.path}: {issue.message}"
                    )
            from datalens_dev_mcp.pipeline.dashboard_object_granularity import (
                validate_semantic_role_object_mapping,
            )

            for finding in validate_semantic_role_object_mapping(payload):
                action_issues.append(
                    f"action {index} dashboard semantic mapping {finding.rule}: "
                    f"{finding.path}: {finding.message}"
                )
            if _has_object_granularity_manifest(payload):
                from datalens_dev_mcp.pipeline.dashboard_object_granularity import (
                    validate_dashboard_object_granularity,
                )

                object_graph = validate_dashboard_object_granularity(payload)
                for finding in object_graph.findings:
                    if finding.severity == "error":
                        action_issues.append(
                            f"action {index} dashboard object granularity {finding.rule}: "
                            f"{finding.path}: {finding.message}"
                        )
            if _has_selector_contract(payload):
                from datalens_dev_mcp.pipeline.selector_layout_contract import validate_selector_layout_contract

                selector_preflight = validate_selector_layout_contract(payload)
                for finding in selector_preflight.findings:
                    if finding.severity == "error":
                        action_issues.append(
                            f"action {index} selector layout contract {finding.rule}: {finding.path}: {finding.message}"
                        )
            if _has_kpi_contract(payload):
                from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract

                kpi_preflight = validate_kpi_indicator_contract(payload)
                for finding in kpi_preflight.findings:
                    if finding.severity == "error":
                        action_issues.append(
                            f"action {index} kpi indicator contract {finding.rule}: {finding.path}: {finding.message}"
                        )
            if _has_source_route_contract(payload):
                from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

                source_preflight = validate_source_route_decision(payload)
                for finding in source_preflight["findings"]:
                    action_issues.append(f"action {index} source route contract {finding}")
        if _is_editor_chart_action(action, payload):
            runtime_preflight = validate_editor_runtime_contract(
                payload,
                source=f"safe_apply.action[{index}]",
                allow_unknown_warnings=bool(
                    action.get("runtime_contract_warning_override")
                    and str(action.get("runtime_contract_override_note") or "").strip()
                ),
            )
            for finding in runtime_preflight["findings"]:
                if finding["severity"] == "error" or not runtime_preflight["allow_unknown_warnings"]:
                    action_issues.append(
                        "action "
                        f"{index} editor runtime contract {finding['rule']}: "
                        f"{finding['path']}:line {finding['line']}: {finding['message']}"
                    )
        if _is_wizard_chart_action(action, payload):
            action_issues.extend(_wizard_live_readback_contract_issues(action, payload, index=index))
            wizard_preflight = validate_wizard_visual_dataset_contract(payload)
            for finding in wizard_preflight.findings:
                if finding.severity == "error":
                    action_issues.append(
                        f"action {index} wizard contract {finding.rule}: {finding.path}: {finding.message}"
                    )
            dataset_readbacks = action.get("dataset_readbacks")
            if isinstance(dataset_readbacks, list):
                wizard_readback = validate_wizard_field_binding_against_dataset_readback(
                    payload,
                    dataset_readbacks,
                    source=f"safe_apply.action[{index}]",
                    strict=True,
                    enforce_role_types=bool(
                        action_type == "create"
                        or action.get("enforce_wizard_role_types")
                    ),
                )
                for finding in wizard_readback["findings"]:
                    if finding["severity"] == "error":
                        action_issues.append(
                            f"action {index} wizard live field binding {finding['rule']}: "
                            f"{finding['path']}: {finding['message']}"
                        )
            elif action_type == "create":
                action_issues.append(
                    f"action {index} Wizard creation requires dataset_readbacks for field existence and role-type validation"
                )
        if _is_table_chart_action(action, payload):
            from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract

            table_preflight = validate_native_table_contract(_native_table_payload_from_editor_payload(payload))
            for finding in table_preflight.findings:
                if finding.severity == "error":
                    action_issues.append(
                        f"action {index} native table contract {finding.rule}: {finding.path}: {finding.message}"
                    )
        if not _is_dashboard_action(action) and _has_kpi_contract(payload):
            from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract

            kpi_preflight = validate_kpi_indicator_contract(payload)
            for finding in kpi_preflight.findings:
                if finding.severity == "error":
                    action_issues.append(
                        f"action {index} kpi indicator contract {finding.rule}: {finding.path}: {finding.message}"
                    )
        if not _is_dashboard_action(action) and _has_source_route_contract(payload):
            from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

            source_preflight = validate_source_route_decision(payload)
            for finding in source_preflight["findings"]:
                action_issues.append(f"action {index} source route contract {finding}")
        for spec_path, spec in _iter_renderer_visual_specs(payload):
            from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

            visual_preflight = validate_visual_quality_contract(spec)
            for finding in visual_preflight.findings:
                if finding.severity == "error":
                    action_issues.append(
                        f"action {index} renderer visual quality {finding.rule}: "
                        f"{spec_path}{finding.path.removeprefix('$')}: {finding.message}"
                    )
        semantic_preflight = validate_payload_sql_performance(payload, source=f"safe_apply.action[{index}]")
        for issue in semantic_preflight["issues"]:
            action_issues.append(f"action {index} sql/performance preflight {issue}")
        action_issues.extend(_delta_v7_evidence_issues(action=action, index=index))
        issues.extend(action_issues)
        action_checks.append(
            {
                "index": index,
                "action": action.get("action"),
                "method": method,
                "object_id": _action_object_id(action, payload),
                "owner": _action_owner(action),
                "readback_mode": readback_mode,
                "ok": not action_issues,
                "issues": action_issues,
                "checks": {
                    "write_method": bool(method and is_write_method(method)),
                    "fresh_read_contract": bool(fresh_method),
                    "readback_contract": readback_mode == "none" or bool(readback_method),
                    "payload_contract": not any("payload_contract" in issue for issue in action_issues),
                    "source_owner": not any("source_owner" in issue for issue in action_issues),
                    "revision_guard": not any("revision_guard" in issue for issue in action_issues),
                    "requires_fresh_read": bool(action.get("requires_fresh_read", False)),
                    "readback_required": bool(action.get("readback_required", False)),
                    "sql_performance_semantics": bool(semantic_preflight["ok"]),
                },
            }
        )
    return {"ok": not issues, "issues": issues, "actions": action_checks}


def execute_safe_apply(
    plan: dict[str, Any],
    *,
    config: DataLensConfig | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    cfg = (config or DataLensConfig.from_env()).reload_canonical_env(
        reload_state="reloaded_before_safe_apply"
    )
    blocked: list[str] = []
    for action in plan.get("actions") or []:
        if isinstance(action, dict):
            blocked.extend(_runtime_write_gate_issues(cfg, _payload_for_action(action)))
    blocked = list(dict.fromkeys(blocked))
    preflight = validate_safe_apply_plan_exhaustive(plan)
    blocked.extend(preflight["issues"])
    if blocked:
        transaction_groups = _transaction_group_summary(plan, [])
        return {
            "executed": False,
            "status": "blocked",
            "proof_level": "source_static",
            "proof_levels": ["source_static"],
            "completed_action_count": 0,
            "completed_action_indices": [],
            "failed_action_index": None,
            "failed_action_indices": [],
            "skipped_action_indices": list(range(len(plan.get("actions") or []))),
            "blocked_reasons": blocked,
            "preflight": preflight,
            "actions": [],
            "result_contract": {
                "action_stage_result_shapes": ["inline", "artifact"],
                "full_rpc_envelopes": "artifact_backed",
                "downstream_reader": "load_safe_apply_stage_value",
                "partial_create_retry_requires_reconciliation": True,
            },
            "rollback": {"required": False, "available": False, "artifacts": []},
            "readback_artifacts": [],
            "transaction_groups": transaction_groups,
            "publish_allowed": False,
        }
    if client is None:
        from datalens_dev_mcp.api.client import DataLensApiClient

        client = DataLensApiClient(cfg)
    results = []
    root = Path(str(plan.get("project_root") or "."))
    run_id = safe_apply_run_id(plan)
    checks_by_index = {item["index"]: item for item in preflight["actions"]}
    for index, action in enumerate(plan["actions"]):
        payload = _payload_for_action(action)
        write_payload = payload
        action_result = _base_action_result(index=index, action=action, payload=payload, preflight=checks_by_index.get(index, {}))
        transaction_error = _publish_transaction_group_error(
            plan=plan,
            results=results,
            action_index=index,
            action=action,
            payload=payload,
        )
        if transaction_error:
            action_result["status"] = "failed"
            action_result["error"] = transaction_error
            results.append(action_result)
            break
        readback_mode = normalize_readback_mode(action.get("readback_mode"))
        fresh_method = action.get("read_method") or action.get("fresh_read_method")
        fresh_payload = action.get("fresh_read_payload") or {}
        action_type = _action_type(action, payload)
        try:
            if action_type == "create" and fresh_method == "getWorkbookEntries":
                paginated_fresh = _read_complete_workbook_entries_for_create(
                    client=client,
                    payload=fresh_payload,
                    target_lock_hash=str(action.get("target_lock_hash") or ""),
                )
                fresh = paginated_fresh["value"]
                action_result["fresh_read_pagination"] = paginated_fresh["evidence"]
                if not paginated_fresh["ok"]:
                    action_result["artifacts"]["pre_write"] = _write_safe_apply_envelope(
                        root=root,
                        run_id=run_id,
                        index=index,
                        label="pre_write",
                        value=fresh,
                    )
                    action_result["summaries"]["pre_write"] = _safe_apply_envelope_summary(
                        fresh,
                        readback_mode,
                    )
                    action_result["status"] = "failed"
                    action_result["error"] = paginated_fresh["error"]
                    results.append(action_result)
                    break
            else:
                fresh = _exclusive_read(client, fresh_method, fresh_payload) if fresh_method else {}
            guarded_existing_write = action_type in {"update", "publish"}
            dashboard_update = _is_dashboard_action(action) and guarded_existing_write
            if action_type == "create" and fresh_method == "getWorkbookEntries" and not fresh:
                action_result["status"] = "failed"
                action_result["error"] = {
                    "category": "fresh_create_reconciliation_incomplete",
                    "message": (
                        "create requires a non-empty getWorkbookEntries envelope with an explicit "
                        "entries array before write"
                    ),
                    "write_outcome": "no_write",
                    "retry_safe": True,
                }
                results.append(action_result)
                break
            if guarded_existing_write and not fresh:
                action_result["status"] = "failed"
                action_result["error"] = {
                    "category": "fresh_read_required",
                    "message": (
                        "update/publish requires a non-empty authoritative fresh read immediately before write; "
                        "only an explicit create action may use the creation-context exception"
                    ),
                }
                results.append(action_result)
                break
            if fresh:
                action_result["artifacts"]["pre_write"] = _write_safe_apply_envelope(
                    root=root,
                    run_id=run_id,
                    index=index,
                    label="pre_write",
                    value=fresh,
                )
                action_result["summaries"]["pre_write"] = _safe_apply_envelope_summary(fresh, readback_mode)
                action_result["revisions"]["pre_write"] = _revision_id(fresh)
                guard_error = _fresh_read_guard_error(action=action, payload=payload, fresh=fresh)
                if guard_error:
                    action_result["status"] = "failed"
                    action_result["error"] = guard_error
                    results.append(action_result)
                    break
                if action_type == "create":
                    reconciliation_error = _fresh_create_reconciliation_error(
                        action=action,
                        payload=payload,
                        fresh=fresh,
                    )
                    if reconciliation_error:
                        action_result["status"] = "failed"
                        action_result["error"] = reconciliation_error
                        results.append(action_result)
                        break
                overlay_result = apply_desired_overlay_to_fresh_readback(
                    action=action,
                    planned_payload=payload,
                    fresh_readback=fresh,
                )
                if not overlay_result["ok"]:
                    action_result["status"] = "failed"
                    action_result["error"] = overlay_result["error"]
                    results.append(action_result)
                    break
                write_payload = overlay_result["payload"]
                overlay_summary = overlay_result["summary"]
                if (
                    overlay_summary.get("fresh_geometry_preserved")
                    or overlay_summary.get("wizard_visualization_token")
                    or overlay_summary.get("change_scope") != "content"
                ):
                    action_result["overlay_application"] = overlay_summary
                if dashboard_update:
                    dashboard_error = _fresh_dashboard_validation_error(
                        action=action,
                        payload=write_payload,
                        fresh=fresh,
                    )
                    if dashboard_error:
                        action_result["status"] = "failed"
                        action_result["error"] = dashboard_error
                        results.append(action_result)
                        break
            cfg = cfg.reload_canonical_env(reload_state="reloaded_immediately_before_write")
            runtime_gate_issues = _runtime_write_gate_issues(cfg, write_payload)
            if runtime_gate_issues:
                action_result["status"] = "failed"
                action_result["error"] = {
                    "category": "runtime_write_disabled",
                    "message": "; ".join(runtime_gate_issues),
                }
                results.append(action_result)
                break
            action_result["write_attempted"] = True
            write_result = client.rpc(action["method"], write_payload)
            action_result["artifacts"]["write_result"] = _write_safe_apply_envelope(
                root=root,
                run_id=run_id,
                index=index,
                label="write_result",
                value=write_result,
            )
            action_result["summaries"]["write_result"] = _safe_apply_envelope_summary(write_result, readback_mode)
            action_result["revisions"]["write"] = _revision_id(write_result)
            if action_type == "create":
                created_identity = _object_identity(sanitize_response(write_result)).get("object_id", "")
                action_result["created_object_identity"] = created_identity
                if not created_identity:
                    action_result["status"] = "failed"
                    action_result["error"] = {
                        "category": "missing_created_identity",
                        "message": (
                            "create response did not return an object identity; exact post-write readback "
                            "cannot be addressed"
                        ),
                        "write_outcome": "unknown",
                        "retry_safe": False,
                    }
                    results.append(action_result)
                    break
            if readback_mode != "none" and fresh_method:
                readback_method = str(action.get("readback_method") or fresh_method)
                readback_payload = deepcopy(action.get("readback_payload") or fresh_payload)
                if action_type == "create":
                    readback_request = _created_object_readback_request(
                        action=action,
                        write_result=write_result,
                        method=readback_method,
                        payload=readback_payload,
                    )
                    if not readback_request["ok"]:
                        action_result["status"] = "failed"
                        action_result["error"] = readback_request["error"]
                        results.append(action_result)
                        break
                    readback_method = str(readback_request["method"])
                    readback_payload = dict(readback_request["payload"])
                readback = _exclusive_read(
                    client,
                    readback_method,
                    readback_payload,
                )
                action_result["artifacts"]["readback"] = _write_safe_apply_envelope(
                    root=root,
                    run_id=run_id,
                    index=index,
                    label="readback",
                    value=readback,
                )
                action_result["summaries"]["readback"] = _safe_apply_envelope_summary(readback, readback_mode)
                action_result["revisions"]["readback"] = _revision_id(readback)
                readback_verification = _post_write_readback_verification(
                    action=action,
                    payload=payload,
                    fresh=fresh,
                    write_payload=write_payload,
                    write_result=write_result,
                    readback=readback,
                )
                action_result["readback_verification"] = {
                    key: value
                    for key, value in readback_verification.items()
                    if key != "error"
                }
                readback_error = readback_verification.get("error")
                if readback_error:
                    action_result["status"] = "failed"
                    action_result["error"] = readback_error
                    results.append(action_result)
                    break
            action_result["executed"] = True
            action_result["status"] = "executed"
        except Exception as exc:  # noqa: BLE001
            action_result["executed"] = False
            action_result["status"] = "failed"
            action_result["error"] = _classify_safe_apply_error(
                exc,
                write_attempted=bool(action_result.get("write_attempted")),
            )
            results.append(action_result)
            break
        results.append(action_result)
    failed_index = next((item["index"] for item in results if item.get("status") == "failed"), None)
    completed_indices = [int(item["index"]) for item in results if item.get("executed")]
    completed_count = len(completed_indices)
    failed_indices = [] if failed_index is None else [int(failed_index)]
    observed_indices = {int(item["index"]) for item in results}
    skipped_indices = [
        index
        for index in range(len(plan.get("actions") or []))
        if index not in observed_indices
    ]
    status = "completed"
    if failed_index is not None:
        status = "partial" if completed_count else "failed"
    proof_levels = _result_proof_levels(results, plan.get("actions") or [])
    result = {
        "executed": failed_index is None,
        "status": status,
        "proof_level": "controlled_live_write" if completed_count else "source_static",
        "proof_levels": proof_levels,
        "completed_action_count": completed_count,
        "completed_action_indices": completed_indices,
        "failed_action_index": failed_index,
        "failed_action_indices": failed_indices,
        "skipped_action_indices": skipped_indices,
        "blocked_reasons": [],
        "run_id": run_id,
        "actions": results,
        "result_contract": {
            "action_stage_result_shapes": ["inline", "artifact"],
            "full_rpc_envelopes": "artifact_backed",
            "downstream_reader": "load_safe_apply_stage_value",
            "partial_create_retry_requires_reconciliation": True,
        },
        "rollback": _rollback_summary(results, failed_index=failed_index),
        "retry_resume": _retry_resume_summary(plan, results, failed_index=failed_index),
        "readback_artifacts": _readback_artifacts(results),
    }
    result["transaction_groups"] = _transaction_group_summary(plan, results)
    result["publish_allowed"] = bool(
        result["transaction_groups"]
        and all(item["publish_allowed"] for item in result["transaction_groups"])
    )
    result["execution_artifact"] = _write_safe_apply_execution_manifest(
        root=root,
        run_id=run_id,
        plan=plan,
        status=status,
        results=results,
    )
    return result


def _exclusive_read(client: Any, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    reader = getattr(client, "rpc_exclusive_read", None)
    if callable(reader):
        return reader(method, payload)
    return client.rpc(method, payload)


def write_safe_apply_plan(path: str | Path, plan: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _base_action_result(
    *,
    index: int,
    action: dict[str, Any],
    payload: dict[str, Any],
    preflight: dict[str, Any],
) -> dict[str, Any]:
    return {
        "index": index,
        "action": action.get("action"),
        "method": action.get("method"),
        "transaction_group_id": str(action.get("transaction_group_id") or "delivery"),
        "change_scope": str(action.get("change_scope") or "content"),
        "object_id": _action_object_id(action, payload),
        "executed": False,
        "write_attempted": False,
        "changed": action.get("changed", True),
        "status": "planned",
        "readback_mode": normalize_readback_mode(action.get("readback_mode")),
        "preflight_checks": _compact_preflight(preflight),
        "revisions": {"pre_write": "", "write": "", "readback": ""},
        "artifacts": {},
        "summaries": {},
    }


def _compact_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    checks = preflight.get("checks") if isinstance(preflight.get("checks"), dict) else {}
    compact = {
        "ok": bool(preflight.get("ok", False)),
        "issues": preflight.get("issues") or [],
        "write_method": bool(checks.get("write_method")),
        "fresh_read_contract": bool(checks.get("fresh_read_contract")),
        "readback_contract": bool(checks.get("readback_contract")),
    }
    owner = preflight.get("owner") or {}
    if owner and not (owner.get("generator") == "unknown" and not owner.get("source_path")):
        compact["owner"] = owner
    return compact


def safe_apply_run_id(plan: dict[str, Any]) -> str:
    return "safe_apply_" + serialized_metadata(safe_apply_run_binding(plan))["sha256"][:12]


def safe_apply_run_binding(plan: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical, replay-resistant binding for one guarded plan."""

    actions = [item for item in plan.get("actions") or [] if isinstance(item, dict)]
    approval = plan.get("approval_provenance") if isinstance(plan.get("approval_provenance"), dict) else {}
    target_lock = plan.get("target_lock") if isinstance(plan.get("target_lock"), dict) else {}
    return {
        "project_root": str(plan.get("project_root") or ""),
        "approved": bool(plan.get("approved")),
        "approval_provenance": {
            "approved": bool(approval.get("approved")),
            "approval_source": str(approval.get("approval_source") or ""),
            "approval_note": str(approval.get("approval_note") or plan.get("approval_note") or ""),
        },
        "request_intent": plan.get("request_intent") if isinstance(plan.get("request_intent"), dict) else {},
        "target_lock_hash": str(target_lock.get("lock_hash") or ""),
        "action_count": len(actions),
        "actions": [
            {"index": index, **_safe_apply_action_binding(action)}
            for index, action in enumerate(actions)
        ],
    }


def _safe_apply_run_id(plan: dict[str, Any]) -> str:
    return safe_apply_run_id(plan)


def _safe_apply_action_binding(action: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_for_action(action)
    approval = action.get("approval_provenance") if isinstance(action.get("approval_provenance"), dict) else {}
    binding = {
        "action": str(action.get("action") or ""),
        "method": str(action.get("method") or ""),
        "object_id": _action_object_id(action, payload),
        "transaction_group_id": str(action.get("transaction_group_id") or "delivery"),
        "change_scope": str(action.get("change_scope") or "content"),
        "semantic_role": str(action.get("semantic_role") or ""),
        "shared_object_key": str(action.get("shared_object_key") or ""),
        "mode": str(payload.get("mode") or action.get("mode") or "save").strip().lower(),
        "expected_revision": _expected_revision(action, payload),
        "payload_sha256": serialized_metadata(payload)["sha256"],
        "desired_overlay_sha256": serialized_metadata(action.get("desired_overlay") or {})["sha256"],
        "readback_branch": str((action.get("readback_contract") or {}).get("branch") or "").strip().lower(),
        "target_lock_hash": str(action.get("target_lock_hash") or ""),
        "approval_provenance": {
            "approved": bool(approval.get("approved")),
            "approval_source": str(approval.get("approval_source") or ""),
            "approval_note": str(approval.get("approval_note") or ""),
        },
    }
    saved_source = _saved_source_binding(action)
    if saved_source:
        binding["saved_source"] = saved_source
    return binding


def _saved_source_binding(action: dict[str, Any]) -> dict[str, Any]:
    source_path = str(action.get("saved_readback_path") or "").strip()
    if not source_path:
        return {}
    path = Path(source_path)
    payload = _payload_for_action(action)
    return {
        "path": str(path),
        "sha256": _raw_file_sha256(path) if path.is_file() else "",
        "object_id": _action_object_id(action, payload),
        "revision_id": str(action.get("expected_saved_rev_id") or "").strip(),
        "source_branch": str(action.get("source_branch") or "").strip().lower(),
    }


def _write_safe_apply_execution_manifest(
    *,
    root: Path,
    run_id: str,
    plan: dict[str, Any],
    status: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    plan_actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    result_by_index = {
        int(item.get("index") or 0): item
        for item in results
        if isinstance(item, dict)
    }
    manifest_actions: list[dict[str, Any]] = []
    for index, action in enumerate(plan_actions):
        if not isinstance(action, dict):
            continue
        action_result = result_by_index.get(index, {})
        binding = _safe_apply_action_binding(action)
        artifacts = action_result.get("artifacts") if isinstance(action_result.get("artifacts"), dict) else {}
        summaries = action_result.get("summaries") if isinstance(action_result.get("summaries"), dict) else {}
        readback_summary = summaries.get("readback") if isinstance(summaries.get("readback"), dict) else {}
        readback_identity = (
            readback_summary.get("identity") if isinstance(readback_summary.get("identity"), dict) else {}
        )
        manifest_actions.append(
            {
                "index": index,
                **binding,
                "status": str(action_result.get("status") or "not_run"),
                "executed": bool(action_result.get("executed")),
                "write_result": _stage_artifact_binding(artifacts.get("write_result")),
                "readback": {
                    **_stage_artifact_binding(artifacts.get("readback")),
                    "branch": binding["readback_branch"],
                    "object_id": str(readback_identity.get("object_id") or ""),
                    "revision_id": str(readback_summary.get("revision_id") or ""),
                },
            }
        )
    manifest = {
        "schema_version": "datalens.safe_apply_execution_evidence.v1",
        "generated_at": now_utc(),
        "project_root": str(plan.get("project_root") or root),
        "run_id": run_id,
        "run_binding": safe_apply_run_binding(plan),
        "status": status,
        "actions": manifest_actions,
    }
    path = root / "artifacts" / "safe_apply" / run_id / "execution_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = stable_json_text(sanitize_response(manifest)) + "\n"
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "serialized_bytes": len(text.encode("utf-8")),
    }


def _stage_artifact_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    path = Path(str(value.get("path") or ""))
    return {
        "path": str(path) if str(path) != "." else "",
        "sha256": _raw_file_sha256(path) if path.is_file() else "",
    }


def _raw_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_safe_apply_envelope(
    *,
    root: Path,
    run_id: str,
    index: int,
    label: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    sanitized = sanitize_response(value)
    metadata = serialized_metadata(sanitized)
    path = root / "artifacts" / "safe_apply" / run_id / f"{index:02d}.{label}.{metadata['sha256'][:12]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = stable_json_text(sanitized) + "\n"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), **metadata}


def _safe_apply_envelope_summary(value: dict[str, Any], readback_mode: str) -> dict[str, Any]:
    sanitized = sanitize_response(value)
    metadata = serialized_metadata(sanitized)
    counts = {key: count for key, count in _shape_counts(sanitized).items() if count}
    summary: dict[str, Any] = {
        "identity": _object_identity(sanitized),
        "revision_id": _revision_id(sanitized),
        "saved_id": _saved_id(sanitized),
        "status": _status_value(sanitized),
        "counts": counts,
        "sha256": metadata["sha256"],
    }
    if readback_mode == "debug":
        text = stable_json_text(sanitized)
        summary["debug_excerpt"] = text[:SAFE_APPLY_DEBUG_INLINE_CHAR_CAP]
        summary["debug_truncated"] = len(text) > SAFE_APPLY_DEBUG_INLINE_CHAR_CAP
        summary["debug_inline_char_cap"] = SAFE_APPLY_DEBUG_INLINE_CHAR_CAP
    return summary


def _fresh_read_guard_error(action: dict[str, Any], payload: dict[str, Any], fresh: dict[str, Any]) -> dict[str, str] | None:
    action_type = _action_type(action, payload)
    expected_object_id = _action_object_id(action, payload)
    actual_object_id = _object_identity(sanitize_response(fresh)).get("object_id", "")
    if action_type in {"update", "publish"} and not expected_object_id:
        return {
            "category": "missing_target_identity",
            "message": "update/publish requires a known target object_id before fresh read validation",
        }
    if expected_object_id and not actual_object_id:
        return {
            "category": "missing_fresh_identity",
            "message": "fresh read did not return the target object identity",
        }
    if expected_object_id and actual_object_id != expected_object_id:
        return {
            "category": "object_id_mismatch",
            "message": f"fresh read object_id {actual_object_id} does not match planned object_id {expected_object_id}",
        }
    expected_revision = _expected_revision(action, payload)
    actual_revision = _revision_id(sanitize_response(fresh))
    if action_type in {"update", "publish"} and not expected_revision:
        return {
            "category": "missing_expected_revision",
            "message": "update/publish requires an expected revision bound to the safe-apply plan",
        }
    if expected_revision and not actual_revision:
        return {
            "category": "missing_fresh_revision",
            "message": "fresh read did not return a revision required by the safe-apply plan",
        }
    if expected_revision and actual_revision and actual_revision != expected_revision:
        return {
            "category": "stale_revision",
            "message": "fresh read revision does not match planned revision",
        }
    return None


def _read_complete_workbook_entries_for_create(
    *,
    client: Any,
    payload: dict[str, Any],
    target_lock_hash: str,
) -> dict[str, Any]:
    base_payload = deepcopy(payload)
    initial_cursor = str(
        base_payload.get("pageToken")
        or base_payload.get("page_token")
        or ""
    ).strip()
    initial_page = base_payload.get("page")
    if initial_cursor or (
        initial_page not in (None, "", 0, 1, 1.0)
    ):
        evidence = _create_inventory_pagination_evidence(
            complete=False,
            page_count=0,
            entry_count=0,
            duplicate_entry_count=0,
            cursor_hashes=[],
            target_lock_hash=target_lock_hash,
            request_payload=base_payload,
            error_category="fresh_create_pagination_requires_first_page",
        )
        return {
            "ok": False,
            "value": {"entries": [], "pagination": evidence},
            "evidence": evidence,
            "error": {
                "category": "fresh_create_pagination_requires_first_page",
                "message": "fresh create reconciliation must start from the first workbook entries page",
                "write_outcome": "no_write",
                "retry_safe": True,
            },
        }

    request_payload = deepcopy(base_payload)
    request_payload.pop("pageToken", None)
    request_payload.pop("page_token", None)
    entries_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    seen_cursors: set[str] = set()
    cursor_hashes: list[str] = []
    duplicate_entry_count = 0
    page_count = 0

    def finish_error(category: str, message: str) -> dict[str, Any]:
        evidence = _create_inventory_pagination_evidence(
            complete=False,
            page_count=page_count,
            entry_count=len(entries_by_id),
            duplicate_entry_count=duplicate_entry_count,
            cursor_hashes=cursor_hashes,
            target_lock_hash=target_lock_hash,
            request_payload=base_payload,
            error_category=category,
        )
        return {
            "ok": False,
            "value": {
                "entries": [
                    item
                    for _entry_id, (_serialized, item) in sorted(entries_by_id.items())
                ],
                "pagination": evidence,
            },
            "evidence": evidence,
            "error": {
                "category": category,
                "message": message,
                "write_outcome": "no_write",
                "retry_safe": True,
            },
        }

    while True:
        raw_page = _exclusive_read(client, "getWorkbookEntries", request_payload)
        page_count += 1
        page = sanitize_response(raw_page)
        while isinstance(page, dict) and isinstance(page.get("result"), dict):
            page = page["result"]
        if isinstance(page, dict) and isinstance(page.get("response"), dict):
            page = page["response"]
        raw_entries = page.get("entries") if isinstance(page, dict) else None
        if not isinstance(raw_entries, list) or not all(
            isinstance(entry, dict) for entry in raw_entries
        ):
            return finish_error(
                "fresh_create_pagination_incomplete_page",
                f"getWorkbookEntries page {page_count} did not return an entries array of objects",
            )
        for entry in raw_entries:
            normalized_entry = json.loads(stable_json_text(sanitize_response(entry)))
            entry_id = _candidate_object_id(normalized_entry)
            if not entry_id:
                return finish_error(
                    "fresh_create_pagination_entry_identity_missing",
                    f"getWorkbookEntries page {page_count} contains an entry without identity",
                )
            serialized_entry = stable_json_text(normalized_entry)
            previous = entries_by_id.get(entry_id)
            if previous is not None:
                if previous[0] != serialized_entry:
                    return finish_error(
                        "fresh_create_pagination_duplicate_conflict",
                        (
                            f"workbook entry {entry_id} differs across pagination pages; "
                            "the inventory is not a stable reconciliation source"
                        ),
                    )
                duplicate_entry_count += 1
                continue
            entries_by_id[entry_id] = (serialized_entry, normalized_entry)
            if len(entries_by_id) > SAFE_APPLY_CREATE_INVENTORY_MAX_ENTRIES:
                return finish_error(
                    "fresh_create_pagination_entry_cap_exceeded",
                    (
                        "workbook entries pagination exceeded the bounded entry cap "
                        f"of {SAFE_APPLY_CREATE_INVENTORY_MAX_ENTRIES}"
                    ),
                )

        next_cursor = str(page.get("nextPageToken") or "").strip()
        if not next_cursor:
            evidence = _create_inventory_pagination_evidence(
                complete=True,
                page_count=page_count,
                entry_count=len(entries_by_id),
                duplicate_entry_count=duplicate_entry_count,
                cursor_hashes=cursor_hashes,
                target_lock_hash=target_lock_hash,
                request_payload=base_payload,
                error_category="",
            )
            return {
                "ok": True,
                "value": {
                    "entries": [
                        item
                        for _entry_id, (_serialized, item) in sorted(entries_by_id.items())
                    ],
                    "pagination": evidence,
                },
                "evidence": evidence,
            }
        if next_cursor in seen_cursors:
            return finish_error(
                "fresh_create_pagination_cursor_cycle",
                "getWorkbookEntries pagination repeated a cursor before reaching a complete inventory",
            )
        seen_cursors.add(next_cursor)
        cursor_hashes.append(hashlib.sha256(next_cursor.encode("utf-8")).hexdigest())
        if page_count >= SAFE_APPLY_CREATE_INVENTORY_MAX_PAGES:
            return finish_error(
                "fresh_create_pagination_page_cap_exceeded",
                (
                    "workbook entries pagination exceeded the bounded page cap "
                    f"of {SAFE_APPLY_CREATE_INVENTORY_MAX_PAGES}"
                ),
            )
        request_payload = deepcopy(base_payload)
        request_payload.pop("pageToken", None)
        request_payload.pop("page_token", None)
        first_page = int(base_payload.get("page") or 1)
        request_payload["page"] = first_page + page_count


def _create_inventory_pagination_evidence(
    *,
    complete: bool,
    page_count: int,
    entry_count: int,
    duplicate_entry_count: int,
    cursor_hashes: list[str],
    target_lock_hash: str,
    request_payload: dict[str, Any],
    error_category: str,
) -> dict[str, Any]:
    return {
        "schema_version": "datalens.safe_apply.create_inventory_pagination.v1",
        "method": "getWorkbookEntries",
        "complete": complete,
        "page_count": page_count,
        "entry_count": entry_count,
        "duplicate_entry_count": duplicate_entry_count,
        "cursor_count": len(cursor_hashes),
        "cursor_chain_sha256": serialized_metadata(cursor_hashes)["sha256"],
        "initial_request_sha256": serialized_metadata(request_payload)["sha256"],
        "target_lock_hash": target_lock_hash,
        "max_pages": SAFE_APPLY_CREATE_INVENTORY_MAX_PAGES,
        "max_entries": SAFE_APPLY_CREATE_INVENTORY_MAX_ENTRIES,
        "merge_order": "entry_id_ascending",
        "error_category": error_category,
    }


def _fresh_create_reconciliation_error(
    *,
    action: dict[str, Any],
    payload: dict[str, Any],
    fresh: dict[str, Any],
) -> dict[str, Any] | None:
    fresh_method = str(action.get("read_method") or action.get("fresh_read_method") or "")
    if fresh_method != "getWorkbookEntries":
        return None
    fresh_payload = (
        action.get("fresh_read_payload")
        if isinstance(action.get("fresh_read_payload"), dict)
        else {}
    )
    workbook_id = str(
        fresh_payload.get("workbookId")
        or payload.get("workbookId")
        or (
            payload.get("entry", {}).get("workbookId")
            if isinstance(payload.get("entry"), dict)
            else ""
        )
        or ""
    ).strip()
    evidence_validation = validate_entries_reconciliation_evidence(
        sanitize_response(fresh),
        expected_workbook_id=workbook_id,
    )
    if not evidence_validation["ok"]:
        return {
            "category": "fresh_create_reconciliation_incomplete",
            "message": "; ".join(evidence_validation["issues"]),
            "write_outcome": "no_write",
            "retry_safe": True,
        }
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    payload_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    internal_name = str(
        entry.get("name")
        or payload.get("name")
        or data.get("name")
        or payload_data.get("name")
        or ""
    ).strip()
    display_title = str(
        data.get("title")
        or payload_data.get("title")
        or payload.get("title")
        or internal_name
        or ""
    ).strip()
    if not internal_name and not display_title:
        return {
            "category": "fresh_create_reconciliation_target_missing",
            "message": "create payload has no stable name or title for fresh object reuse reconciliation",
            "write_outcome": "no_write",
            "retry_safe": True,
        }
    reconciliation = reconcile_partial_creates(
        workbook_id=workbook_id,
        planned_objects=[
            {
                "display_title": display_title,
                "internal_name": internal_name,
                "object_type": str(action.get("object_type") or "unknown"),
            }
        ],
        entries_payload=sanitize_response(fresh),
    )
    object_decision = reconciliation["objects"][0]
    if object_decision["recommended_action"] == "reuse":
        return {
            "category": "create_target_now_exists",
            "message": (
                "fresh workbook entries now contain a compatible object; create is blocked "
                "and the existing object must be reused"
            ),
            "existing_object_id": object_decision.get("existing_object_id") or "",
            "write_outcome": "no_write",
            "retry_safe": True,
        }
    if object_decision["recommended_action"] == "manual_review":
        return {
            "category": "fresh_create_reconciliation_ambiguous",
            "message": "fresh workbook entries contain duplicate compatible create targets",
            "write_outcome": "no_write",
            "retry_safe": True,
        }
    return None


def _fresh_dashboard_validation_error(
    *,
    action: dict[str, Any],
    payload: dict[str, Any],
    fresh: dict[str, Any],
) -> dict[str, Any] | None:
    validation = validate_dashboard_payload(payload, current_dashboard=sanitize_response(fresh))
    errors = [issue for issue in validation.issues if issue.severity == "error"]
    if not errors:
        return None
    detail = "; ".join(f"{issue.rule}: {issue.path}: {issue.message}" for issue in errors[:5])
    return {
        "category": "dashboard_fresh_validation_failed",
        "write_outcome": "no_write",
        "retry_safe": True,
        "message": f"fresh dashboard validation blocked write: {detail}"[:1000],
    }


def apply_desired_overlay_to_fresh_readback(
    *,
    action: dict[str, Any],
    planned_payload: dict[str, Any],
    fresh_readback: dict[str, Any],
) -> dict[str, Any]:
    """Merge intent onto authoritative fresh state before any update write."""

    overlay = action.get("desired_overlay")
    if not isinstance(overlay, dict):
        return {
            "ok": False,
            "error": {
                "category": "desired_overlay_missing",
                "message": "safe apply action requires desired_overlay separate from the fresh readback",
                "write_outcome": "no_write",
                "retry_safe": True,
            },
        }
    method = str(action.get("method") or "")
    if method == "updateWizardChart":
        wizard_error = _fresh_wizard_visualization_error(
            action=action,
            planned_payload=planned_payload,
            fresh=fresh_readback,
        )
        if wizard_error:
            return {"ok": False, "error": wizard_error}
    if _action_type(action, planned_payload) == "create":
        merged = deepcopy(planned_payload)
    else:
        merge_base = _request_shaped_fresh_readback(
            method=method,
            planned_payload=planned_payload,
            fresh_readback=fresh_readback,
        )
        merged = _merge_overlay_value(merge_base, overlay)
        for key in REQUEST_CONTROL_IDENTITY_KEYS:
            if key in planned_payload:
                merged[key] = deepcopy(planned_payload[key])

    scope = str(action.get("change_scope") or "content").strip().lower()
    if _is_dashboard_action(action):
        if scope == "content":
            _restore_fresh_geometry(
                merged,
                _request_shaped_fresh_readback(
                    method=method,
                    planned_payload=planned_payload,
                    fresh_readback=fresh_readback,
                ),
            )
        else:
            geometry_error = _geometry_expectation_error(action, fresh=fresh_readback, merged=merged)
            if geometry_error:
                return {"ok": False, "error": geometry_error}
    return {
        "ok": True,
        "payload": merged,
        "summary": {
            "source": "fresh_saved_readback",
            "change_scope": scope,
            "unknown_fields_preserved": True,
            "fresh_geometry_preserved": bool(_is_dashboard_action(action) and scope == "content"),
            "wizard_visualization_token": _wizard_visualization_token(merged) if method == "updateWizardChart" else "",
        },
    }


def _request_shaped_fresh_readback(
    *,
    method: str,
    planned_payload: dict[str, Any],
    fresh_readback: dict[str, Any],
) -> dict[str, Any]:
    if method not in {"updateDashboard", "updateEditorChart"}:
        return deepcopy(fresh_readback)
    if not isinstance(planned_payload.get("entry"), dict):
        return deepcopy(fresh_readback)
    candidate = _first_identity_candidate(deepcopy(fresh_readback))
    if not isinstance(candidate, dict) or not candidate:
        return deepcopy(fresh_readback)
    return {"entry": candidate}


def _merge_overlay_value(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = deepcopy(base)
        for key, value in overlay.items():
            merged[key] = _merge_overlay_value(base.get(key), value) if key in base else deepcopy(value)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        base_identities = [_merge_identity(item) for item in base]
        overlay_identities = [_merge_identity(item) for item in overlay]
        if all(base_identities) and all(overlay_identities):
            overlay_by_id = {identity: item for identity, item in zip(overlay_identities, overlay)}
            merged_list = [
                _merge_overlay_value(item, overlay_by_id[identity]) if identity in overlay_by_id else deepcopy(item)
                for identity, item in zip(base_identities, base)
            ]
            known = set(base_identities)
            merged_list.extend(
                deepcopy(item)
                for identity, item in zip(overlay_identities, overlay)
                if identity not in known
            )
            return merged_list
    return deepcopy(overlay)


def _merge_identity(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("i", "id", "entryId", "chartId", "dashboardId", "guid"):
        if str(value.get(key) or "").strip():
            return f"{key}:{str(value[key]).strip()}"
    return ""


def _geometry_nodes(value: Any) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            identity = _merge_identity(item)
            if identity and any(key in item for key in ("x", "y", "w", "h")):
                nodes[identity] = {key: deepcopy(item[key]) for key in ("x", "y", "w", "h") if key in item}
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return nodes


def _restore_fresh_geometry(merged: dict[str, Any], fresh: dict[str, Any]) -> None:
    geometry = _geometry_nodes(fresh)

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            identity = _merge_identity(item)
            if identity in geometry:
                item.update(deepcopy(geometry[identity]))
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(merged)


def _geometry_scope_contract_issues(action: dict[str, Any], *, index: int) -> list[str]:
    scope = str(action.get("change_scope") or "content").strip().lower()
    if scope == "content":
        return []
    expectations = action.get("geometry_expectations")
    if not isinstance(expectations, list) or not expectations:
        return [
            f"action {index} change_scope={scope} requires non-empty geometry_expectations with expected_old/expected_new"
        ]
    issues: list[str] = []
    for expectation_index, item in enumerate(expectations):
        item = item if isinstance(item, dict) else {}
        item_id = str(item.get("item_id") or "").strip()
        old = item.get("expected_old") if isinstance(item.get("expected_old"), dict) else {}
        new = item.get("expected_new") if isinstance(item.get("expected_new"), dict) else {}
        if not item_id or any(key not in old or key not in new for key in ("x", "y", "w", "h")):
            issues.append(
                f"action {index} geometry_expectations[{expectation_index}] requires item_id and x/y/w/h in expected_old/expected_new"
            )
    return issues


def _geometry_expectation_error(
    action: dict[str, Any],
    *,
    fresh: dict[str, Any],
    merged: dict[str, Any],
) -> dict[str, Any] | None:
    fresh_nodes = _geometry_nodes(fresh)
    merged_nodes = _geometry_nodes(merged)
    for item in action.get("geometry_expectations") or []:
        if not isinstance(item, dict):
            continue
        identity = f"i:{str(item.get('item_id') or '').strip()}"
        expected_old = item.get("expected_old") or {}
        expected_new = item.get("expected_new") or {}
        if fresh_nodes.get(identity) != expected_old or merged_nodes.get(identity) != expected_new:
            return {
                "category": "geometry_expectation_mismatch",
                "message": (
                    f"fresh saved geometry for {item.get('item_id')!r} does not match explicit expected_old/new contract"
                ),
                "write_outcome": "no_write",
                "retry_safe": True,
            }
    return None


def _wizard_live_readback_contract_issues(
    action: dict[str, Any],
    payload: dict[str, Any],
    *,
    index: int,
) -> list[str]:
    method = str(action.get("method") or "")
    token = _wizard_visualization_token(payload)
    if method == "createWizardChart":
        if not token or not is_supported_wizard_visualization(token):
            return [
                f"action {index} Wizard creation requires one of the supported canonical visualization IDs"
            ]
        return []
    if method != "updateWizardChart":
        return []
    issues: list[str] = []
    fresh_method = str(action.get("fresh_read_method") or action.get("read_method") or "")
    fresh_payload = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    if fresh_method != "getWizardChart":
        issues.append(f"action {index} Wizard update requires fresh getWizardChart")
    if str(fresh_payload.get("branch") or "").strip().lower() != "saved":
        issues.append(f"action {index} Wizard update requires fresh saved-branch readback")
    return issues


def _fresh_wizard_visualization_error(
    *,
    action: dict[str, Any],
    planned_payload: dict[str, Any],
    fresh: dict[str, Any],
) -> dict[str, Any] | None:
    planned_token = _wizard_visualization_token(planned_payload)
    fresh_token = _wizard_visualization_token(fresh)
    if not fresh_token:
        return {
            "category": "wizard_live_visualization_token_missing",
            "message": "fresh getWizardChart saved readback did not expose the existing visualization token",
            "write_outcome": "no_write",
            "retry_safe": True,
        }
    if planned_token and planned_token != fresh_token:
        return {
            "category": "wizard_visualization_token_mismatch",
            "message": (
                f"planned Wizard visualization token {planned_token!r} does not match fresh saved token {fresh_token!r}"
            ),
            "write_outcome": "no_write",
            "retry_safe": True,
        }
    return None


def _wizard_visualization_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("visualizationId", "visualization_id"):
            if str(value.get(key) or "").strip():
                return str(value[key]).strip()
        visualization = value.get("visualization")
        if isinstance(visualization, dict) and str(visualization.get("id") or "").strip():
            return str(visualization["id"]).strip()
        for item in value.values():
            found = _wizard_visualization_token(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _wizard_visualization_token(item)
            if found:
                return found
    return ""


def _created_object_readback_request(
    *,
    action: dict[str, Any],
    write_result: dict[str, Any],
    method: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    created_object_id = _object_identity(sanitize_response(write_result)).get("object_id", "")
    if not created_object_id:
        return {
            "ok": False,
            "error": {
                "category": "missing_created_identity",
                "message": "create response did not return an object identity",
                "write_outcome": "unknown",
                "retry_safe": False,
            },
        }
    readback_payload = deepcopy(payload)
    id_key = CREATE_READBACK_ID_KEYS.get(method)
    if id_key:
        readback_payload[id_key] = created_object_id
    elif method == "getWorkbookEntries":
        if not str(readback_payload.get("workbookId") or "").strip():
            fresh_payload = (
                action.get("fresh_read_payload")
                if isinstance(action.get("fresh_read_payload"), dict)
                else {}
            )
            workbook_id = str(fresh_payload.get("workbookId") or "").strip()
            if workbook_id:
                readback_payload["workbookId"] = workbook_id
        if not str(readback_payload.get("workbookId") or "").strip():
            return {
                "ok": False,
                "error": {
                    "category": "created_readback_not_addressable",
                    "message": "getWorkbookEntries create readback requires workbookId",
                    "write_outcome": "written_unverified",
                    "retry_safe": False,
                },
            }
    else:
        return {
            "ok": False,
            "error": {
                "category": "created_readback_not_addressable",
                "message": (
                    f"readback method {method or '<missing>'} cannot address or enumerate the "
                    "created object deterministically"
                ),
                "write_outcome": "written_unverified",
                "retry_safe": False,
            },
        }
    return {
        "ok": True,
        "method": method,
        "payload": readback_payload,
        "created_object_id": created_object_id,
    }


def _post_write_readback_verification(
    *,
    action: dict[str, Any],
    payload: dict[str, Any],
    fresh: dict[str, Any],
    write_payload: dict[str, Any],
    write_result: dict[str, Any],
    readback: dict[str, Any],
) -> dict[str, Any]:
    action_type = _action_type(action, payload)
    expected_object_id = _action_object_id(action, payload)
    created_object_id = ""
    created_readback_object: dict[str, Any] | None = None
    sanitized = sanitize_response(readback)
    if action_type == "create":
        created_object_id = _object_identity(sanitize_response(write_result)).get("object_id", "")
        if created_object_id:
            created_readback_object = _find_readback_object_by_identity(
                sanitized,
                object_id=created_object_id,
                identity_key=CREATE_READBACK_ID_KEYS.get(
                    str(action.get("readback_method") or action.get("fresh_read_method") or "")
                ),
            )
        if created_readback_object is not None:
            sanitized = created_readback_object
        expected_object_id = created_object_id
    actual_object_id = _object_identity(sanitized).get("object_id", "")
    fresh_revision = _revision_id(sanitize_response(fresh))
    write_revision = _revision_id(sanitize_response(write_result))
    readback_revision = _revision_id(sanitized)
    content_equivalent = _write_payload_matches_readback(
        method=str(action.get("method") or ""),
        write_payload=write_payload,
        readback=sanitized,
    )
    api_noop_proven = _api_noop_proven(
        action_type=action_type,
        method=str(action.get("method") or ""),
        payload=payload,
        fresh=fresh,
        write_payload=write_payload,
        write_result=write_result,
        readback=readback,
    )
    verification: dict[str, Any] = {
        "verified": False,
        "content_equivalent": content_equivalent,
        "revision_advanced": bool(
            fresh_revision and readback_revision and fresh_revision != readback_revision
        ),
        "publish_source_revision_matched": bool(
            action_type == "publish"
            and fresh_revision
            and readback_revision
            and fresh_revision == readback_revision
        ),
        "api_noop_proven": api_noop_proven,
        "fresh_revision": fresh_revision,
        "write_revision": write_revision,
        "readback_revision": readback_revision,
        "expected_object_id": expected_object_id,
        "actual_object_id": actual_object_id,
    }
    if action_type == "create" and not created_object_id:
        verification["error"] = {
            "category": "missing_created_identity",
            "message": "create response did not return an object identity",
        }
        return verification
    if action_type == "create" and created_readback_object is None:
        verification["error"] = {
            "category": "created_object_missing_from_readback",
            "message": (
                f"post-write readback did not contain the exact created object {created_object_id}"
            ),
        }
        return verification
    if expected_object_id and not actual_object_id:
        verification["error"] = {
            "category": "missing_readback_identity",
            "message": "post-write readback did not return an object identity",
        }
        return verification
    if expected_object_id and actual_object_id != expected_object_id:
        verification["error"] = {
            "category": "readback_object_id_mismatch",
            "message": f"post-write readback object_id {actual_object_id} does not match planned object_id {expected_object_id}",
        }
        return verification
    if action_type in {"update", "publish"} and not readback_revision:
        verification["error"] = {
            "category": "missing_readback_revision",
            "message": "post-write readback did not return a revision required by the safe-apply plan",
        }
        return verification
    if action_type in {"update", "publish"} and not content_equivalent:
        verification["error"] = {
            "category": "readback_content_mismatch",
            "message": "post-write readback is not content-equivalent to the intended merged write payload",
        }
        return verification
    if action_type == "create" and not content_equivalent:
        verification["error"] = {
            "category": "readback_content_mismatch",
            "message": "created object readback is not content-equivalent to the create payload",
        }
        return verification
    if action_type == "publish" and fresh_revision and readback_revision != fresh_revision:
        verification["error"] = {
            "category": "published_revision_source_mismatch",
            "message": "published readback revision does not match the verified saved source revision",
        }
        return verification
    if (
        action_type == "update"
        and fresh_revision
        and readback_revision == fresh_revision
        and not api_noop_proven
    ):
        verification["error"] = {
            "category": "readback_revision_not_advanced",
            "message": (
                "post-write readback still exposes the pre-write revision and the execution did not prove "
                "an API no-op"
            ),
        }
        return verification
    if (
        action_type in {"create", "update", "publish"}
        and write_revision
        and readback_revision != write_revision
        and (action_type == "create" or (fresh_revision and write_revision != fresh_revision))
    ):
        verification["error"] = {
            "category": "readback_write_revision_mismatch",
            "message": "post-write readback revision does not match the revision returned by the write",
        }
        return verification
    if _expected_revision(action, payload) and not readback_revision:
        verification["error"] = {
            "category": "missing_readback_revision",
            "message": "post-write readback did not return a revision required by the safe-apply plan",
        }
        return verification
    verification["verified"] = True
    return verification


_SEMANTIC_CONTROL_KEYS = {
    "branch",
    "chartId",
    "chart_id",
    "connectionId",
    "connection_id",
    "dashboardId",
    "dashboard_id",
    "datasetId",
    "dataset_id",
    "entryId",
    "entry_id",
    "id",
    "lockToken",
    "mode",
    "publishedId",
    "published_id",
    "revId",
    "rev_id",
    "revisionId",
    "revision_id",
    "savedId",
    "saved_id",
    "workbookId",
    "workbook_id",
}
_SEMANTIC_VOLATILE_METADATA_KEYS = {
    "createdAt",
    "created_at",
    "createdBy",
    "created_by",
    "revUpdatedAt",
    "rev_updated_at",
    "revUpdatedBy",
    "rev_updated_by",
    "updatedAt",
    "updated_at",
    "updatedBy",
    "updated_by",
}


def _write_payload_matches_readback(
    *,
    method: str,
    write_payload: dict[str, Any],
    readback: dict[str, Any],
) -> bool:
    expected = _semantic_object_payload(write_payload, method=method)
    actual = _semantic_object_payload(readback, method=method)
    return _semantic_subset(actual=actual, expected=expected)


def _semantic_object_payload(value: dict[str, Any], *, method: str) -> Any:
    current = deepcopy(value)
    while isinstance(current, dict) and isinstance(current.get("result"), dict):
        current = current["result"]
    if not isinstance(current, dict):
        return current

    if method == "updateDataset":
        data = current.get("data")
        if isinstance(data, dict) and isinstance(data.get("dataset"), dict):
            current = data["dataset"]
        elif isinstance(current.get("dataset"), dict):
            current = current["dataset"]
    elif method == "updateConnection":
        data = current.get("data")
        if isinstance(data, dict) and isinstance(data.get("connection"), dict):
            current = data["connection"]
        elif isinstance(current.get("connection"), dict):
            current = current["connection"]
    else:
        for key in ("entry", "dashboard", "chart", "object"):
            nested = current.get(key)
            if not isinstance(nested, dict):
                continue
            current = nested.get("entry") if isinstance(nested.get("entry"), dict) else nested
            break

    if not isinstance(current, dict):
        return current
    return {
        key: deepcopy(item)
        for key, item in sorted(current.items())
        if key not in _SEMANTIC_CONTROL_KEYS
        and key not in _SEMANTIC_VOLATILE_METADATA_KEYS
    }


def _semantic_subset(*, actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            key in actual and _semantic_subset(actual=actual[key], expected=value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _semantic_subset(actual=actual_item, expected=expected_item)
                for actual_item, expected_item in zip(actual, expected, strict=True)
            )
        )
    return actual == expected


def _api_noop_proven(
    *,
    action_type: str,
    method: str,
    payload: dict[str, Any],
    fresh: dict[str, Any],
    write_payload: dict[str, Any],
    write_result: dict[str, Any],
    readback: dict[str, Any],
) -> bool:
    sanitized_result = sanitize_response(write_result)
    status = str(sanitized_result.get("status") or sanitized_result.get("state") or "").strip().lower()
    explicit_noop = bool(
        sanitized_result.get("noop") is True
        or sanitized_result.get("noOp") is True
        or sanitized_result.get("changed") is False
        or status in {"noop", "no_op", "not_modified", "unchanged"}
    )
    if explicit_noop:
        return True
    payload_mode = str(payload.get("mode") or "").strip().lower()
    if action_type != "update" or payload_mode == "publish":
        return False
    intended = _semantic_object_payload(write_payload, method=method)
    before = _semantic_object_payload(fresh, method=method)
    after = _semantic_object_payload(readback, method=method)
    return intended == before == after


def _expected_revision(action: dict[str, Any], payload: dict[str, Any]) -> str:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    return str(
        action.get("expected_rev_id")
        or action.get("expected_saved_rev_id")
        or entry.get("revId")
        or entry.get("rev_id")
        or payload.get("revId")
        or payload.get("revisionId")
        or ""
    ).strip()


def _action_proof_levels(action_result: dict[str, Any], plan_action: dict[str, Any] | None = None) -> list[str]:
    levels = ["source_static"]
    artifacts = action_result.get("artifacts") if isinstance(action_result.get("artifacts"), dict) else {}
    if artifacts.get("pre_write"):
        levels.append("live_read_only_api")
    if action_result.get("write_attempted"):
        levels.append("controlled_live_write")
    if artifacts.get("readback"):
        readback_payload = plan_action.get("readback_payload") if isinstance(plan_action, dict) else {}
        branch = readback_payload.get("branch") if isinstance(readback_payload, dict) else ""
        levels.append(proof_level_for_readback_branch(str(branch or "saved")))
    if action_result.get("executed"):
        levels.append("controlled_live_write")
    return list(dict.fromkeys(levels))


def _result_proof_levels(results: list[dict[str, Any]], plan_actions: list[dict[str, Any]]) -> list[str]:
    levels = ["source_static"]
    for action in results:
        index = int(action.get("index") or 0)
        plan_action = plan_actions[index] if 0 <= index < len(plan_actions) and isinstance(plan_actions[index], dict) else {}
        levels.extend(_action_proof_levels(action, plan_action))
    return list(dict.fromkeys(levels))


def _readback_artifacts(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts = []
    for action in results:
        readback = action.get("artifacts", {}).get("readback")
        if isinstance(readback, dict):
            artifacts.append(
                {
                    "action_index": action.get("index"),
                    "path": readback.get("path"),
                }
            )
    return artifacts


def _rollback_summary(results: list[dict[str, Any]], *, failed_index: int | None) -> dict[str, Any]:
    if failed_index is None:
        return {"required": False, "artifacts": [], "compensation_plan": []}
    pre_write_artifacts = []
    for action in results:
        if not action.get("executed"):
            continue
        artifact = action.get("artifacts", {}).get("pre_write")
        if isinstance(artifact, dict):
            pre_write_artifacts.append(
                {
                    "action_index": action.get("index"),
                    "object_id": action.get("object_id"),
                    "path": artifact.get("path"),
                    "serialized_chars": artifact.get("serialized_chars"),
                    "serialized_bytes": artifact.get("serialized_bytes"),
                    "sha256": artifact.get("sha256"),
                }
            )
    compensation_plan = [
        {
            "action_index": item["action_index"],
            "object_id": item["object_id"],
            "source_artifact": item["path"],
            "mode": "manual_restore_required",
            "reason": "remote writes are not transactional; restore from pre_write artifact if rollback is required",
        }
        for item in pre_write_artifacts
    ]
    return {
        "required": bool(pre_write_artifacts),
        "available": False,
        "reason": "manual rollback is required from pre_write artifacts",
        "artifacts": pre_write_artifacts,
        "compensation_plan": compensation_plan,
    }


def _retry_resume_summary(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    failed_index: int | None,
) -> dict[str, Any]:
    actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    completed = [int(item["index"]) for item in results if item.get("executed")]
    if failed_index is None:
        # Completion already exposes the completed indices at the top level.
        # Keep the no-op retry contract explicit without repeating them for
        # every successful multi-action execution.
        return {"available": False}
    failed_result = next((item for item in results if item.get("index") == failed_index), {})
    error = failed_result.get("error") if isinstance(failed_result.get("error"), dict) else {}
    write_outcome = str(error.get("write_outcome") or "").strip().lower()
    if not write_outcome:
        write_outcome = "unknown" if failed_result.get("write_attempted") else "no_write"
    failed_safe_to_retry = bool(write_outcome == "no_write" and error.get("retry_safe", True))
    reconciliation_required = bool(error.get("reconciliation_required"))
    if failed_safe_to_retry:
        unfinished = [index for index in range(failed_index, len(actions)) if index not in completed]
    else:
        unfinished = []
    return {
        "available": bool(unfinished),
        "completed_action_indices": completed,
        "failed_action_index": failed_index,
        "failed_action_write_attempted": bool(failed_result.get("write_attempted")),
        "failed_action_write_outcome": write_outcome,
        "safe_unfinished_action_indices": unfinished,
        "requires_fresh_preflight": True,
        "requires_partial_create_reconciliation": bool(
            reconciliation_required
            or _requires_partial_create_reconciliation(actions, completed, unfinished)
        ),
        "resume_policy": (
            "rerun_fresh_read_then_retry_same_action"
            if failed_safe_to_retry
            else "write_outcome_unknown_blocks_automatic_resume"
            if write_outcome == "unknown"
            else "reconcile_remote_state_before_new_plan"
            if reconciliation_required
            else "automatic_resume_not_safe"
        ),
    }


def _transaction_group_issues(actions: list[Any]) -> list[str]:
    issues: list[str] = []
    groups: dict[str, list[tuple[int, str]]] = {}
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        group = str(action.get("transaction_group_id") or "").strip()
        if not group:
            issues.append(f"action {index} requires a non-empty transaction_group_id")
            continue
        payload = _payload_for_action(action)
        mode = str(payload.get("mode") or action.get("mode") or "save").strip().lower()
        groups.setdefault(group, []).append((index, mode))
    for group, members in groups.items():
        publish_indices = [index for index, mode in members if mode == "publish"]
        save_indices = [index for index, mode in members if mode == "save"]
        if publish_indices and save_indices and max(save_indices) > min(publish_indices):
            issues.append(
                f"transaction_group_id {group!r} must place every save action before every publish action"
            )
        if publish_indices:
            for index in save_indices:
                action = actions[index]
                if not isinstance(action, dict) or not _is_chart_or_dashboard_action(action):
                    continue
                readback = action.get("readback_contract") if isinstance(action.get("readback_contract"), dict) else {}
                if readback.get("required") is not True or str(readback.get("branch") or "") != "saved":
                    issues.append(
                        f"transaction_group_id {group!r} action {index} requires saved readback before publish"
                    )
    return issues


def _publish_transaction_group_error(
    *,
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    action_index: int,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    mode = str(payload.get("mode") or action.get("mode") or "save").strip().lower()
    if mode != "publish":
        return None
    group = str(action.get("transaction_group_id") or "delivery").strip()
    result_by_index = {int(item.get("index") or 0): item for item in results if isinstance(item, dict)}
    required_save_indices = [
        index
        for index, candidate in enumerate(plan.get("actions") or [])
        if index < action_index
        and isinstance(candidate, dict)
        and str(candidate.get("transaction_group_id") or "delivery").strip() == group
        and str((_payload_for_action(candidate).get("mode") or candidate.get("mode") or "save")).strip().lower()
        == "save"
        and _is_chart_or_dashboard_action(candidate)
    ]
    missing = [
        index
        for index in required_save_indices
        if not _completed_saved_readback(
            action=(plan.get("actions") or [])[index],
            result=result_by_index.get(index, {}),
        )
    ]
    if not missing:
        return None
    return {
        "category": "transaction_group_incomplete",
        "message": (
            f"publish blocked because transaction_group_id {group!r} lacks completed save+saved-readback "
            f"for actions: {missing}"
        ),
        "write_outcome": "no_write",
        "retry_safe": False,
        "reconciliation_required": True,
    }


def _transaction_group_summary(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    result_by_index = {
        int(item.get("index") or 0): item for item in results if isinstance(item, dict)
    }
    groups: dict[str, list[int]] = {}
    for index, action in enumerate(actions):
        if isinstance(action, dict):
            groups.setdefault(str(action.get("transaction_group_id") or "delivery"), []).append(index)
    summaries: list[dict[str, Any]] = []
    for group, indices in groups.items():
        modes = [
            str((_payload_for_action(actions[index]).get("mode") or actions[index].get("mode") or "save")).strip().lower()
            for index in indices
        ]
        completed = [index for index in indices if result_by_index.get(index, {}).get("executed")]
        failed = [index for index in indices if result_by_index.get(index, {}).get("status") == "failed"]
        unknown_outcome = any(
            str((result_by_index.get(index, {}).get("error") or {}).get("write_outcome") or "").lower()
            == "unknown"
            for index in indices
        )
        if len(completed) == len(indices):
            status = "completed"
        elif completed:
            status = "partial"
        elif failed:
            status = "failed"
        else:
            status = "not_run"
        required_save_indices = [
            index
            for index, mode in zip(indices, modes)
            if mode == "save" and _is_chart_or_dashboard_action(actions[index])
        ]
        saved_readback_complete = all(
            _completed_saved_readback(
                action=actions[index],
                result=result_by_index.get(index, {}),
            )
            for index in required_save_indices
        )
        publish_allowed = bool(
            not failed
            and not unknown_outcome
            and saved_readback_complete
        )
        summaries.append(
            {
                "transaction_group_id": group,
                "action_indices": indices,
                "completed_action_indices": completed,
                "failed_action_indices": failed,
                "status": status,
                "publish_allowed": publish_allowed,
                "no_partial_publish": True,
            }
        )
    return summaries


def _completed_saved_readback(*, action: dict[str, Any], result: dict[str, Any]) -> bool:
    return bool(
        result.get("executed")
        and (result.get("artifacts") or {}).get("readback")
        and (result.get("readback_verification") or {}).get("verified")
        and str((action.get("readback_contract") or {}).get("branch") or "").strip().lower() == "saved"
    )


def _is_chart_or_dashboard_action(action: dict[str, Any]) -> bool:
    method = str(action.get("method") or "").strip().lower()
    return "chart" in method or "dashboard" in method


def _action_owner(action: dict[str, Any]) -> dict[str, str]:
    return {
        "generator": str(action.get("generator") or action.get("generator_owner") or "unknown"),
        "source_path": str(
            action.get("generator_source")
            or action.get("source_path")
            or action.get("payload_source")
            or action.get("payload_path")
            or ""
        ),
    }


def _source_owner_contract(action: dict[str, Any]) -> dict[str, str]:
    owner = action.get("source_owner") if isinstance(action.get("source_owner"), dict) else {}
    generator = str(owner.get("generator") or action.get("generator") or action.get("generator_owner") or "").strip()
    source_path = str(
        owner.get("source_path")
        or action.get("generator_source")
        or action.get("source_path")
        or action.get("payload_source")
        or action.get("payload_path")
        or ""
    ).strip()
    return {
        "generator": generator or "datalens_dev_mcp.safe_apply",
        "source_path": source_path,
    }


def _payload_contract(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    existing = action.get("payload_contract") if isinstance(action.get("payload_contract"), dict) else {}
    metadata = serialized_metadata(payload)
    path = str(existing.get("path") or action.get("payload_path") or "").strip()
    source = str(existing.get("source") or ("artifact" if path else "inline"))
    contract: dict[str, Any] = {
        "source": source,
        "content_kind": str(existing.get("content_kind") or "datalens_api_request"),
        "hash_algorithm": "sha256",
        "sha256": str(existing.get("sha256") or action.get("payload_sha256") or metadata["sha256"]),
    }
    if path:
        contract["path"] = path
    else:
        contract["inline"] = True
    return contract


def _fresh_read_contract(action: dict[str, Any]) -> dict[str, Any]:
    existing = action.get("fresh_read_contract") if isinstance(action.get("fresh_read_contract"), dict) else {}
    payload = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    branch = str(existing.get("branch") or payload.get("branch") or "saved").strip().lower()
    return {
        "required": bool(existing.get("required", action.get("requires_fresh_read", True))),
        "method": str(existing.get("method") or action.get("fresh_read_method") or action.get("read_method") or ""),
        "payload": existing.get("payload") if isinstance(existing.get("payload"), dict) else payload,
        "branch": branch,
        "purpose": str(existing.get("purpose") or "preflight_fresh_read"),
    }


def _readback_contract(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    existing = action.get("readback_contract") if isinstance(action.get("readback_contract"), dict) else {}
    readback_payload = action.get("readback_payload") if isinstance(action.get("readback_payload"), dict) else {}
    payload_mode = str(payload.get("mode") or action.get("mode") or "save").strip().lower()
    default_branch = "published" if payload_mode == "publish" else "saved"
    branch = str(existing.get("branch") or readback_payload.get("branch") or default_branch).strip().lower()
    return {
        "required": bool(existing.get("required", action.get("readback_required", True))),
        "method": str(
            existing.get("method")
            or action.get("readback_method")
            or action.get("fresh_read_method")
            or action.get("read_method")
            or ""
        ),
        "payload": existing.get("payload") if isinstance(existing.get("payload"), dict) else readback_payload,
        "branch": branch,
        "mode": normalize_readback_mode(str(existing.get("mode") or action.get("readback_mode") or "minimal")),
        "proof_level": proof_level_for_readback_branch(branch),
    }


def _revision_guard(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    existing = action.get("revision_guard") if isinstance(action.get("revision_guard"), dict) else {}
    action_type = str(action.get("action_type") or _action_type(action, payload))
    expected_revision = str(existing.get("expected_revision") or _expected_revision(action, payload) or "").strip()
    guard: dict[str, Any] = {
        "expected_revision": expected_revision,
        "stale_revision_blocks_write": bool(existing.get("stale_revision_blocks_write", True)),
        "unknown_fields_preserved": bool(existing.get("unknown_fields_preserved", action.get("preserve_unknown_fields", True))),
    }
    if action_type == "create" and not expected_revision:
        guard["create_exception"] = True
        guard["exception_reason"] = "new object has no remote revision before create; fresh read must prove creation context"
    if action_type == "publish":
        guard["expected_saved_rev_id"] = str(action.get("expected_saved_rev_id") or "").strip()
        guard["expected_saved_id"] = str(action.get("expected_saved_id") or "").strip()
    return guard


def _stale_revision_retry_policy(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    existing = action.get("stale_revision_retry_policy")
    policy = dict(existing) if isinstance(existing, dict) else {}
    action_type = str(action.get("action_type") or _action_type(action, payload))
    is_update = action_type == "update"
    policy.setdefault("enabled", is_update)
    policy.setdefault("max_retry_count", 1 if is_update else 0)
    policy.setdefault("fresh_read_before_retry", is_update)
    policy.setdefault("create_new_on_revision_mismatch", False)
    policy.setdefault("unresolved_status", "revision_conflict_unresolved")
    policy.setdefault(
        "reason",
        "stale revision must retry the existing object once before blocking; create fallback is not allowed",
    )
    return policy


def _branch_semantics(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    fresh_payload = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    readback_payload = action.get("readback_payload") if isinstance(action.get("readback_payload"), dict) else {}
    payload_mode = str(payload.get("mode") or action.get("mode") or "save").strip().lower()
    return {
        "write_mode": payload_mode or "save",
        "source_branch": str(action.get("source_branch") or fresh_payload.get("branch") or "saved").strip().lower(),
        "fresh_read_branch": str(fresh_payload.get("branch") or "saved").strip().lower(),
        "readback_branch": str(readback_payload.get("branch") or ("published" if payload_mode == "publish" else "saved")).strip().lower(),
    }


def _approval_provenance(
    *,
    approved: bool,
    approval_note: str,
    approved_at: str,
    approval_source: str = "",
    request_digest: str = "",
) -> dict[str, Any]:
    return {
        "approved": bool(approved),
        "approval_source": approval_source or ("legacy_approved_plan" if approved else "not_authorized"),
        "approval_note": str(approval_note or ""),
        "approved_at": approved_at if approved else "",
        "request_digest": request_digest,
    }


def _request_intent_binding(user_request_text: str, *, approved: bool) -> dict[str, Any]:
    raw_text = str(user_request_text or "")
    normalized = normalize_user_request(raw_text or "implement")
    return {
        "normalized_intent": normalized.task_intent,
        "publish_override": normalized.publish_override,
        "request_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "request_text_present": bool(raw_text),
        "authorization_source": "current_user_request" if raw_text else "tool_call_intent",
        "authorizes_standard_mutation": bool(approved),
    }


def _runtime_write_gate_issues(config: DataLensConfig, payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not config.write_enabled:
        issues.append("write mode is disabled; set DATALENS_MCP_ENABLE_WRITES=1")
    if not config.save_enabled:
        issues.append("save execution is disabled; set DATALENS_MCP_LIVE_ALLOW_SAVE=1")
    mode = str(payload.get("mode") or "save").strip().lower()
    if mode == "publish":
        if not config.publish_enabled:
            issues.append("publish execution is disabled; set DATALENS_MCP_LIVE_ALLOW_PUBLISH=1")
    return issues


def _action_type(action: dict[str, Any], payload: dict[str, Any]) -> str:
    explicit = str(action.get("action_type") or "").strip().lower()
    if explicit in {"create", "update", "publish"}:
        return explicit
    payload_mode = str(payload.get("mode") or "").strip().lower()
    if payload_mode == "publish" or action.get("publish"):
        return "publish"
    method = str(action.get("method") or "").strip()
    if method.startswith("create"):
        return "create"
    return "update"


def _contract_issues(*, action: dict[str, Any], payload: dict[str, Any], index: int) -> list[str]:
    issues: list[str] = []
    source_owner = action.get("source_owner")
    if not isinstance(source_owner, dict) or not str(source_owner.get("generator") or "").strip():
        issues.append(f"action {index} source_owner.generator is required")
    payload_contract = action.get("payload_contract")
    if not isinstance(payload_contract, dict):
        issues.append(f"action {index} payload_contract is required")
    else:
        expected_sha = serialized_metadata(payload)["sha256"]
        actual_sha = str(payload_contract.get("sha256") or "").strip()
        if not actual_sha:
            issues.append(f"action {index} payload_contract.sha256 is required")
        elif actual_sha != expected_sha:
            issues.append(f"action {index} payload_contract.sha256 does not match payload")
        if payload_contract.get("source") == "artifact" and not str(payload_contract.get("path") or "").strip():
            issues.append(f"action {index} payload_contract.path is required for artifact payloads")
    fresh_contract = action.get("fresh_read_contract")
    if not isinstance(fresh_contract, dict) or not str(fresh_contract.get("method") or "").strip():
        issues.append(f"action {index} fresh_read_contract.method is required")
    readback_contract = action.get("readback_contract")
    try:
        normalized_readback_mode = normalize_readback_mode(action.get("readback_mode"))
    except ValueError:
        normalized_readback_mode = "minimal"
    if normalized_readback_mode != "none":
        if not isinstance(readback_contract, dict) or not str(readback_contract.get("method") or "").strip():
            issues.append(f"action {index} readback_contract.method is required")
    revision_guard = action.get("revision_guard")
    action_type = _action_type(action, payload)
    if not isinstance(revision_guard, dict):
        issues.append(f"action {index} revision_guard is required")
        revision_guard_for_create = {}
    else:
        revision_guard_for_create = revision_guard
        if not revision_guard.get("stale_revision_blocks_write", False):
            issues.append(f"action {index} revision_guard.stale_revision_blocks_write must be true")
        if action_type == "update" and not str(revision_guard.get("expected_revision") or "").strip():
            issues.append(f"action {index} revision_guard.expected_revision is required for update actions")
        if action_type == "publish":
            if not str(revision_guard.get("expected_saved_rev_id") or action.get("expected_saved_rev_id") or "").strip():
                issues.append(f"action {index} revision_guard.expected_saved_rev_id is required for publish actions")
            if not str(revision_guard.get("expected_saved_id") or action.get("expected_saved_id") or "").strip():
                issues.append(f"action {index} revision_guard.expected_saved_id is required for publish actions")
    if action_type == "create" and not (
        str(revision_guard_for_create.get("expected_revision") or "").strip()
        or revision_guard_for_create.get("create_exception")
    ):
        issues.append(f"action {index} revision_guard.create_exception is required when create has no revision")
    if action_type == "create":
        creation_proof = action.get("creation_necessity_proof")
        if not isinstance(creation_proof, dict) or not str(creation_proof.get("update_insufficient_reason") or "").strip():
            issues.append(f"action {index} creation_necessity_proof.update_insufficient_reason is required for create actions")
        elif not bool(creation_proof.get("existing_readback_checked") or creation_proof.get("object_reuse_checked")):
            issues.append(f"action {index} create actions require object reuse/readback evidence before live execution")
        reuse_decision = action.get("object_reuse_decision")
        if not isinstance(reuse_decision, dict):
            issues.append(f"action {index} object_reuse_decision is required for create actions")
        else:
            decision = str(reuse_decision.get("decision") or "").strip().lower()
            if reuse_decision.get("create_allowed") is False:
                issues.append(f"action {index} object_reuse_decision.create_allowed must be true for create actions")
            if decision == "block":
                issues.append(f"action {index} object_reuse_decision blocks create action")
            if decision == "create" and not str(reuse_decision.get("baseline_proof_artifact") or "").strip():
                issues.append(f"action {index} object_reuse_decision.baseline_proof_artifact is required for create actions")
        reuse_contract = reuse_decision if isinstance(reuse_decision, dict) else {}
        if _temporary_object_name(payload, action) and not _has_cleanup_lifecycle(action, reuse_contract):
            issues.append(f"action {index} temporary/runtime-fix object names require an explicit cleanup lifecycle")
    if not str(action.get("target_lock_hash") or "").strip():
        issues.append(f"action {index} target_lock_hash is required")
    return issues


def _delta_v7_evidence_issues(*, action: dict[str, Any], index: int) -> list[str]:
    issues: list[str] = []
    source_matrix = action.get("source_availability_matrix")
    if isinstance(source_matrix, dict):
        from datalens_dev_mcp.pipeline.source_availability import validate_source_availability_consumers

        validation = validate_source_availability_consumers(source_matrix, strict_publish_gate=True)
        for reason in validation.get("blocked_reasons") or []:
            issues.append(f"action {index} source availability {reason}")
    source_budget = action.get("editor_source_budget_evidence") or action.get("source_budget_evidence")
    if source_budget:
        from datalens_dev_mcp.pipeline.performance_budget import normalize_editor_source_budget_evidence_v7

        rows = normalize_editor_source_budget_evidence_v7(source_budget)
        for row in rows:
            if row.get("decision") in {"block", "insufficient_evidence"}:
                issues.append(
                    f"action {index} source budget {row.get('entry_id') or '<unknown>'}:"
                    f"{row.get('source_key') or '<unknown>'}:{row.get('decision')}"
                )
    baseline_diff = action.get("baseline_diff_contract")
    if isinstance(baseline_diff, dict):
        for reason in baseline_diff.get("blocked_reasons") or []:
            issues.append(f"action {index} baseline preservation {reason}")
    cleanup_report = action.get("object_cleanup_report")
    if isinstance(cleanup_report, dict):
        for row in cleanup_report.get("objects") or cleanup_report.get("created_objects") or []:
            if isinstance(row, dict) and row.get("active_in_saved_or_published_graph") and row.get("cleanup_requested"):
                issues.append(f"action {index} cleanup refuses active saved/published graph object")
    return issues


def _dashboard_baseline_contract_issues(
    *,
    action: dict[str, Any],
    payload: dict[str, Any],
    current_dashboard: Any,
    index: int,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(current_dashboard, dict) or not current_dashboard:
        issues.append(f"action {index} dashboard update requires a non-empty current_dashboard baseline")
    contract = action.get("baseline_diff_contract")
    if not isinstance(contract, dict) or not contract:
        issues.append(f"action {index} dashboard update requires baseline_diff_contract")
        return issues
    if contract.get("schema_version") != "datalens.baseline-diff-contract.delta-v6":
        issues.append(f"action {index} dashboard baseline_diff_contract has unsupported schema_version")
    expected_object_id = _action_object_id(action, payload)
    if expected_object_id and str(contract.get("dashboard_id") or "") != expected_object_id:
        issues.append(f"action {index} dashboard baseline_diff_contract.dashboard_id does not match action object_id")
    if not isinstance(contract.get("baseline_source"), dict):
        issues.append(f"action {index} dashboard baseline_diff_contract.baseline_source is required")
    if not isinstance(contract.get("tabs"), list) or not isinstance(contract.get("changed_objects"), list):
        issues.append(f"action {index} dashboard baseline_diff_contract must include tabs and changed_objects")
    if isinstance(current_dashboard, dict) and current_dashboard and expected_object_id:
        recomputed = build_baseline_diff_contract(
            dashboard_id=expected_object_id,
            workbook_id=str(contract.get("workbook_id") or ""),
            baseline_source=(
                contract.get("baseline_source")
                if isinstance(contract.get("baseline_source"), dict)
                else {}
            ),
            baseline_dashboard=current_dashboard,
            proposed_dashboard=payload,
            changed_objects=[],
        )
        for key in ("tabs", "unexpected_layout_diff", "blocked_reasons"):
            if contract.get(key) != recomputed.get(key):
                issues.append(f"action {index} dashboard baseline_diff_contract.{key} is stale or unbound")
        for reason in recomputed.get("blocked_reasons") or []:
            issues.append(f"action {index} dashboard recomputed baseline preservation {reason}")
    for reason in contract.get("blocked_reasons") or []:
        issues.append(f"action {index} dashboard baseline preservation {reason}")
    return issues


def _temporary_object_name(payload: dict[str, Any], action: dict[str, Any]) -> bool:
    text = " ".join(
        str(item)
        for item in (
            action.get("action"),
            action.get("object_id"),
            payload.get("name"),
            payload.get("title"),
            (payload.get("entry") or {}).get("name") if isinstance(payload.get("entry"), dict) else "",
            (payload.get("entry") or {}).get("title") if isinstance(payload.get("entry"), dict) else "",
            (payload.get("entry") or {}).get("data", {}).get("title")
            if isinstance(payload.get("entry"), dict) and isinstance(payload.get("entry", {}).get("data"), dict)
            else "",
        )
    ).lower()
    return any(
        token in text
        for token in (
            "runtime fix",
            "runtime_fix",
            " v13",
            "v13 ",
            "temp",
            "temporary",
            "repair",
            "generated",
        )
    )


def _has_cleanup_lifecycle(action: dict[str, Any], reuse_decision: dict[str, Any]) -> bool:
    cleanup = action.get("cleanup_lifecycle") or reuse_decision.get("cleanup_lifecycle")
    return isinstance(cleanup, dict) and bool(cleanup.get("mode") or cleanup.get("required") or cleanup.get("plan_path"))


def _requires_partial_create_reconciliation(
    actions: list[dict[str, Any]],
    completed: list[int],
    unfinished: list[int],
) -> bool:
    relevant_indices = set(completed) | set(unfinished)
    for index in relevant_indices:
        if 0 <= index < len(actions):
            method = str(actions[index].get("method") or "").lower()
            action = str(actions[index].get("action") or "").lower()
            if method.startswith("create") or action.startswith("create"):
                return True
    return False


def _shape_counts(value: Any) -> dict[str, int]:
    counts = {"top_level_keys": 0, "entries": 0, "charts": 0, "tabs": 0, "items": 0}
    if isinstance(value, dict):
        counts["top_level_keys"] = len(value)
        if isinstance(value.get("entries"), list):
            counts["entries"] = len(value["entries"])
        if isinstance(value.get("charts"), list):
            counts["charts"] = len(value["charts"])
        data = _nested_data(value)
        if isinstance(data.get("tabs"), list):
            counts["tabs"] = len(data["tabs"])
        if isinstance(data.get("items"), list):
            counts["items"] = len(data["items"])
    return counts


def _nested_data(value: dict[str, Any]) -> dict[str, Any]:
    entry = value.get("entry")
    if isinstance(entry, dict) and isinstance(entry.get("data"), dict):
        return entry["data"]
    for key in ("dashboard", "chart", "object"):
        nested = value.get(key)
        if isinstance(nested, dict):
            nested_entry = nested.get("entry")
            if isinstance(nested_entry, dict) and isinstance(nested_entry.get("data"), dict):
                return nested_entry["data"]
            if isinstance(nested.get("data"), dict):
                return nested["data"]
    return value.get("data") if isinstance(value.get("data"), dict) else {}


def _object_identity(value: dict[str, Any]) -> dict[str, str]:
    candidate = _first_identity_candidate(value)
    return {
        "object_id": _candidate_object_id(candidate),
        "name": str(candidate.get("name") or candidate.get("displayKey") or ""),
    }


def _find_readback_object_by_identity(
    value: Any,
    *,
    object_id: str,
    identity_key: str | None = None,
) -> dict[str, Any] | None:
    if not object_id:
        return None
    if isinstance(value, dict):
        current = value
        while isinstance(current.get("result"), dict):
            current = current["result"]
        identity_keys = ["entryId", "entry_id", "id"]
        if identity_key:
            identity_keys.extend(
                [identity_key, re.sub(r"(?<!^)(?=[A-Z])", "_", identity_key).lower()]
            )
        if any(
            str(current.get(key) or "").strip() == object_id
            for key in identity_keys
        ):
            return current
        ordered_keys = (
            "entry",
            "dashboard",
            "chart",
            "dataset",
            "connection",
            "report",
            "object",
            "entries",
            "charts",
            "dashboards",
            "datasets",
            "connections",
            "reports",
        )
        for key in ordered_keys:
            if key not in current:
                continue
            found = _find_readback_object_by_identity(
                current[key],
                object_id=object_id,
                identity_key=identity_key,
            )
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = _find_readback_object_by_identity(
                item,
                object_id=object_id,
                identity_key=identity_key,
            )
            if found is not None:
                return found
    return None


def _revision_id(value: dict[str, Any]) -> str:
    candidate = _first_identity_candidate(value)
    return str(candidate.get("revId") or candidate.get("rev_id") or candidate.get("revisionId") or candidate.get("revision_id") or "")


def _saved_id(value: dict[str, Any]) -> str:
    return str(_first_identity_candidate(value).get("savedId") or _first_identity_candidate(value).get("saved_id") or "")


def _saved_published_identity_diverges(action: dict[str, Any], payload: dict[str, Any]) -> bool:
    saved_ids: list[str] = []
    published_ids: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).replace("_", "").lower()
                if lowered == "savedid" and str(item).strip():
                    saved_ids.append(str(item).strip())
                elif lowered == "publishedid" and str(item).strip():
                    published_ids.append(str(item).strip())
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(action)
    walk(payload)
    return bool(saved_ids and published_ids and saved_ids[0] != published_ids[0])


def _status_value(value: dict[str, Any]) -> str:
    return str(value.get("status") or value.get("state") or ("ok" if value else "empty"))


def _first_identity_candidate(value: dict[str, Any]) -> dict[str, Any]:
    while isinstance(value.get("result"), dict):
        value = value["result"]
    for key in ("entry", "dashboard", "chart", "dataset", "connection", "connector", "report", "object"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            nested = candidate.get("entry")
            if isinstance(nested, dict):
                return nested
            return candidate
    return value


def _candidate_object_id(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("entryId")
        or candidate.get("entry_id")
        or candidate.get("id")
        or candidate.get("dashboardId")
        or candidate.get("chartId")
        or candidate.get("datasetId")
        or candidate.get("connectionId")
        or candidate.get("reportId")
        or ""
    ).strip()


def _action_object_id(action: dict[str, Any], payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    fresh_payload = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    readback_payload = action.get("readback_payload") if isinstance(action.get("readback_payload"), dict) else {}
    return str(
        action.get("object_id")
        or entry.get("entryId")
        or entry.get("id")
        or payload.get("dashboardId")
        or payload.get("chartId")
        or payload.get("datasetId")
        or payload.get("connectionId")
        or fresh_payload.get("dashboardId")
        or fresh_payload.get("chartId")
        or fresh_payload.get("datasetId")
        or fresh_payload.get("connectionId")
        or readback_payload.get("dashboardId")
        or readback_payload.get("chartId")
        or readback_payload.get("datasetId")
        or readback_payload.get("connectionId")
        or ""
    ).strip()


def _classify_safe_apply_error(exc: Exception, *, write_attempted: bool) -> dict[str, Any]:
    message = redact_text(str(exc))[:500] or exc.__class__.__name__
    upper = message.upper()
    base: dict[str, Any] = {
        "message": message,
        "exception_type": exc.__class__.__name__,
    }
    if "ENTRY_IS_LOCKED" in upper:
        return {
            **base,
            "category": "conflict_no_write",
            "remote_code": "ENTRY_IS_LOCKED",
            "write_outcome": "no_write",
            "retry_safe": True,
            "reconciliation_required": False,
            "resume_after": ["fresh_read", "revision_recheck"],
            **_conflict_timing(message),
        }
    if "UNIQUE_VIOLATION" in upper:
        return {
            **base,
            "category": "conflict_no_write",
            "remote_code": "UNIQUE_VIOLATION",
            "write_outcome": "no_write",
            "retry_safe": False,
            "reconciliation_required": True,
            "resume_after": ["entries_reconciliation", "fresh_read", "new_safe_apply_plan"],
        }
    if write_attempted:
        return {
            **base,
            "category": "write_outcome_unknown",
            "write_outcome": "unknown",
            "retry_safe": False,
            "reconciliation_required": True,
            "resume_after": ["live_readback", "entries_reconciliation", "new_safe_apply_plan"],
        }
    return {
        **base,
        "category": "pre_write_failed",
        "write_outcome": "no_write",
        "retry_safe": True,
        "reconciliation_required": False,
        "resume_after": ["fresh_read", "new_safe_apply_plan"],
    }


def _concise_error(exc: Exception) -> dict[str, Any]:
    """Backward-compatible pre-write classifier for callers that only need redaction."""

    return _classify_safe_apply_error(exc, write_attempted=False)


def _conflict_timing(message: str) -> dict[str, Any]:
    timing: dict[str, Any] = {}
    retry_match = re.search(
        r"(?:retry[_-]?after|retryAfter)\s*[\"']?\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)",
        message,
        flags=re.IGNORECASE,
    )
    if retry_match:
        value = float(retry_match.group(1))
        timing["retry_after"] = int(value) if value.is_integer() else value
    lock_match = re.search(
        r"(?:lock[_-]?until|lockUntil)\s*[\"']?\s*[:=]\s*[\"']?([^\s,}\"']+)",
        message,
        flags=re.IGNORECASE,
    )
    if lock_match:
        timing["lock_until"] = lock_match.group(1)
    return timing


def _payload_for_action(action: dict[str, Any]) -> dict[str, Any]:
    payload = action.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    payload_path = str(action.get("payload_path") or "").strip()
    if not payload_path:
        return {}
    path = Path(payload_path)
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return dict(loaded) if isinstance(loaded, dict) else {}


def _is_dashboard_action(action: dict[str, Any]) -> bool:
    method = str(action.get("method") or "").lower()
    if "dashboard" in method:
        return True
    payload = action.get("payload")
    if isinstance(payload, dict):
        keys = {str(key) for key in payload}
        return bool(keys & {"dashboardId", "dashboard_id", "blocks", "items", "widgets", "selector_rows"})
    payload_path = str(action.get("payload_path") or "").lower()
    return "dashboard" in payload_path


def _is_editor_chart_action(action: dict[str, Any], payload: dict[str, Any]) -> bool:
    method = str(action.get("method") or "").lower()
    if "editorchart" in method:
        return True
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    scope = str(entry.get("scope") or entry.get("type") or payload.get("scope") or "").lower()
    if "editor" in scope:
        return True
    return any(key in payload for key in ("javascript", "html", "css", "sources", "prepare"))


def _is_wizard_chart_action(action: dict[str, Any], payload: dict[str, Any]) -> bool:
    method = str(action.get("method") or "").lower()
    if "wizardchart" in method:
        return True
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    scope = str(entry.get("scope") or entry.get("type") or payload.get("scope") or payload.get("route") or "").lower()
    return "wizard" in scope or "datasetsPartialFields" in stable_json_text(payload)


def _is_table_chart_action(action: dict[str, Any], payload: dict[str, Any]) -> bool:
    method = str(action.get("method") or "").lower()
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    entry_type = str(entry.get("type") or payload.get("entry_type") or "").lower()
    if entry_type == "table_node":
        return True
    if "editorchart" in method and "table" in str(action.get("action") or "").lower():
        return True
    return False


def _has_object_granularity_manifest(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("objects", "object_manifest", "expected_visual_count", "dashboard_like_advanced_editor"))


def _has_selector_contract(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("selectors", "selector_rows", "controls", "selectorRows"))


def _has_kpi_contract(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("kpis", "indicators", "expected_kpi_count"))


def _has_source_route_contract(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "source_mode",
            "selected_source_route",
            "dataset_id",
            "existing_dataset_id",
            "connection_id",
            "user_uploaded_file",
            "source_file_name",
            "explicit_static_embedded_approval",
        )
    )


def _iter_renderer_visual_specs(value: Any, path: str = "$"):
    if isinstance(value, dict):
        spec = value.get("renderer_visual_spec")
        if isinstance(spec, dict) and spec:
            yield f"{path}.renderer_visual_spec", spec
        elif _looks_like_renderer_visual_spec(value):
            yield path, value
        for key, item in value.items():
            if key == "renderer_visual_spec":
                continue
            yield from _iter_renderer_visual_specs(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_renderer_visual_specs(item, f"{path}[{index}]")


def _looks_like_renderer_visual_spec(value: dict[str, Any]) -> bool:
    return bool(
        (value.get("family") or value.get("selected_family"))
        and any(key in value for key in ("labels", "label_spec", "axes", "axis_spec", "encoding", "analytical_task"))
    )


def _native_table_payload_from_editor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    prepare = str(data.get("prepare") or data.get("prepare.js") or "")
    sources = str(data.get("sources") or data.get("sources.js") or "")
    columns = _columns_from_prepare(prepare)
    return {
        "route": "editor_table",
        "columns": columns,
        "source": {"query": sources or prepare, "row_count": payload.get("source_rows")},
        "empty_state_policy": {"message": "Нет данных по выбранным фильтрам"},
    }


def _columns_from_prepare(prepare: str) -> list[dict[str, Any]]:
    import ast
    import re

    match = re.search(r"const\s+columns\s*=\s*(\[[^\]]*\])", prepare, flags=re.S)
    names: list[str] = []
    if match:
        try:
            raw = ast.literal_eval(match.group(1))
            if isinstance(raw, list):
                names = [str(item) for item in raw if str(item)]
        except Exception:  # noqa: BLE001
            names = []
    if not names and "head =" in prepare:
        names = ["value"]
    columns = []
    for name in names:
        lower = name.lower()
        if lower in {"value", "amount", "count", "total"} and "type: 'bar'" in prepare:
            columns.append(
                {
                    "id": name,
                    "title": name,
                    "role": "measure",
                    "type": "bar",
                    "format": "number",
                    "min": 0,
                    "max": "computed_from_visible_rows",
                    "barColor": "#2f80ed",
                    "showLabel": True,
                    "label_position": "outside",
                }
            )
        else:
            columns.append({"id": name, "title": name, "role": "dimension", "type": "text", "format": "text"})
    return columns


def _normalize_readback_branch(branch: str) -> str:
    normalized = str(branch or "").strip().lower()
    if normalized not in READBACK_BRANCHES:
        raise ValueError(f"readback branch must be one of {sorted(READBACK_BRANCHES)}")
    return normalized


def normalize_publish_object_type(object_type: str) -> str:
    normalized = str(object_type or "").strip().lower().replace("-", "_")
    return "editor_chart" if normalized in EDITOR_PUBLISH_ALIASES else normalized


def _normalize_publish_object_type(object_type: str) -> str:
    return normalize_publish_object_type(object_type)


def _publish_plan_error(category: str, message: str) -> dict[str, Any]:
    return {"ok": False, "status": "publish_blocked", "error": {"category": category, "message": message}, "actions": []}


def _error(category: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"category": category, "message": message}}


def _publish_action_from_saved_readback(
    *,
    saved_readback: dict[str, Any],
    object_id: str,
    source_path: Path,
    method_spec: dict[str, str],
    readback_mode: str,
) -> dict[str, Any]:
    saved_identity = _saved_readback_identity(saved_readback, object_id=object_id)
    if saved_identity.get("duplicate"):
        return _error(
            "duplicate_saved_readback",
            f"saved readback contains duplicate entries for object_id {saved_identity.get('object_id') or object_id}",
        )
    if saved_identity.get("ambiguous"):
        return _error("ambiguous_saved_readback", "object_id is required when saved readback contains multiple objects")
    if not saved_identity["object_id"]:
        return _error("missing_object_id", "object_id or saved readback entry id is required")
    missing_identity = [key for key in ("saved_rev_id", "saved_id") if not saved_identity.get(key)]
    if missing_identity:
        return _error("missing_saved_revision", f"saved readback is missing {', '.join(missing_identity)}")
    saved_entry = _saved_readback_entry(saved_readback, object_id=saved_identity["object_id"])
    if not saved_entry:
        return _error("missing_saved_entry", "saved readback is missing the complete object entry")
    completeness_issues = _saved_entry_completeness_issues(saved_entry, method=method_spec["write"])
    if completeness_issues:
        return _error("incomplete_saved_entry", "; ".join(completeness_issues))
    publish_entry = dict(saved_entry)
    publish_entry["entryId"] = saved_identity["object_id"]
    publish_entry["revId"] = saved_identity["saved_rev_id"]
    publish_entry.pop("savedId", None)
    publish_entry.pop("saved_id", None)
    action = {
        "action": "publish_object",
        "method": method_spec["write"],
        "mode": "save",
        "publish": True,
        "source_branch": "saved",
        "saved_readback_path": str(source_path),
        "expected_saved_rev_id": saved_identity["saved_rev_id"],
        "expected_saved_id": saved_identity["saved_id"],
        "requires_fresh_read": True,
        "fresh_read_method": method_spec["read"],
        "fresh_read_payload": {method_spec["id_key"]: saved_identity["object_id"], "branch": "saved"},
        "readback_method": method_spec["read"],
        "readback_payload": {method_spec["id_key"]: saved_identity["object_id"], "branch": "published"},
        "readback_mode": normalize_readback_mode(readback_mode),
        "readback_required": normalize_readback_mode(readback_mode) != "none",
        "payload": {
            "mode": "publish",
            "entry": publish_entry,
        },
    }
    if method_spec["write"] == "updateDashboard":
        action["current_dashboard"] = saved_readback
        action["baseline_dashboard"] = saved_readback
        action["baseline_diff_contract"] = build_baseline_diff_contract(
            dashboard_id=saved_identity["object_id"],
            baseline_source={"kind": "saved_readback", "path": str(source_path)},
            baseline_dashboard=saved_readback,
            proposed_dashboard=action["payload"],
            changed_objects=[],
        )
    return {
        "ok": True,
        "action": action,
        "publish_source": {
            "branch": "saved",
            "artifact_path": str(source_path),
            "object_id": saved_identity["object_id"],
            "expected_saved_rev_id": saved_identity["saved_rev_id"],
            "expected_saved_id": saved_identity["saved_id"],
        },
    }


def _publish_source_issues(*, root: Path, action: dict[str, Any], index: int) -> list[str]:
    issues: list[str] = []
    if not action.get("publish"):
        issues.append(f"action {index} payload mode publish requires publish=true")
    if str(action.get("source_branch") or "").strip().lower() != "saved":
        issues.append(f"action {index} publish source_branch must be saved")
    saved_readback_path = str(action.get("saved_readback_path") or "").strip()
    if not saved_readback_path:
        issues.append(f"action {index} publish requires saved_readback_path")
        return issues
    path = Path(saved_readback_path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        issues.append(f"action {index} saved_readback_path does not exist: {path}")
        return issues
    try:
        readback = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        issues.append(f"action {index} saved_readback_path is not valid JSON: {exc.__class__.__name__}")
        return issues
    branch = str(readback.get("branch") or "").strip().lower()
    if branch != "saved":
        issues.append(f"action {index} publish must be built from saved branch readback, got {branch or 'unknown'}")
    object_id = _action_object_id(action, _payload_for_action(action))
    identity = _saved_readback_identity(readback, object_id=object_id)
    if identity.get("duplicate"):
        issues.append(f"action {index} saved_readback_path has duplicate entries for object_id {object_id}")
        return issues
    if identity.get("ambiguous"):
        issues.append(f"action {index} saved_readback_path has ambiguous object matches; object_id is required")
        return issues
    if object_id and identity.get("object_id") and identity["object_id"] != object_id:
        issues.append(f"action {index} saved_readback_path object_id does not match action object_id")
        return issues
    if object_id and not (identity.get("saved_rev_id") or identity.get("saved_id")):
        issues.append(f"action {index} saved_readback_path has no saved readback for object_id {object_id}")
        return issues
    if object_id:
        saved_entry = _saved_readback_entry(readback, object_id=object_id)
        if not saved_entry:
            issues.append(f"action {index} saved_readback_path is missing full saved entry for object_id {object_id}")
        else:
            issues.extend(
                f"action {index} {issue}"
                for issue in _saved_entry_completeness_issues(saved_entry, method=str(action.get("method") or ""))
            )
    expected_rev = str(action.get("expected_saved_rev_id") or "").strip()
    expected_saved_id = str(action.get("expected_saved_id") or "").strip()
    if not expected_rev:
        issues.append(f"action {index} publish requires expected_saved_rev_id")
    elif identity.get("saved_rev_id") and identity["saved_rev_id"] != expected_rev:
        issues.append(f"action {index} expected_saved_rev_id does not match saved readback")
    if not expected_saved_id:
        issues.append(f"action {index} publish requires expected_saved_id")
    elif identity.get("saved_id") and identity["saved_id"] != expected_saved_id:
        issues.append(f"action {index} expected_saved_id does not match saved readback")
    fresh_branch = ""
    if isinstance(action.get("fresh_read_payload"), dict):
        fresh_branch = str(action["fresh_read_payload"].get("branch") or "").strip().lower()
    if fresh_branch and fresh_branch != "saved":
        issues.append(f"action {index} publish fresh_read_payload.branch must be saved")
    return issues


def _saved_readback_identity(readback: dict[str, Any], *, object_id: str = "") -> dict[str, str]:
    candidates = _saved_readback_candidates(readback)
    requested_id = str(object_id or "").strip()
    matched: list[tuple[dict[str, str], bool]] = []
    for candidate in candidates:
        candidate_object_id = str(
            candidate.get("entryId")
            or candidate.get("entry_id")
            or candidate.get("id")
            or candidate.get("dashboardId")
            or candidate.get("chartId")
            or ""
        ).strip()
        saved_rev_id = str(
            candidate.get("revId")
            or candidate.get("rev_id")
            or candidate.get("savedRevId")
            or candidate.get("saved_rev_id")
            or ""
        ).strip()
        saved_id = str(candidate.get("savedId") or candidate.get("saved_id") or "").strip()
        if requested_id and candidate_object_id and candidate_object_id != requested_id:
            continue
        if candidate_object_id or saved_rev_id or saved_id:
            matched.append(
                (
                    {
                        "object_id": candidate_object_id or requested_id,
                        "saved_rev_id": saved_rev_id,
                        "saved_id": saved_id,
                    },
                    isinstance(candidate.get("data"), dict),
                )
            )
    full_matches = [item for item, complete in matched if complete]
    identity_matches = full_matches or [item for item, _complete in matched]
    unique = {
        (item["object_id"], item["saved_rev_id"], item["saved_id"]): item
        for item in identity_matches
        if item["object_id"] or item["saved_rev_id"] or item["saved_id"]
    }
    if requested_id:
        requested_matches = [
            item
            for item in unique.values()
            if item["object_id"] == requested_id or (not item["object_id"] and requested_id)
        ]
        if len(requested_matches) > 1:
            return {
                "object_id": requested_id,
                "saved_rev_id": "",
                "saved_id": "",
                "duplicate": "true",
            }
        return next(iter(requested_matches), {"object_id": requested_id, "saved_rev_id": "", "saved_id": ""})
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        return {
            "object_id": "",
            "saved_rev_id": "",
            "saved_id": "",
            "ambiguous": "true",
        }
    return {"object_id": str(object_id or "").strip(), "saved_rev_id": "", "saved_id": ""}


def _saved_readback_entry(readback: dict[str, Any], *, object_id: str) -> dict[str, Any]:
    requested_id = str(object_id or "").strip()
    for candidate in _saved_readback_candidates(readback):
        candidate_object_id = str(
            candidate.get("entryId")
            or candidate.get("entry_id")
            or candidate.get("id")
            or candidate.get("dashboardId")
            or candidate.get("chartId")
            or ""
        ).strip()
        if requested_id and candidate_object_id != requested_id:
            continue
        if candidate_object_id:
            return candidate
    return {}


def _saved_entry_completeness_issues(saved_entry: dict[str, Any], *, method: str) -> list[str]:
    issues: list[str] = []
    if not isinstance(saved_entry.get("data"), dict):
        issues.append("publish requires full saved entry.data, not summary-only revision identity")
    if method == "updateDashboard" and not isinstance(saved_entry.get("meta"), dict):
        issues.append("dashboard publish requires full saved entry.meta")
    if method in {"updateEditorChart", "updateWizardChart", "updateDashboard"}:
        object_id = _candidate_object_id(saved_entry)
        if not object_id:
            issues.append("publish requires saved entry object id")
    return issues


def _saved_readback_candidates(readback: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def append_envelope(value: Any) -> None:
        if not isinstance(value, dict):
            return
        nested = value.get("entry")
        candidates.append(nested if isinstance(nested, dict) else value)

    for key in ("dashboard", "chart", "entry", "object"):
        append_envelope(readback.get(key))
    response = readback.get("response")
    if isinstance(response, dict):
        append_envelope(response)
        for key in ("dashboard", "chart", "entry", "object"):
            append_envelope(response.get(key))
    for key in ("charts", "objects", "entries"):
        values = readback.get(key)
        if isinstance(values, list):
            for value in values:
                append_envelope(value)
    object_ids = readback.get("object_ids")
    if isinstance(object_ids, list):
        for value in object_ids:
            if isinstance(value, dict):
                append_envelope(value)
            elif isinstance(value, str) and value.strip():
                candidates.append({"entryId": value.strip()})
    summary = readback.get("summary")
    if isinstance(summary, dict):
        identity = summary.get("identity")
        if isinstance(identity, dict):
            candidates.append(identity)
    candidates.append(readback)
    return candidates
