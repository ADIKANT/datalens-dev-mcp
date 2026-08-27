from __future__ import annotations

from typing import Any

from datalens_dev_mcp.api.request_compiler import project_method_request

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


def map_materialized_action(
    *,
    object_id: str,
    object_type: str,
    workbook_id: str,
    saved_revision: str,
    materialized_payload: dict[str, Any],
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
    return {
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
