from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError, DataLensSafetyError
from datalens_dev_mcp.api.methods import get_method_schema
from datalens_dev_mcp.api.request_compiler import (
    compile_guarded_rpc_request,
    compile_method_request,
    validate_method_request,
)
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.knowledge.formulas import load_formula_registry, validate_formula_expression
from datalens_dev_mcp.mcp.object_registry import object_read_contract, object_type_registry
from datalens_dev_mcp.mcp.response_projection import (
    DEFAULT_INLINE_CHAR_BUDGET,
    project_response,
    sanitize_response,
    serialized_metadata,
    stable_sha256,
)
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan
from datalens_dev_mcp.pipeline.baseline_preservation import create_necessity_proof
from datalens_dev_mcp.pipeline.delivery_intent import resolve_delivery_intent_from_env
from datalens_dev_mcp.pipeline.user_request import normalize_user_request
from datalens_dev_mcp.pipeline.sql_performance import validate_payload_sql_performance
from datalens_dev_mcp.pipeline.sql_runtime_reality import build_sql_runtime_reality_check
from datalens_dev_mcp.pipeline.object_routing import validate_field_availability
from datalens_dev_mcp.pipeline.route_registry import (
    QL_EXPLICIT_ROUTE,
    WIZARD_MAP_ALIAS,
    WIZARD_NATIVE_ROUTE,
    is_supported_wizard_visualization,
    normalize_creation_route,
)


SENSITIVE_KEYWORDS = ("token", "authorization", "password", "secret", "iam", "subjecttoken")

OBJECT_METHODS: dict[str, dict[str, str | None]] = {
    "dashboard": {"read": "getDashboard", "create": "createDashboard", "update": "updateDashboard"},
    "chart": {"read": "getEditorChart", "create": "createEditorChart", "update": "updateEditorChart"},
    "editor_chart": {"read": "getEditorChart", "create": "createEditorChart", "update": "updateEditorChart"},
    "advanced_editor_chart": {"read": "getEditorChart", "create": "createEditorChart", "update": "updateEditorChart"},
    "table": {"read": "getEditorChart", "create": "createEditorChart", "update": "updateEditorChart"},
    "control": {"read": "getEditorChart", "create": "createEditorChart", "update": "updateEditorChart"},
    "markdown": {"read": "getEditorChart", "create": "createEditorChart", "update": "updateEditorChart"},
    "wizard_chart": {"read": "getWizardChart", "create": "createWizardChart", "update": "updateWizardChart"},
    "dataset": {"read": "getDataset", "create": "createDataset", "update": "updateDataset", "validate": "validateDataset"},
    "connector": {"read": "getConnection", "create": "createConnection", "update": "updateConnection"},
    "connection": {"read": "getConnection", "create": None, "update": None},
    "folder": {"read": None, "create": "createFolder", "update": None},
    "permission": {"read": "getPermissions", "create": None, "update": "modifyPermissions"},
    "workbook_permission": {"read": "listWorkbookAccessBindings", "create": None, "update": "updateWorkbookAccessBindings"},
    "workbook_entry": {"read": None, "create": None, "update": "renameEntry", "move": "moveFolderEntry"},
    "dataset_field": {"read": None, "create": None, "update": None},
    "calculated_field": {"read": None, "create": None, "update": None},
    "ql_chart": {"read": "getQLChart", "create": "createQLChart", "update": "updateQLChart"},
    "report": {"read": "getReport", "create": None, "update": None},
    "d3_node": {"read": "getEditorChart", "create": None, "update": None},
}

READ_ID_KEYS = {
    "dashboard": "dashboardId",
    "chart": "chartId",
    "editor_chart": "chartId",
    "advanced_editor_chart": "chartId",
    "table": "chartId",
    "control": "chartId",
    "markdown": "chartId",
    "wizard_chart": "chartId",
    "dataset": "datasetId",
    "connector": "connectionId",
    "connection": "connectionId",
    "permission": "entryId",
    "workbook_permission": "workbookId",
    "ql_chart": "chartId",
    "report": "entryId",
    "d3_node": "chartId",
}

SOURCE_ADAPTERS = {
    "canonical_object_payload",
    "canonical_request_payload",
    "rpc_readback_envelope",
    "saved_entry",
    "published_entry",
    "artifact_path",
    "project_manifest_reference",
}
PERMISSION_MUTATION_TYPES = {"permission", "workbook_permission"}
PLACEHOLDER_TARGETS = {
    "",
    "id",
    "target",
    "target_id",
    "workbook_id",
    "dashboard_id",
    "chart_id",
    "dataset_id",
    "connection_id",
    "<id>",
    "<target_id>",
    "<workbook_id>",
    "<dashboard_id>",
    "<chart_id>",
    "<dataset_id>",
    "<connection_id>",
}


def dl_probe_auth(client: Any | None = None) -> dict[str, Any]:
    """Run the minimal read-only auth probe."""
    try:
        active_client = client or DataLensApiClient(DataLensConfig.from_env())
        response = active_client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1})
        return {"ok": True, "status": "authenticated", "method": "getWorkbooksList", "response_keys": sorted(response)}
    except Exception as exc:  # noqa: BLE001
        return _error_result(exc, fallback_category="auth_failure")


def dl_read_object(
    object_type: str,
    object_id: str,
    branch: str = "saved",
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
    workbook_id: str = "",
    client: Any | None = None,
) -> dict[str, Any]:
    contract = object_read_contract(object_type)
    normalized = contract.object_type if contract else str(object_type or "").strip().lower()
    if not normalized:
        return _error("missing_input", "object_type is required")
    if not object_id:
        return _error("missing_input", "object_id is required")
    if not contract:
        return {
            **_error(
                "unsupported_type",
                f"Unsupported object_type `{object_type}`. Use one of {sorted(object_type_registry()['object_types'])}.",
            ),
            "object_type": normalized,
            "object_id": object_id,
            "attempted_method": "",
            "remediation": "Resolve the workbook entry type through getWorkbookEntries or add an evidence-backed registry contract.",
        }
    method = contract.read_method
    if not method:
        result = _unavailable(normalized, "read")
        result.update(
            {
                "object_id": object_id,
                "attempted_method": "",
                "contract": contract.to_dict(),
                "remediation": contract.unsupported_reason
                or "Use the supported parent object read contract or workbook inventory.",
            }
        )
        return result
    payload_key = contract.identity_field
    payload = {payload_key: object_id}
    if workbook_id and payload_key != "workbookId":
        payload["workbookId"] = workbook_id
    if contract.branch_semantics == "saved_or_published":
        payload["branch"] = branch
    try:
        active_client = client or DataLensApiClient(DataLensConfig.from_env())
        response = active_client.rpc(method, payload)
        projected = _project_read_response(
            response=response,
            object_type=normalized,
            object_id=object_id,
            branch=branch,
            method=method,
            contract=contract.to_dict(),
            response_mode=response_mode,
            inline_char_budget=inline_char_budget,
            project_root=project_root,
            run_id=run_id,
        )
        return projected
    except Exception as exc:  # noqa: BLE001
        result = _error_result(exc)
        result.update(
            {
                "object_type": normalized,
                "object_id": object_id,
                "attempted_method": method,
                "contract": contract.to_dict(),
                "remediation": _bounded_remediation(result["error"]["category"], method, normalized),
            }
        )
        return result


