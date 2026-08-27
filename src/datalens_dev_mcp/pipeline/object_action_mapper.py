from __future__ import annotations

from typing import Any

from datalens_dev_mcp.api.request_compiler import project_method_request
from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract

ACTION_ROUTES = {
    "dashboard": ("getDashboard", "updateDashboard", "dashboardId", "update_dashboard"),
    "chart": ("getEditorChart", "updateEditorChart", "chartId", "update_editor_chart"),
    "editor_chart": ("getEditorChart", "updateEditorChart", "chartId", "update_editor_chart"),
    "editor_table": ("getEditorChart", "updateEditorChart", "chartId", "update_editor_chart"),
    "control": ("getEditorChart", "updateEditorChart", "chartId", "update_editor_chart"),
    "markdown": ("getEditorChart", "updateEditorChart", "chartId", "update_editor_chart"),
    "wizard_chart": ("getWizardChart", "updateWizardChart", "chartId", "update_wizard_chart"),
    "ql_chart": ("getQLChart", "updateQLChart", "chartId", "update_ql_chart"),
}

SEMANTIC_READ_ROUTES = {
    "dashboard": ("getDashboard", "dashboardId", True),
    "chart": ("getEditorChart", "chartId", True),
    "editor_chart": ("getEditorChart", "chartId", True),
    "editor_table": ("getEditorChart", "chartId", True),
    "control": ("getEditorChart", "chartId", True),
    "markdown": ("getEditorChart", "chartId", True),
    "wizard_chart": ("getWizardChart", "chartId", True),
    "ql_chart": ("getQLChart", "chartId", True),
    "dataset": ("getDataset", "datasetId", False),
    "connection": ("getConnection", "connectionId", False),
}


def semantic_fresh_read_spec(
    *,
    object_id: str,
    object_type: str,
    workbook_id: str,
) -> dict[str, Any]:
    route = SEMANTIC_READ_ROUTES.get(str(object_type or ""))
    if route is None:
        raise ValueError(f"unsupported object type for semantic fresh read: {object_type}")
    method, id_key, branch_aware = route
    payload = {id_key: object_id}
    if branch_aware:
        payload["branch"] = "saved"
    elif workbook_id:
        payload["workbookId"] = workbook_id
    return {"method": method, "payload": payload, "object_type": object_type}


def map_materialized_action(
    *,
    object_id: str,
    object_type: str,
    workbook_id: str,
    saved_revision: str,
    materialized_payload: dict[str, Any],
    baseline_payload: dict[str, Any] | None = None,
    semantic_patch_plan: dict[str, Any],
) -> dict[str, Any]:
    route = ACTION_ROUTES.get(str(object_type or ""))
    if route is None:
        raise ValueError(f"unsupported object type for semantic action mapping: {object_type}")
    read_method, write_method, id_key, action_name = route
    projected = project_method_request(
        write_method,
        materialized_payload,
        object_type=object_type,
        operation="update",
        object_id=object_id,
        workbook_id=workbook_id,
        mode="save",
    )
    if not projected.get("ok"):
        raise ValueError("materialized payload does not match write API: " + "; ".join(projected.get("issues") or []))
    action = {
        "action": action_name,
        "action_type": "update",
        "object_id": object_id,
        "object_type": object_type,
        "method": write_method,
        "mode": "save",
        "payload": projected["payload"],
        "fresh_read_method": read_method,
        "fresh_read_payload": {id_key: object_id, "branch": "saved"},
        "readback_method": read_method,
        "readback_payload": {id_key: object_id, "branch": "saved"},
        "readback_mode": "full",
        "requires_fresh_read": True,
        "preserve_unknown_fields": True,
        "expected_revision": saved_revision,
        "semantic_patch_plan": semantic_patch_plan,
        "semantic_expected_payloads": {object_id: materialized_payload},
        "changed": True,
    }
    if object_type == "dashboard":
        if not isinstance(baseline_payload, dict) or not baseline_payload:
            raise ValueError("dashboard semantic action requires a fresh saved baseline")
        action["current_dashboard"] = baseline_payload
        action["baseline_dashboard"] = baseline_payload
        action["baseline_diff_contract"] = build_baseline_diff_contract(
            dashboard_id=object_id,
            workbook_id=workbook_id,
            baseline_source={"kind": "live_saved_readback", "path": f"datalens://dashboard/{object_id}?branch=saved"},
            baseline_dashboard=baseline_payload,
            proposed_dashboard=projected["payload"],
            changed_objects=[],
        )
    return action