def dl_validate_object_payload(
    object_type: str,
    payload: dict[str, Any] | None = None,
    operation: str = "update",
    approval_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_object_type(object_type)
    if not normalized:
        return _error("missing_input", "object_type is required")
    policy_block = _policy_blocked_lifecycle(normalized, operation)
    if policy_block:
        return policy_block
    if payload is None:
        return _error("missing_input", "payload is required")
    sensitive_path = _find_sensitive_key(payload)
    if sensitive_path:
        return _error("unsafe_sensitive_input", f"payload contains sensitive key `{sensitive_path}`")
    if normalized == "wizard_chart":
        unsupported = _wizard_chart_error(payload, operation=operation)
        if unsupported:
            return unsupported
    if normalized == "ql_chart":
        unsupported = _ql_chart_error(payload, operation=operation, approval_provenance=approval_provenance)
        if unsupported:
            return unsupported
    method = OBJECT_METHODS.get(normalized, {}).get(operation)
    schema = get_method_schema(method) if method else {"mode": "unknown"}
    validation = validate_method_request(method, payload) if method else {"ok": False, "issues": ["method unavailable"], "schema_ref": ""}
    if not validation["ok"]:
        return {
            "ok": False,
            "object_type": normalized,
            "operation": operation,
            "method": method,
            "method_available": bool(method),
            "method_schema": schema,
            "payload_keys": sorted(payload),
            "request_schema_ref": validation["schema_ref"],
            "issues": validation["issues"],
            "error": {"category": "datalens_validation_error", "message": "; ".join(validation["issues"])},
        }
    return {
        "ok": True,
        "object_type": normalized,
        "operation": operation,
        "method": method,
        "method_available": bool(method),
        "method_schema": schema,
        "request_schema_ref": validation["schema_ref"],
        "payload_keys": sorted(payload),
    }


def dl_list_related_objects(entry_ids: list[str], client: Any | None = None) -> dict[str, Any]:
    if not entry_ids:
        return _error("missing_input", "entry_ids is required")
    try:
        active_client = client or DataLensApiClient(DataLensConfig.from_env())
        return {"ok": True, "method": "getEntriesRelations", "response": active_client.rpc("getEntriesRelations", {"entryIds": entry_ids})}
    except Exception as exc:  # noqa: BLE001
        return _error_result(exc)


def dl_get_dataset_schema(
    dataset_id: str = "",
    dataset: dict[str, Any] | None = None,
    required_fields: list[str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    source = dataset
    if source is None and dataset_id:
        read = dl_read_object("dataset", dataset_id, response_mode="full", inline_char_budget=100_000, client=client)
        if not read.get("ok"):
            return read
        source = read.get("response") or {}
    if source is None:
        return _error("missing_input", "dataset_id or dataset is required")
    fields = _extract_fields(source)
    return {
        "ok": True,
        "dataset_id": dataset_id or source.get("datasetId") or source.get("id") or "",
        "fields": fields,
        "field_validation": validate_field_availability(required_fields or [], {"fields": fields}),
    }


def dl_plan_object_create(
    object_type: str,
    payload: dict[str, Any] | None = None,
    source_adapter: str = "",
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    return _guarded_write_plan(
        object_type,
        "create",
        payload,
        source_adapter=source_adapter,
        delivery_intent_text=delivery_intent_text,
        approved=None,
    )


def dl_plan_object_update(
    object_type: str,
    payload: dict[str, Any] | None = None,
    mode: str = "save",
    source_adapter: str = "",
    lifecycle_operation: str = "update",
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    return _guarded_write_plan(
        object_type,
        lifecycle_operation or "update",
        payload,
        mode=mode,
        source_adapter=source_adapter,
        delivery_intent_text=delivery_intent_text,
        approved=None,
    )


def dl_validate_object(
    object_type: str,
    payload: dict[str, Any] | None = None,
    operation: str = "update",
    source_adapter: str = "",
    execute_validation: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    normalized = _normalize_object_type(object_type)
    lifecycle_operation = "validate" if normalized == "dataset" else operation
    plan = _guarded_write_plan(
        object_type,
        lifecycle_operation,
        payload,
        mode="save",
        source_adapter=source_adapter,
        approval_provenance=None,
    )
    if not plan.get("ok"):
        return plan


    result = {
        key: value
        for key, value in plan.items()
        if key
        in {
            "ok",
            "implemented",
            "object_type",
            "operation",
            "method",
            "method_schema",
            "request_schema_ref",
            "payload",
            "source_adapter",
            "compiled_from_openapi",
            "lifecycle_schema_version",
            "delivery_intent_decision",
            "approval_provenance",
        }
    }
    result["execute_now"] = False
    result["validation_result"] = {"executed": False}
    if execute_validation:
        if plan["method"] != "validateDataset":
            return _error("unsupported_validation", f"live validation is only available for validateDataset, not {plan['method']}")
        try:
            active_client = client or DataLensApiClient(DataLensConfig.from_env())
            response = active_client.rpc("validateDataset", plan["payload"])
            sanitized = sanitize_response(response)
            result["validation_result"] = {
                "executed": True,
                "ok": True,
                "method": "validateDataset",
                "summary": {
                    "response_keys": sorted(sanitized) if isinstance(sanitized, dict) else [],
                    "metadata": serialized_metadata(sanitized),
                },
            }
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["validation_result"] = {"executed": True, "ok": False, "method": "validateDataset"}
            result["error"] = _error_result(exc)["error"]
    return result


def dl_compile_guarded_rpc_request(
    method: str,
    payload: dict[str, Any] | None = None,
    object_type: str = "",
    operation: str = "",
    object_id: str = "",
    workbook_id: str = "",
    mode: str = "save",
    base_revision: str = "",
    fresh_read_artifact_path: str = "",
    expected_readback_branch: str = "",
    publish_source_artifact: str = "",
    changed_sections: list[str] | None = None,
) -> dict[str, Any]:
    if not method:
        return _error("missing_input", "method is required")
    if not isinstance(payload, dict) or not payload:
        return _error("missing_input", "payload is required")
    return compile_guarded_rpc_request(
        method,
        payload,
        object_type=object_type,
        operation=operation,
        object_id=object_id,
        workbook_id=workbook_id,
        mode=mode,
        base_revision=base_revision,
        fresh_read_artifact_path=fresh_read_artifact_path,
        expected_readback_branch=expected_readback_branch,
        publish_source_artifact=publish_source_artifact,
        changed_sections=changed_sections,
        approval_provenance=None,
    )


def dl_plan_publish_from_saved(
    object_type: str,
    saved_readback_path: str = "",
    object_id: str = "",
    object_ids: list[str] | None = None,
    target: str = "",
    project_root: str = ".",
    readback_mode: str = "minimal",
    approved: bool = False,
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan

    normalized = _normalize_object_type(object_type)
    plan = create_publish_safe_apply_plan(
        project_root=project_root,
        target=target or normalized or object_type,
        object_type=normalized or object_type,
        object_id=object_id,
        object_ids=object_ids,
        saved_readback_path=saved_readback_path,
        approved=approved,
        readback_mode=readback_mode,
    )
    plan["delivery_intent_decision"] = _delivery_intent_decision(
        delivery_intent_text,
        default_text="implement",
        target_known=_known_target(object_id, object_ids or [], saved_readback_path),
        approved=approved,
        fresh_readback_available=True,
        revision_preservation_available=True,
        saved_readback_available=bool(saved_readback_path),
        saved_readback_fresh=bool(plan.get("ok")),
        proof_path=str(Path(project_root) / "artifacts" / "publish_safe_apply_plan.json"),
        target_chart_id=object_id,
    )
    return plan


def dl_create_editor_chart_plan(entry: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("editor_chart", "create", entry, delivery_intent_text=delivery_intent_text)


def dl_update_editor_chart_plan(
    entry: dict[str, Any] | None = None,
    mode: str = "save",
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    return _guarded_write_plan("editor_chart", "update", entry, mode=mode, delivery_intent_text=delivery_intent_text)


def dl_create_wizard_chart_plan(entry: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("wizard_chart", "create", entry, delivery_intent_text=delivery_intent_text)


def dl_update_wizard_chart_plan(
    entry: dict[str, Any] | None = None,
    mode: str = "save",
    source_adapter: str = "",
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    return _guarded_write_plan(
        "wizard_chart",
        "update",
        entry,
        mode=mode,
        source_adapter=source_adapter,
        delivery_intent_text=delivery_intent_text,
    )


def dl_create_dashboard_plan(entry: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("dashboard", "create", entry, delivery_intent_text=delivery_intent_text)


def dl_update_dashboard_plan(
    entry: dict[str, Any] | None = None,
    mode: str = "save",
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    return _guarded_write_plan("dashboard", "update", entry, mode=mode, delivery_intent_text=delivery_intent_text)


def dl_plan_dashboard_tab_update(
    current_dashboard: dict[str, Any] | None = None,
    tab: dict[str, Any] | None = None,
    tab_operation: str = "append",
    tab_id: str = "",
) -> dict[str, Any]:
    """Plan an append/replace dashboard tab update while preserving unrelated tabs."""
    if not isinstance(current_dashboard, dict) or not current_dashboard:
        return _error("missing_input", "current_dashboard is required")
    if not isinstance(tab, dict) or not tab:
        return _error("missing_input", "tab is required")
    if tab_operation not in {"append", "replace"}:
        return _error("datalens_validation_error", "tab_operation must be append or replace")
    sensitive_path = _find_sensitive_key(tab)
    if sensitive_path:
        return _error("unsafe_sensitive_input", f"tab contains sensitive key `{sensitive_path}`")

    proposed_dashboard = deepcopy(current_dashboard)
    tabs_info = _dashboard_tabs(proposed_dashboard)
    if tabs_info is None:
        return _error("missing_input", "current_dashboard must contain a tabs list")
    tabs, tabs_path = tabs_info
    original_count = len(tabs)
    changed_paths: list[str] = []

    if tab_operation == "append":
        tabs.append(deepcopy(tab))
        changed_paths.append(f"{tabs_path}[{original_count}]")
    else:
        target_id = tab_id or str(tab.get("id") or tab.get("tabId") or tab.get("title") or "")
        if not target_id:
            return _error("missing_input", "tab_id or tab id/tabId/title is required for replace")
        replaced = False
        for index, existing in enumerate(tabs):
            if not isinstance(existing, dict):
                continue
            existing_id = str(existing.get("id") or existing.get("tabId") or existing.get("title") or "")
            if existing_id == target_id:
                tabs[index] = deepcopy(tab)
                changed_paths.append(f"{tabs_path}[{index}]")
                replaced = True
                break
        if not replaced:
            return _error("manual_review", f"tab `{target_id}` was not found for replacement")

    return {
        "ok": True,
        "implemented": True,
        "object_type": "dashboard",
        "operation": f"tab_{tab_operation}",
        "method": "updateDashboard",
        "method_schema": get_method_schema("updateDashboard"),
        "execute_now": False,
        "safe_apply_required": True,
        "fresh_read_required": True,
        "preserve_revision": True,
        "preserve_existing_metadata": True,
        "force_legacy_title_hint_metadata": False,
        "publish_separate": True,
        "changed_paths": changed_paths,
        "unchanged_tab_count": original_count if tab_operation == "append" else max(original_count - 1, 0),
        "proposed_dashboard": proposed_dashboard,
        "action_sequence": [
            {"step": "fresh_read", "method": "getDashboard", "branch": "saved"},
            {"step": "save", "method": "updateDashboard", "mode": "save"},
            {"step": "readback_saved", "method": "getDashboard", "branch": "saved"},
        ],
    }


def dl_create_connector_plan(config: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("connector", "create", config, delivery_intent_text=delivery_intent_text)


def dl_update_connector_plan(config: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("connector", "update", config, delivery_intent_text=delivery_intent_text)


def dl_create_dataset_plan(config: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("dataset", "create", config, delivery_intent_text=delivery_intent_text)


def dl_update_dataset_plan(config: dict[str, Any] | None = None, delivery_intent_text: str = "") -> dict[str, Any]:
    return _guarded_write_plan("dataset", "update", config, delivery_intent_text=delivery_intent_text)


def dl_plan_guarded_dataset_update(
    dataset_id: str = "",
    current_dataset: dict[str, Any] | None = None,
    proposed_dataset: dict[str, Any] | None = None,
    workbook_id: str = "",
    affected_chart_payloads: list[dict[str, Any]] | None = None,
    validate_only: bool = True,
    allow_guid_changes: bool = False,
    execute_validation: bool = False,
    delivery_intent_text: str = "",
    project_root: str = ".",
    client: Any | None = None,
) -> dict[str, Any]:
    """Plan a guarded validateDataset/updateDataset workflow without execution."""
    effective_authorized = _request_authorizes_standard_write(
        delivery_intent_text,
        default_text="implement" if not validate_only else "plan only",
    )
    if not dataset_id:
        return _error("missing_input", "dataset_id is required")
    if not isinstance(current_dataset, dict) or not current_dataset:
        return _error("missing_input", "current_dataset is required")
    if not isinstance(proposed_dataset, dict) or not proposed_dataset:
        return _error("missing_input", "proposed_dataset is required")
    sensitive_path = _find_sensitive_key(proposed_dataset)
    if sensitive_path:
        return _error("unsafe_sensitive_input", f"proposed_dataset contains sensitive key `{sensitive_path}`")
    validate_compiled = compile_method_request(
        "validateDataset",
        proposed_dataset,
        object_type="dataset",
        object_id=dataset_id,
        workbook_id=workbook_id,
    )
    if not validate_compiled["ok"]:
        return _error("datalens_validation_error", validate_compiled["error"]["message"])
    update_compiled = compile_method_request(
        "updateDataset",
        proposed_dataset,
        object_type="dataset",
        object_id=dataset_id,
    )
    if not update_compiled["ok"]:
        return _error("datalens_validation_error", update_compiled["error"]["message"])

    guid_report = _dataset_guid_report(
        current_dataset,
        proposed_dataset,
        affected_chart_payloads or [],
        allow_guid_changes=allow_guid_changes,
    )
    blocked_reasons = list(guid_report["blocked_reasons"])
    calculated_field_report = _dataset_calculated_field_report(proposed_dataset)
    blocked_reasons.extend(
        f"calculated field {issue['field']}: {issue['category']}"
        for issue in calculated_field_report["issues"]
        if issue.get("severity") == "error"
    )
    current_dataset_entry = current_dataset.get("dataset") if isinstance(current_dataset.get("dataset"), dict) else current_dataset
    current_revision = str(
        _first_scalar(current_dataset_entry, current_dataset, keys=("revId", "rev_id", "revisionId", "versionId")) or ""
    )
    if not validate_only and not current_revision:
        blocked_reasons.append("current_dataset revId/revisionId is required for guarded updateDataset")
    semantic_preflight = validate_payload_sql_performance(
        {"dataset": proposed_dataset, "charts": affected_chart_payloads or []},
        source=f"dataset_update.{dataset_id}",
    )
    sql_runtime_reality = build_sql_runtime_reality_check(
        payload={"dataset": proposed_dataset, "charts": affected_chart_payloads or []},
        dialect="clickhouse",
        target_execution_engine="datalens_clickhouse",
        validated_by=["static_lint", "validateDataset"] if execute_validation else ["static_lint"],
        dialect_equivalent=False,
        result="not_run",
    )
    blocked_reasons.extend(f"sql/performance preflight {issue}" for issue in semantic_preflight["issues"])
    if not validate_only and not effective_authorized:
        blocked_reasons.append("request intent does not authorize updateDataset execution")
    mode = "validate_only" if validate_only else "save"
    action_sequence = [
        {"step": "fresh_read", "method": "getDataset", "dataset_id": dataset_id},
        {
            "step": "validate",
            "method": "validateDataset",
            "dataset_id": dataset_id,
            "gate_role": "schema_hint",
            "acceptance_gate": False,
        },
    ]
    if not validate_only:
        action_sequence.extend(
            [
                {"step": "save", "method": "updateDataset", "dataset_id": dataset_id},
                {"step": "readback_saved", "method": "getDataset", "dataset_id": dataset_id},
            ]
        )
    validation_result: dict[str, Any] = {"executed": False}
    if execute_validation:
        try:
            active_client = client or DataLensApiClient(DataLensConfig.from_env())
            response = active_client.rpc("validateDataset", validate_compiled["payload"])
            sanitized = sanitize_response(response)
            validation_result = {
                "executed": True,
                "ok": True,
                "method": "validateDataset",
                "summary": {
                    "response_keys": sorted(sanitized) if isinstance(sanitized, dict) else [],
                    "metadata": serialized_metadata(sanitized),
                },
            }
        except Exception as exc:  # noqa: BLE001
            validation_result = {
                "executed": True,
                "ok": False,
                "method": "validateDataset",
                "error": _error_result(exc)["error"],
            }
            blocked_reasons.append("validateDataset failed")

    safe_apply_plan = None
    if not validate_only and effective_authorized and not blocked_reasons:
        safe_apply_plan = create_safe_apply_plan(
            project_root=project_root,
            approved=effective_authorized,
            user_request_text=delivery_intent_text,
            actions=[
                {
                    "action": "update_dataset",
                    "method": "updateDataset",
                    "object_id": dataset_id,
                    "expected_rev_id": current_revision,
                    "payload": update_compiled["payload"],
                    "fresh_read_method": "getDataset",
                    "fresh_read_payload": {"datasetId": dataset_id},
                    "readback_method": "getDataset",
                    "readback_payload": {"datasetId": dataset_id},
                    "readback_mode": "minimal",
                    "requires_fresh_read": True,
                    "readback_required": True,
                    "preserve_unknown_fields": True,
                    "stale_revision_retry_policy": {
                        "enabled": True,
                        "max_retry_count": 1,
                        "fresh_read_before_retry": True,
                        "create_new_on_revision_mismatch": False,
                        "unresolved_status": "revision_conflict_unresolved",
                    },
                }
            ],
        )

    return {
        "ok": not blocked_reasons,
        "implemented": True,
        "object_type": "dataset",
        "dataset_id": dataset_id,
        "mode": mode,
        "validate_only": validate_only,
        "request_authorized": effective_authorized,
        "execute_now": False,
        "safe_apply_required": True,
        "fresh_read_required": True,
        "preserve_revision": True,
        "preserve_unknown_fields": True,
        "preserve_field_guids": not allow_guid_changes,
        "publish_separate": True,
        "validate_method": "validateDataset",
        "update_method": "updateDataset",
        "readback_method": "getDataset",
        "method_schema": get_method_schema("updateDataset"),
        "validate_request_payload": validate_compiled["payload"],
        "update_request_payload": update_compiled["payload"],
        "validation_result": validation_result,
        "validation_gate_classification": {
            "validateDataset": "schema_hint",
            "api_readback_parity": "structural_check",
            "browser_runtime_smoke": "acceptance_gate",
        },
        "revision_conflict_policy": {
            "retry_existing_update_once": True,
            "fresh_read_before_retry": True,
            "create_runtime_fix_fallback": False,
            "unresolved_status": "revision_conflict_unresolved",
        },
        "safe_apply_plan": safe_apply_plan,
        "action_sequence": action_sequence,
        "guid_report": guid_report,
        "calculated_field_report": calculated_field_report,
        "sql_performance_preflight": semantic_preflight,
        "sql_runtime_reality_check": sql_runtime_reality,
        "blocked_reasons": blocked_reasons,
        "delivery_intent_decision": _delivery_intent_decision(
            delivery_intent_text,
            default_text="plan only" if validate_only else "implement",
            target_known=_known_target(dataset_id),
            approved=effective_authorized,
            fresh_readback_available=bool(current_dataset),
            revision_preservation_available=True,
            saved_readback_available=False,
            target_workbook_id=workbook_id,
        ),
        "error": (
            {
                "category": "guarded_write_blocked",
                "message": "; ".join(blocked_reasons),
            }
            if blocked_reasons
            else None
        ),
    }


def dl_create_dataset_field_plan(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _not_implemented("dataset_field", "create", config, schema_path="schemas/field-config.schema.json")


def dl_update_dataset_field_plan(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _not_implemented("dataset_field", "update", config, schema_path="schemas/field-config.schema.json")


def dl_create_calculated_field_plan(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _not_implemented("calculated_field", "create", config, schema_path="schemas/calculated-field-config.schema.json")


def dl_update_calculated_field_plan(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _not_implemented("calculated_field", "update", config, schema_path="schemas/calculated-field-config.schema.json")


def dl_save_object_plan(
    object_type: str,
    entry: dict[str, Any] | None = None,
    delivery_intent_text: str = "",
    approval_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _guarded_write_plan(
        object_type,
        "update",
        entry,
        mode="save",
        delivery_intent_text=delivery_intent_text,
        approval_provenance=approval_provenance,
    )


def dl_publish_object_plan(
    object_type: str,
    entry: dict[str, Any] | None = None,
    delivery_intent_text: str = "",
    approval_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_object_type(object_type)
    source_adapter = (
        "saved_entry"
        if normalized in {"wizard_chart", "ql_chart"}
        and isinstance(entry, dict)
        and str(entry.get("branch") or entry.get("source_branch") or "").strip().lower() == "saved"
        else ""
    )
    return _guarded_write_plan(
        object_type,
        "update",
        entry,
        mode="publish",
        source_adapter=source_adapter,
        delivery_intent_text=delivery_intent_text,
        approval_provenance=approval_provenance,
    )


def _guarded_write_plan(
    object_type: str,
    operation: str,
    entry: dict[str, Any] | None,
    *,
    mode: str = "save",
    source_adapter: str = "",
    delivery_intent_text: str = "",
    approved: bool | None = None,
    approval_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_authorized = _request_authorizes_standard_write(
        delivery_intent_text,
        legacy_approved=approved,
        default_text="implement",
    )
    effective_provenance = _request_approval_provenance(
        delivery_intent_text,
        supplied=approval_provenance,
        authorized=effective_authorized,
    )
    normalized = _normalize_object_type(object_type)
    if not normalized:
        return _error("missing_input", "object_type is required")
    policy_block = _policy_blocked_lifecycle(normalized, operation)
    if policy_block:
        return policy_block
    if not isinstance(entry, dict) or not entry:
        return _error("missing_input", "entry is required")
    if mode not in {"save", "publish"}:
        return _error("datalens_validation_error", "mode must be save or publish")
    sensitive_path = _find_sensitive_key(entry)
    if sensitive_path:
        return _error("unsafe_sensitive_input", f"entry contains sensitive key `{sensitive_path}`")
    if normalized == "wizard_chart":
        unsupported = _wizard_chart_error(
            entry,
            operation=operation,
            source_adapter=source_adapter,
        )
        if unsupported:
            return unsupported
    if normalized == "ql_chart":
        unsupported = _ql_chart_error(
            entry,
            operation=operation,
            source_adapter=source_adapter,
            approval_provenance=effective_provenance,
        )
        if unsupported:
            return unsupported
    method = OBJECT_METHODS.get(normalized, {}).get(operation)
    if not method:
        return _unavailable(normalized, operation)
    prepared = _prepare_lifecycle_payload(
        normalized,
        operation,
        method,
        entry,
        source_adapter=source_adapter,
    )
    if not prepared["ok"]:
        return prepared
    payload_input = prepared["payload"]
    compiled = compile_method_request(
        method,
        payload_input,
        object_type=normalized,
        operation=operation,
        object_id=_object_id_for_payload(normalized, payload_input),
        mode=mode,
    )
    if not compiled["ok"]:
        return _error("datalens_validation_error", compiled["error"]["message"])
    payload = compiled["payload"]
    dataset_shape_error = _dataset_request_shape_error(method, payload)
    if dataset_shape_error:
        return dataset_shape_error
    semantic_preflight = validate_payload_sql_performance(payload, source=f"{normalized}.{operation}")
    if not semantic_preflight["ok"]:
        return {
            **_error("datalens_validation_error", "; ".join(semantic_preflight["issues"])),
            "object_type": normalized,
            "operation": operation,
            "method": method,
            "sql_performance_preflight": semantic_preflight,
        }
    result = {
        "ok": True,
        "implemented": True,
        "object_type": normalized,
        "operation": operation,
        "method": method,
        "method_schema": get_method_schema(method),
        "request_schema_ref": compiled["schema_ref"],
        "mode": None if operation == "create" else mode,
        "source_adapter": prepared["adapter"],
        "compiled_from_openapi": True,
        "lifecycle_schema_version": "2026-06-25.lifecycle.v1",
        "safe_apply_required": True,
        "execute_now": False,
        "fresh_read_required": operation != "create",
        "preserve_revision": operation != "create",
        "preserve_unknown_fields": operation != "create",
        "readback_required": True,
        "publish_separate": mode != "publish",
        "payload": payload,
        "sql_performance_preflight": semantic_preflight,
        "delivery_intent_decision": _delivery_intent_decision(
            delivery_intent_text,
            default_text="implement" if mode == "publish" else "plan only",
            target_known=_object_target_known(normalized, operation, payload),
            approved=effective_authorized,
            fresh_readback_available=operation != "create",
            revision_preservation_available=operation != "create",
            saved_readback_available=mode == "publish",
            saved_readback_fresh=mode == "publish",
            target_workbook_id=str(payload.get("workbookId") or payload.get("workbook_id") or ""),
            target_dashboard_id=str(payload.get("dashboardId") or payload.get("dashboard_id") or ""),
            target_chart_id=str(payload.get("chartId") or payload.get("chart_id") or payload.get("entryId") or ""),
        ),
        "approval_provenance": _sanitize_approval_provenance(effective_provenance),
    }
    if operation == "create":
        result["creation_necessity_proof"] = create_necessity_proof(
            action={"operation": operation, "object_type": normalized, "method": method},
            payload=payload,
        )
        result["default_object_policy"] = "prefer_existing_object_update; create only with necessity proof"
    return result


def _delivery_intent_decision(
    delivery_intent_text: str = "",
    *,
    default_text: str = "plan only",
    target_known: bool = False,
    approved: bool = False,
    approval_source: str = "",
    approval_sources: list[str] | None = None,
    fresh_readback_available: bool = False,
    revision_preservation_available: bool = False,
    saved_readback_available: bool = False,
    saved_readback_fresh: bool | None = None,
    proof_path: str = "",
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
) -> dict[str, Any]:
    return resolve_delivery_intent_from_env(
        delivery_intent_text,
        default_text=default_text,
        target_known=target_known,
        approved=approved,
        approval_source=approval_source,
        approval_sources=approval_sources,
        fresh_readback_available=fresh_readback_available,
        revision_preservation_available=revision_preservation_available,
        saved_readback_available=saved_readback_available,
        saved_readback_fresh=saved_readback_fresh,
        proof_path=proof_path,
        target_workbook_id=target_workbook_id,
        target_dashboard_id=target_dashboard_id,
        target_chart_id=target_chart_id,
    )


def _known_target(*values: Any) -> bool:
    for value in values:
        if isinstance(value, list):
            if _known_target(*value):
                return True
            continue
        text = str(value or "").strip()
        if text and text.lower() not in PLACEHOLDER_TARGETS:
            return True
    return False


def _request_authorizes_standard_write(
    delivery_intent_text: str,
    *,
    legacy_approved: bool | None = None,
    default_text: str = "implement",
) -> bool:
    if legacy_approved is not None:
        return bool(legacy_approved)
    normalized = normalize_user_request(delivery_intent_text or default_text)
    return bool(
        normalized.task_intent in {"implement", "fix", "enhance", "redesign", "update"}
        and normalized.publish_override not in {"plan_only", "dry_run"}
        and not normalized.destructive_actions
    )


def _request_approval_provenance(
    delivery_intent_text: str,
    *,
    supplied: dict[str, Any] | None,
    authorized: bool,
) -> dict[str, Any]:
    if isinstance(supplied, dict) and supplied:
        return supplied
    raw_text = str(delivery_intent_text or "")
    normalized = normalize_user_request(raw_text or "implement")
    return {
        "selection_origin": "explicit_user_request" if normalized.route_intent == "ql_explicit" else "current_user_request",
        "selection_reason": normalized.route_intent,
        "request_digest": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "approval_sources": ["current_user_request"] if authorized else [],
    }


def _object_target_known(object_type: str, operation: str, payload: dict[str, Any]) -> bool:
    if operation == "create":
        location_known = _known_target(payload.get("workbookId"), payload.get("parentId"), payload.get("collectionId"))
        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        planned_identity_known = _known_target(
            payload.get("name"),
            payload.get("title"),
            payload.get("key"),
            entry.get("name"),
            data.get("name"),
            data.get("title"),
        )
        return location_known and planned_identity_known
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    object_id = _object_id_for_payload(object_type, payload)
    return _known_target(object_id, entry.get("entryId"), entry.get("chartId"), entry.get("dashboardId"), entry.get("id"))


def _prepare_lifecycle_payload(
    object_type: str,
    operation: str,
    method: str,
    entry: dict[str, Any],
    *,
    source_adapter: str = "",
) -> dict[str, Any]:
    requested_adapter = str(source_adapter or "").strip()
    if requested_adapter and requested_adapter not in SOURCE_ADAPTERS:
        return _error(
            "unsupported_source_adapter",
            f"source_adapter must be one of {sorted(SOURCE_ADAPTERS)}",
        )
    if requested_adapter == "artifact_path":
        loaded = _load_artifact_source(entry)
        if not loaded["ok"]:
            return loaded
        entry = loaded["payload"]
        requested_adapter = loaded["adapter"]
    elif requested_adapter == "project_manifest_reference":
        loaded = _load_project_manifest_source(entry)
        if not loaded["ok"]:
            return loaded
        entry = loaded["payload"]
        requested_adapter = loaded["adapter"]
    elif requested_adapter in {"rpc_readback_envelope", "saved_entry", "published_entry"}:
        loaded = _extract_lifecycle_readback_source(object_type, entry, requested_adapter)
        if not loaded["ok"]:
            return loaded
        entry = loaded["payload"]
    elif requested_adapter == "canonical_object_payload":
        entry = _extract_canonical_object_payload(object_type, entry)

    if requested_adapter in {"rpc_readback_envelope", "saved_entry", "published_entry", "canonical_object_payload"}:
        shape_error = _canonical_payload_shape_error(object_type, entry)
        if shape_error:
            return shape_error

    if not requested_adapter:
        ambiguity = _ambiguous_mutation_source(object_type, operation, entry)
        if ambiguity:
            return ambiguity
        adapter = (
            "canonical_request_payload"
            if validate_method_request(method, entry)["ok"]
            else "canonical_object_payload"
        )
    else:
        adapter = requested_adapter

    return {"ok": True, "payload": dict(entry), "adapter": adapter}


def _load_artifact_source(entry: dict[str, Any]) -> dict[str, Any]:
    artifact_path = str(entry.get("artifact_path") or entry.get("path") or "").strip()
    if not artifact_path:
        return _error("missing_input", "artifact_path source adapter requires artifact_path")
    path = Path(artifact_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return _error("missing_artifact", f"artifact_path does not exist: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _error("invalid_artifact", f"artifact_path is not valid JSON: {exc.__class__.__name__}")
    if not isinstance(loaded, dict) or not loaded:
        return _error("invalid_artifact", "artifact_path must contain a JSON object")
    return {"ok": True, "payload": loaded, "adapter": "artifact_path"}


def _load_project_manifest_source(entry: dict[str, Any]) -> dict[str, Any]:
    manifest_path = str(entry.get("manifest_path") or "").strip()
    object_id = str(entry.get("object_id") or entry.get("entryId") or entry.get("id") or "").strip()
    if not manifest_path or not object_id:
        return _error("missing_input", "project_manifest_reference requires manifest_path and object_id")
    path = Path(manifest_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return _error("missing_artifact", f"manifest_path does not exist: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _error("invalid_artifact", f"manifest_path is not valid JSON: {exc.__class__.__name__}")
    payload = _manifest_payload_by_id(manifest, object_id)
    if not payload:
        return _error("missing_object_id", f"manifest object_id was not found: {object_id}")
    return {"ok": True, "payload": payload, "adapter": "project_manifest_reference"}


def _manifest_payload_by_id(manifest: Any, object_id: str) -> dict[str, Any]:
    if isinstance(manifest, dict):
        for key in ("objects", "entries", "payloads"):
            child = manifest.get(key)
            found = _manifest_payload_by_id(child, object_id)
            if found:
                return found
        candidate_id = str(
            manifest.get("object_id")
            or manifest.get("entryId")
            or manifest.get("chartId")
            or manifest.get("dashboardId")
            or manifest.get("datasetId")
            or manifest.get("connectionId")
            or manifest.get("id")
            or ""
        ).strip()
        if candidate_id == object_id:
            payload = manifest.get("payload") if isinstance(manifest.get("payload"), dict) else manifest
            return dict(payload)
        for value in manifest.values():
            found = _manifest_payload_by_id(value, object_id)
            if found:
                return found
    elif isinstance(manifest, list):
        for item in manifest:
            found = _manifest_payload_by_id(item, object_id)
            if found:
                return found
    return {}


def _extract_lifecycle_readback_source(object_type: str, entry: dict[str, Any], adapter: str) -> dict[str, Any]:
    if adapter in {"saved_entry", "published_entry"}:
        expected = "saved" if adapter == "saved_entry" else "published"
        branch = str(entry.get("branch") or entry.get("source_branch") or "").strip().lower()
        if branch and branch != expected:
            return _error("invalid_source_adapter", f"{adapter} requires {expected} branch, got {branch}")
    if object_type == "dataset":
        payload = _extract_dataset_readback_payload(entry)
    elif object_type in {"connector", "connection"}:
        payload = _extract_connection_readback_payload(entry)
    else:
        payload = _extract_entry_readback_payload(entry)
    if not payload:
        return _error("invalid_source_adapter", f"{adapter} could not extract an object payload")
    shape_error = _canonical_payload_shape_error(object_type, payload)
    if shape_error:
        return shape_error
    return {"ok": True, "payload": payload}


def _extract_entry_readback_payload(value: dict[str, Any]) -> dict[str, Any]:
    current = _unwrap_result_envelope(value)
    for key in ("entry", "dashboard", "chart", "object"):
        nested = current.get(key)
        if isinstance(nested, dict):
            nested_entry = nested.get("entry")
            return dict(nested_entry if isinstance(nested_entry, dict) else nested)
    return dict(current)


def _extract_dataset_readback_payload(value: dict[str, Any]) -> dict[str, Any]:
    current = _unwrap_result_envelope(value)
    if isinstance(current.get("dataset"), dict):
        dataset = dict(current["dataset"])
        dataset_id = str(current.get("datasetId") or dataset.get("datasetId") or dataset.get("id") or "").strip()
        if dataset_id and "datasetId" not in dataset:
            dataset["datasetId"] = dataset_id
        return dataset
    return dict(current)


def _extract_connection_readback_payload(value: dict[str, Any]) -> dict[str, Any]:
    current = _unwrap_result_envelope(value)
    for key in ("connection", "connector", "object"):
        nested = current.get(key)
        if isinstance(nested, dict):
            return dict(nested)
    return dict(current)


def _unwrap_result_envelope(value: dict[str, Any]) -> dict[str, Any]:
    current = value
    for _ in range(6):
        next_value = None
        for key in ("result", "response"):
            nested = current.get(key)
            if isinstance(nested, dict):
                next_value = nested
                break
        if next_value is None:
            break
        current = next_value
    return current


def _extract_canonical_object_payload(object_type: str, value: dict[str, Any]) -> dict[str, Any]:
    if object_type == "dataset":
        return _extract_dataset_readback_payload(value)
    if object_type in {"connector", "connection"}:
        return _extract_connection_readback_payload(value)
    return _extract_entry_readback_payload(value)


def _canonical_payload_shape_error(object_type: str, value: dict[str, Any]) -> dict[str, Any] | None:
    if _contains_result_envelope(value):
        return _error("malformed_readback_envelope", "object payload still contains nested result/response envelope fields")
    if object_type == "dataset":
        object_id = str(value.get("datasetId") or value.get("dataset_id") or value.get("id") or "").strip()
        if not object_id:
            return _error("missing_object_id", "dataset payload must contain datasetId before lifecycle planning")
    elif object_type in {"connector", "connection"}:
        object_id = str(value.get("connectionId") or value.get("connection_id") or value.get("id") or "").strip()
        if not object_id:
            return _error("missing_object_id", "connection payload must contain connectionId or id before lifecycle planning")
    elif object_type in {"dashboard", "editor_chart", "wizard_chart", "ql_chart"}:
        entry = value.get("entry") if isinstance(value.get("entry"), dict) else value
        object_id = str(
            entry.get("entryId")
            or entry.get("id")
            or entry.get("dashboardId")
            or entry.get("chartId")
            or ""
        ).strip()
        if not object_id:
            return _error("missing_object_id", f"{object_type} payload must contain an object id before lifecycle planning")
    return None


def _contains_result_envelope(value: Any) -> bool:
    if isinstance(value, dict):
        if isinstance(value.get("result"), dict) or isinstance(value.get("response"), dict):
            return True
        return any(_contains_result_envelope(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_result_envelope(item) for item in value)
    return False


def _ambiguous_mutation_source(object_type: str, operation: str, value: dict[str, Any]) -> dict[str, Any] | None:
    if _summary_only_read(value):
        return _error("summary_readback_not_mutation_source", "summary-only readbacks cannot be used as mutation payloads")
    if any(isinstance(value.get(key), dict) for key in ("result", "response")):
        return _error("explicit_adapter_required", "RPC readback envelopes require source_adapter=rpc_readback_envelope")
    if object_type == "dataset" and operation in {"update", "validate"}:
        if _is_exact_dataset_mutation_request(value):
            return None
        if _looks_like_dataset_readback(value):
            return _error(
                "explicit_adapter_required",
                "dataset readback shapes require source_adapter=rpc_readback_envelope or canonical_object_payload",
            )
    if object_type in {"connector", "connection"} and operation == "update":
        if _is_exact_connection_mutation_request(value):
            return None
        if _looks_like_connection_readback(value):
            return _error(
                "explicit_adapter_required",
                "connection readback shapes require source_adapter=rpc_readback_envelope or canonical_object_payload",
            )
    return None


def _summary_only_read(value: dict[str, Any]) -> bool:
    return bool(value.get("summary")) and not any(key in value for key in ("entry", "data", "dataset", "connection", "connector"))


def _is_exact_dataset_mutation_request(value: dict[str, Any]) -> bool:
    data = value.get("data")
    return bool(value.get("datasetId")) and isinstance(data, dict) and isinstance(data.get("dataset"), dict)


def _is_exact_connection_mutation_request(value: dict[str, Any]) -> bool:
    return bool(value.get("connectionId")) and isinstance(value.get("data"), dict)


def _looks_like_dataset_readback(value: dict[str, Any]) -> bool:
    keys = set(value)
    identity_keys = {"datasetId", "dataset_id", "id", "revId", "revisionId"}
    content_keys = {"fields", "sources", "source_avatars", "result_schema", "data_export_forbidden", "validation"}
    return bool(keys & identity_keys) and bool(keys & content_keys)


def _looks_like_connection_readback(value: dict[str, Any]) -> bool:
    keys = set(value)
    identity_keys = {"connectionId", "connection_id", "id", "revId", "revisionId"}
    content_keys = {"type", "name", "params", "parameters", "options", "data_export_forbidden"}
    return bool(keys & identity_keys) and bool(keys & content_keys)


def _dataset_request_shape_error(method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if method not in {"updateDataset", "validateDataset"}:
        return None
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("dataset"), dict):
        return _error("datalens_validation_error", "updateDataset/validateDataset requires data.dataset")
    if "dataset" in payload:
        return _error("datalens_validation_error", "data.dataset must be the only dataset wrapper in updateDataset/validateDataset")
    nested = data["dataset"]
    if isinstance(nested.get("data"), dict) and isinstance(nested["data"].get("dataset"), dict):
        return _error("datalens_validation_error", "data.dataset is double-wrapped")
    return None


def _project_read_response(
    *,
    response: dict[str, Any],
    object_type: str,
    object_id: str,
    branch: str,
    method: str,
    contract: dict[str, Any],
    response_mode: str,
    inline_char_budget: int,
    project_root: str,
    run_id: str,
) -> dict[str, Any]:
    summary = _read_object_summary(response, object_type=object_type, object_id=object_id, branch=branch)
    projected = project_response(
        kind=object_type,
        response=response,
        summary=summary,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id or f"read_{object_type}_{object_id}",
    )
    projected.update(
        {
            "method": method,
            "object_type": object_type,
            "object_id": object_id,
            "branch": branch if contract.get("branch_semantics") == "saved_or_published" else "",
            "contract": contract,
        }
    )
    return projected


def _read_object_summary(response: dict[str, Any], *, object_type: str, object_id: str, branch: str) -> dict[str, Any]:
    entry = _first_dict(response, keys=("entry", "chart", "dashboard", "dataset", "connection", "report", "workbook", "collection"))
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    if not data and isinstance(response.get("data"), dict):
        data = response["data"]
    payload = data if data else entry if entry else response
    links = _as_list(response.get("links") or entry.get("links") if isinstance(entry, dict) else [])
    dependency_ids = _dependency_ids(response)
    section_hashes = []
    if isinstance(payload, dict):
        for name, value in sorted(payload.items()):
            if name.lower() in {"data", "entry"} and isinstance(value, dict):
                continue
            section_hashes.append(
                {
                    "name": name,
                    "metadata": serialized_metadata(sanitize_response(value)),
                }
            )
    return {
        "schema_version": "2026-06-25.generic_object_summary.v1",
        "identity": {
            "id": _first_scalar(
                entry,
                response,
                keys=(
                    "entryId",
                    "chartId",
                    "dashboardId",
                    "datasetId",
                    "connectionId",
                    "workbookId",
                    "collectionId",
                    "id",
                ),
            )
            or object_id,
            "rev_id": _first_scalar(entry, response, keys=("revId", "rev_id", "revisionId", "versionId")),
            "saved_id": _first_scalar(entry, response, keys=("savedId", "saved_id")),
        },
        "object_type": object_type,
        "branch": branch,
        "title": str(_first_scalar(entry, data, response, keys=("displayKey", "title", "name")) or ""),
        "counts": {
            "links": len(links),
            "dependencies": sum(len(values) for values in dependency_ids.values()),
            "top_level_keys": len(response) if isinstance(response, dict) else 0,
            "payload_keys": len(payload) if isinstance(payload, dict) else 0,
        },
        "dependency_ids": dependency_ids,
        "section_hashes": section_hashes[:80],
        "payload_metadata": serialized_metadata(sanitize_response(payload)),
        "response_sha256": stable_sha256(sanitize_response(response)),
    }


def _first_dict(value: dict[str, Any], *, keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        item = value.get(key)
        if isinstance(item, dict):
            return item
    result = value.get("result")
    if isinstance(result, dict):
        return _first_dict(result, keys=keys) or result
    return {}


def _first_scalar(*values: Any, keys: tuple[str, ...]) -> Any:
    for value in values:
        if not isinstance(value, dict):
            continue
        for key in keys:
            item = value.get(key)
            if isinstance(item, str | int | float | bool) and item != "":
                return item
    return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dependency_ids(value: Any) -> dict[str, list[str]]:
    ids: dict[str, set[str]] = {"dataset": set(), "connection": set(), "entry": set()}
    _collect_dependency_ids(value, ids)
    return {key: sorted(items)[:200] for key, items in ids.items() if items}


def _collect_dependency_ids(value: Any, ids: dict[str, set[str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if isinstance(item, str) and item:
                if lowered in {"datasetid", "dataset_id", "datasetentryid"}:
                    ids["dataset"].add(item)
                elif lowered in {"connectionid", "connection_id", "connid", "conn_id"}:
                    ids["connection"].add(item)
                elif lowered in {"entryid", "entry_id", "chartid", "chart_id", "dashboardid", "dashboard_id"}:
                    ids["entry"].add(item)
            _collect_dependency_ids(item, ids)
    elif isinstance(value, list):
        for item in value:
            _collect_dependency_ids(item, ids)


def _bounded_remediation(category: str, method: str, object_type: str) -> str:
    if category == "auth_failure":
        return f"Retry {method} after verifying DATALENS_ENV_FILE auth; do not print credential values."
    if category == "datalens_validation_error":
        return f"Check the object id, branch, workbook id and official {method} request schema for {object_type}."
    if category == "unavailable_api_method":
        return f"Use workbook inventory or an evidence-backed supported parent read for {object_type}."
    return f"Retry {method} with the same read-only MCP path and preserve the structured error evidence."


def _not_implemented(
    object_type: str,
    operation: str,
    payload: dict[str, Any] | None,
    *,
    schema_path: str,
) -> dict[str, Any]:
    if payload is not None:
        sensitive_path = _find_sensitive_key(payload)
        if sensitive_path:
            return _error("unsafe_sensitive_input", f"payload contains sensitive key `{sensitive_path}`")
    return {
        "ok": False,
        "implemented": False,
        "object_type": object_type,
        "operation": operation,
        "schema_path": schema_path,
        "error": {
            "category": "unavailable_api_method",
            "message": (
                f"{operation} for {object_type} is represented as schema/spec only; "
                "no validated DataLens API method is implemented."
            ),
        },
    }


def _unavailable(object_type: str, operation: str) -> dict[str, Any]:
    return {
        "ok": False,
        "implemented": False,
        "object_type": object_type,
        "operation": operation,
        "error": {
            "category": "unavailable_api_method",
            "message": f"No curated DataLens API method is available for {operation} {object_type}.",
        },
    }


def _policy_blocked_lifecycle(object_type: str, operation: str) -> dict[str, Any] | None:
    normalized_operation = str(operation or "").strip().lower()
    if object_type == "connection" and normalized_operation in {"create", "update", "validate", "publish"}:
        return {
            **_error(
                "unavailable_api_method",
                "connection is read-only in generic lifecycle tools; request object_type='connector' or use "
                "dl_create_connector_plan/dl_update_connector_plan for the guarded createConnection/updateConnection route",
            ),
            "implemented": False,
            "object_type": object_type,
            "operation": normalized_operation,
            "lifecycle_semantics": {
                "read_object_type": "connection",
                "write_object_type": "connector",
                "read_method": "getConnection",
                "write_methods": ["createConnection", "updateConnection"],
            },
        }
    if normalized_operation == "move":
        return {
            **_error(
                "blocked_by_explicit_policy",
                "move operations are outside the guarded lifecycle write surface and require separate reviewed tooling",
            ),
            "implemented": False,
            "object_type": object_type,
            "operation": normalized_operation,
        }
    if object_type in PERMISSION_MUTATION_TYPES and normalized_operation in {"create", "update", "validate", "publish"}:
        return {
            **_error(
                "blocked_by_explicit_policy",
                "permission/access-binding mutations are outside the guarded lifecycle write surface",
            ),
            "implemented": False,
            "object_type": object_type,
            "operation": normalized_operation,
        }
    return None


def _error(category: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"category": category, "message": message}}


def _error_result(exc: Exception, *, fallback_category: str = "unknown_runtime_error") -> dict[str, Any]:
    text = str(exc)
    category = fallback_category
    if isinstance(exc, DataLensSafetyError):
        category = "unsafe_sensitive_input"
    elif isinstance(exc, DataLensApiError):
        lowered = text.lower()
        if "http 401" in lowered or "auth_" in lowered:
            category = "auth_failure"
        elif "validation_error" in lowered:
            category = "datalens_validation_error"
    return _error(category, _sanitize_message(text or exc.__class__.__name__))


def _normalize_object_type(object_type: str) -> str:
    normalized = (object_type or "").strip().lower().replace("-", "_")
    aliases = {
        "advanced_editor": "advanced_editor_chart",
        "editor": "editor_chart",
        "table_node": "table",
        "widget_table_node": "table",
        "control_node": "control",
        "widget_control_node": "control",
        "markdown_node": "markdown",
        "widget_markdown_node": "markdown",
        "report_node": "report",
        "ql": "ql_chart",
        "ql_chart_node": "ql_chart",
        "graph_ql_node": "ql_chart",
        "table_ql_node": "ql_chart",
    }
    return aliases.get(normalized, normalized)


def _find_sensitive_key(value: Any, path: str = "") -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if any(word in str(key).lower() for word in SENSITIVE_KEYWORDS):
                return child
            found = _find_sensitive_key(item, child)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_sensitive_key(item, f"{path}[{index}]")
            if found:
                return found
    return ""


def _sanitize_message(message: str) -> str:
    sanitized = message
    for keyword in SENSITIVE_KEYWORDS:
        sanitized = sanitized.replace(keyword.upper(), "<redacted-key>")
        sanitized = sanitized.replace(keyword, "<redacted-key>")
    return sanitized[:1000]


def _wizard_chart_error(
    entry: dict[str, Any],
    *,
    operation: str = "update",
    source_adapter: str = "",
) -> dict[str, Any] | None:
    route = str(entry.get("route") or "").strip()
    visualization_token = _wizard_visualization_token(entry)
    if operation == "create" and not visualization_token:
        return _error(
            "unsupported_chart_type",
            "Wizard creation requires an explicit supported visualization_id.",
        )
    if operation == "create" and not is_supported_wizard_visualization(visualization_token):
        return _error("unsupported_chart_type", f"Unknown Wizard visualization_id `{visualization_token}` is blocked for create.")
    if route and normalize_creation_route(route) != WIZARD_NATIVE_ROUTE:
        return _error("unsupported_chart_type", "Wizard chart route must be wizard_native.")
    if route == WIZARD_MAP_ALIAS and visualization_token != "geolayer":
        return _error("unsupported_chart_type", "wizard_map_native compatibility alias is valid only for geolayer.")
    if operation == "update":
        if source_adapter not in {"rpc_readback_envelope", "saved_entry"}:
            return _error(
                "fresh_saved_readback_required",
                "Wizard updates must be derived from a fresh getWizardChart saved readback.",
            )
        branch = str(entry.get("branch") or entry.get("source_branch") or "").strip().lower()
        if branch != "saved":
            return _error(
                "fresh_saved_readback_required",
                "Existing non-map Wizard updates require explicit branch=saved readback evidence.",
            )
        if not visualization_token:
            return _error(
                "wizard_visualization_token_missing",
                "Fresh getWizardChart saved readback must expose the existing visualization token.",
            )
        if not _lifecycle_revision_token(entry):
            return _error("fresh_saved_readback_required", "Wizard saved readback must include a fresh revision id.")
    return None


def _ql_chart_error(
    entry: dict[str, Any],
    *,
    operation: str,
    source_adapter: str = "",
    approval_provenance: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if operation not in {"create", "update"}:
        return _error("blocked_by_explicit_policy", "QL supports only guarded create/update; delete remains closed.")
    if normalize_creation_route(str(entry.get("route") or "")) != QL_EXPLICIT_ROUTE:
        return _error("ql_explicit_route_required", "QL create/update requires route=ql_explicit.")
    provenance = approval_provenance or (
        entry.get("approval_provenance") if isinstance(entry.get("approval_provenance"), dict) else {}
    )
    if provenance.get("selection_origin") != "explicit_user_request":
        return _error(
            "explicit_user_request_required",
            "QL create/update requires approval_provenance.selection_origin=explicit_user_request.",
        )
    if not (
        provenance.get("user_request_excerpt")
        or provenance.get("request_digest")
        or provenance.get("decision_id")
        or provenance.get("approval_sources")
    ):
        return _error("explicit_user_request_required", "QL approval provenance must include bounded request evidence.")
    data = _find_data_payload(entry)
    if not isinstance(data, dict) or not data:
        return _error("missing_input", "QL payload data must be passed explicitly or extracted from a fresh saved QL seed.")
    if source_adapter in {"rpc_readback_envelope", "saved_entry"}:
        branch = str(entry.get("branch") or entry.get("source_branch") or "").strip().lower()
        if branch != "saved" or not _lifecycle_revision_token(entry):
            return _error("fresh_saved_readback_required", "QL seed must be saved branch with a fresh revision id.")
    elif source_adapter not in {"", "canonical_request_payload"}:
        return _error(
            "invalid_source_adapter",
            "QL payload source must be explicit canonical_request_payload or a fresh saved QL readback.",
        )
    return None


def _wizard_visualization_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("visualizationId", "visualization_id"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        chart_type = str(value.get("chart_type") or "").strip()
        if chart_type in {"map", "geo_layer", "symbol_map"}:
            return "geolayer"
        if is_supported_wizard_visualization(chart_type):
            return chart_type
        visualization = value.get("visualization")
        if isinstance(visualization, dict):
            token = str(visualization.get("id") or visualization.get("type") or "").strip()
            if token:
                return token
        for child in value.values():
            token = _wizard_visualization_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _wizard_visualization_token(child)
            if token:
                return token
    return ""


def _lifecycle_revision_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("revId", "revisionId", "revision_id", "versionId"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        for child in value.values():
            token = _lifecycle_revision_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _lifecycle_revision_token(child)
            if token:
                return token
    return ""


def _find_data_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if isinstance(value.get("data"), dict):
            return value["data"]
        for child in value.values():
            found = _find_data_payload(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_data_payload(child)
            if found is not None:
                return found
    return None


def _sanitize_approval_provenance(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: deepcopy(value[key])
        for key in ("selection_origin", "selection_reason", "request_digest", "decision_id", "approval_sources")
        if value.get(key) not in (None, "")
    }


def _dataset_guid_report(
    current_dataset: dict[str, Any],
    proposed_dataset: dict[str, Any],
    affected_chart_payloads: list[dict[str, Any]],
    *,
    allow_guid_changes: bool,
) -> dict[str, Any]:
    current_guid_by_name = _field_guid_map(current_dataset)
    proposed_guid_by_name = _field_guid_map(proposed_dataset)
    changed_field_guids = [
        {"field": name, "current_guid": current_guid, "proposed_guid": proposed_guid_by_name.get(name, "")}
        for name, current_guid in sorted(current_guid_by_name.items())
        if name in proposed_guid_by_name and proposed_guid_by_name[name] and proposed_guid_by_name[name] != current_guid
    ]
    missing_field_guids = [
        {"field": name, "current_guid": current_guid}
        for name, current_guid in sorted(current_guid_by_name.items())
        if name not in proposed_guid_by_name or not proposed_guid_by_name[name]
    ]

    proposed_guids = {guid for guid in proposed_guid_by_name.values() if guid}
    chart_references = _chart_guid_references(affected_chart_payloads, set(current_guid_by_name.values()))
    broken_chart_guid_references = [
        reference for reference in chart_references if reference["guid"] and reference["guid"] not in proposed_guids
    ]
    blocked_reasons: list[str] = []
    if (changed_field_guids or missing_field_guids) and not allow_guid_changes:
        blocked_reasons.append("dataset field GUIDs changed or disappeared while allow_guid_changes=false")
    if broken_chart_guid_references:
        blocked_reasons.append("affected chart payloads reference dataset field GUIDs missing from proposed_dataset")

    return {
        "current_field_guid_count": len([guid for guid in current_guid_by_name.values() if guid]),
        "proposed_field_guid_count": len([guid for guid in proposed_guid_by_name.values() if guid]),
        "changed_field_guids": changed_field_guids,
        "missing_field_guids": missing_field_guids,
        "affected_chart_guid_references": chart_references,
        "broken_chart_guid_references": broken_chart_guid_references,
        "allow_guid_changes": allow_guid_changes,
        "blocked_reasons": blocked_reasons,
    }


def _field_guid_map(dataset: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in _extract_fields(dataset):
        name = str(field.get("name") or field.get("title") or "").strip()
        guid = str(field.get("guid") or field.get("id") or field.get("fieldId") or "").strip()
        if name:
            result[name] = guid
    return result


def _chart_guid_references(payloads: list[dict[str, Any]], candidate_guids: set[str]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for index, payload in enumerate(payloads):
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for guid in sorted(candidate_guids):
            if guid and guid in text:
                chart_id = str(payload.get("chartId") or payload.get("id") or payload.get("entryId") or f"chart[{index}]")
                references.append({"chart_id": chart_id, "guid": guid})
    return references


def _dashboard_tabs(dashboard: dict[str, Any]) -> tuple[list[Any], str] | None:
    direct = dashboard.get("tabs")
    if isinstance(direct, list):
        return direct, "$.tabs"
    data = dashboard.get("data")
    if isinstance(data, dict) and isinstance(data.get("tabs"), list):
        return data["tabs"], "$.data.tabs"
    body = dashboard.get("body")
    if isinstance(body, dict) and isinstance(body.get("tabs"), list):
        return body["tabs"], "$.body.tabs"
    return None


def _extract_fields(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    fields = dataset.get("fields") or dataset.get("dataset", {}).get("fields") or []
    normalized: list[dict[str, Any]] = []
    for field in fields if isinstance(fields, list) else []:
        if isinstance(field, str):
            normalized.append({"name": field})
        elif isinstance(field, dict):
            name = field.get("name") or field.get("title") or field.get("guid") or field.get("id")
            if name:
                normalized.append({"name": str(name), **field})
    return normalized


def _dataset_calculated_field_report(dataset: dict[str, Any]) -> dict[str, Any]:
    fields = _extract_fields(dataset)
    known: dict[str, str] = {}
    for field in fields:
        name = str(field.get("name") or field.get("title") or "").strip()
        guid = str(field.get("guid") or field.get("id") or field.get("fieldId") or "").strip()
        if name:
            known[name.casefold()] = name
        if guid:
            known[guid.casefold()] = name or guid

    registry = load_formula_registry()
    issues: list[dict[str, Any]] = []
    dependencies: dict[str, list[str]] = {}
    checked = 0
    for index, field in enumerate(fields):
        formula_key = next((key for key in ("formula", "expression") if key in field), "")
        if not formula_key:
            continue
        checked += 1
        field_name = str(field.get("name") or field.get("title") or field.get("guid") or f"field[{index}]")
        expression = str(field.get(formula_key) or "").strip()
        if not expression:
            issues.append(
                {
                    "severity": "error",
                    "category": "missing_formula_expression",
                    "field": field_name,
                    "path": f"$.fields[{index}].{formula_key}",
                }
            )
            continue
        validation = validate_formula_expression(expression, registry=registry)
        for item in validation.get("issues") or []:
            issues.append(
                {
                    "severity": str(item.get("severity") or "error"),
                    "category": str(item.get("category") or "formula_validation"),
                    "field": field_name,
                    "path": f"$.fields[{index}].{formula_key}",
                    "details": item,
                }
            )
        refs = [str(item) for item in validation.get("field_refs") or [] if str(item)]
        dependencies[field_name] = refs
        for ref in refs:
            if ref.casefold() not in known:
                issues.append(
                    {
                        "severity": "error",
                        "category": "unknown_field_reference",
                        "field": field_name,
                        "reference": ref,
                        "path": f"$.fields[{index}].{formula_key}",
                    }
                )

    cycles = _calculated_field_cycles(dependencies)
    for cycle in cycles:
        issues.append(
            {
                "severity": "error",
                "category": "calculated_field_cycle",
                "field": cycle[0],
                "cycle": cycle,
                "path": "$.fields",
            }
        )
    return {
        "ok": not any(issue.get("severity") == "error" for issue in issues),
        "checked_field_count": checked,
        "known_field_count": len(fields),
        "dependencies": dependencies,
        "cycles": cycles,
        "issues": issues,
        "standalone_api_used": False,
        "validation_scope": "embedded_dataset_fields",
    }


def _calculated_field_cycles(dependencies: dict[str, list[str]]) -> list[list[str]]:
    canonical = {name.casefold(): name for name in dependencies}
    graph = {
        name.casefold(): [ref.casefold() for ref in refs if ref.casefold() in canonical]
        for name, refs in dependencies.items()
    }
    visiting: list[str] = []
    visited: set[str] = set()
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        if node in visiting:
            start = visiting.index(node)
            rendered = [canonical[item] for item in visiting[start:]] + [canonical[node]]
            if rendered not in cycles:
                cycles.append(rendered)
            return
        if node in visited:
            return
        visiting.append(node)
        for child in graph.get(node, []):
            visit(child)
        visiting.pop()
        visited.add(node)

    for node in graph:
        visit(node)
    return cycles


def _object_id_for_payload(object_type: str, payload: dict[str, Any]) -> str:
    if object_type == "dataset":
        return str(payload.get("datasetId") or payload.get("dataset_id") or payload.get("id") or "")
    if object_type == "connector":
        return str(payload.get("connectionId") or payload.get("connection_id") or payload.get("id") or "")
    return str(payload.get("entryId") or payload.get("chartId") or payload.get("dashboardId") or payload.get("id") or "")
