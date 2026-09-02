from __future__ import annotations

from copy import deepcopy
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


DELETE_ROUTES = {
    "wizard_chart": ("deleteWizardChart", "getWizardChart", "chartId"),
    "editor_chart": ("deleteEditorChart", "getEditorChart", "chartId"),
    "editor_table": ("deleteEditorChart", "getEditorChart", "chartId"),
    "editor_markdown": ("deleteHtmlPage", "getHtmlPage", "entryId"),
    "html_page": ("deleteHtmlPage", "getHtmlPage", "entryId"),
    "dashboard": ("deleteDashboard", "getDashboard", "dashboardId"),
    "dataset": ("deleteDataset", "getDataset", "datasetId"),
}


def execute_run_owned_cleanup(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    ownership = read_json(journal.root / "inputs" / "cleanup-ownership.json", {}) or {}
    cleanup_plan = read_json(journal.root / "plans" / "run-owned-cleanup-plan.json", {}) or {}
    _validate_cleanup_inputs(journal, contract, ownership, cleanup_plan)
    if client is None:
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        client = DataLensApiClient(DataLensConfig.from_env())

    results: list[dict[str, Any]] = []
    objects = [dict(item) for item in ownership.get("objects") or [] if isinstance(item, dict)]
    for item in reversed(objects):
        object_type = str(item.get("object_type") or "")
        object_id = str(item.get("object_id") or "")
        workbook_id = str(item.get("workbook_id") or "")
        route = DELETE_ROUTES.get(object_type)
        if route is None:
            raise ValueError(f"run-owned cleanup does not support object type {object_type}")
        delete_method, read_method, id_key = route
        read_payload = {id_key: object_id}
        if read_method in {"getWizardChart", "getEditorChart", "getHtmlPage", "getDashboard"}:
            read_payload["branch"] = "saved"
        elif workbook_id:
            read_payload["workbookId"] = workbook_id
        before = client.rpc_readonly(read_method, read_payload, exclusive=True)
        observed_workbook = _deep_first(before, {"workbookId", "workbook_id"})
        if observed_workbook and str(observed_workbook) != workbook_id:
            raise ValueError("run-owned cleanup live workbook does not match ownership proof")
        client.rpc(delete_method, {id_key: object_id}, exclusive=True)
        absent = False
        try:
            client.rpc_readonly(read_method, read_payload, exclusive=True)
        except DataLensApiError as exc:
            absent = exc.http_status == 404 or exc.failure_family == "NOT_FOUND_404"
            if not absent:
                raise
        if not absent:
            raise ValueError("run-owned cleanup readback still finds the deleted object")
        results.append(
            {
                "object_id": object_id,
                "object_type": object_type,
                "delete_method": delete_method,
                "read_method": read_method,
                "verified_absent": True,
            }
        )
    receipt = {
        "schema_id": "datalens_run_owned_cleanup_receipt",
        "task_id": journal.task_id,
        "contract_hash": str(contract.get("contract_hash") or ""),
        "ownership_hash": str(ownership.get("ownership_hash") or ""),
        "cleanup_plan_hash": str(cleanup_plan.get("plan_hash") or ""),
        "object_count": len(results),
        "objects": results,
        "all_verified_absent": all(item.get("verified_absent") for item in results),
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    write_json(journal.delivery_root / "run-owned-cleanup-receipt.json", receipt)
    return deepcopy(receipt)


def _validate_cleanup_inputs(
    journal: ProjectJournal,
    contract: dict[str, Any],
    ownership: dict[str, Any],
    cleanup_plan: dict[str, Any],
) -> None:
    if str(contract.get("task_kind") or "") != "cleanup_run_owned_objects":
        raise ValueError("run-owned cleanup requires the typed cleanup task kind")
    ownership_material = dict(ownership)
    ownership_hash = str(ownership_material.pop("ownership_hash", ""))
    if not ownership_hash or ownership_hash != canonical_hash(ownership_material):
        raise ValueError("run-owned cleanup ownership hash mismatch")
    plan_material = dict(cleanup_plan)
    plan_hash = str(plan_material.pop("plan_hash", ""))
    if not plan_hash or plan_hash != canonical_hash(plan_material):
        raise ValueError("run-owned cleanup plan hash mismatch")
    if cleanup_plan.get("ownership_hash") != ownership_hash:
        raise ValueError("run-owned cleanup plan is not bound to ownership")
    objects = [item for item in ownership.get("objects") or [] if isinstance(item, dict)]
    if not objects:
        raise ValueError("run-owned cleanup has no exact objects")
    for item in objects:
        if (
            str(item.get("created_by_task_id") or "") != str(ownership.get("task_id") or "")
            or str(item.get("cleanup_route") or "") != "direct_object_delete"
            or not str(item.get("run_id") or "")
            or not str(item.get("creation_receipt") or "")
            or str(item.get("object_type") or "") not in DELETE_ROUTES
        ):
            raise ValueError("run-owned cleanup object lacks exact ownership or a supported direct route")


def _deep_first(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and item is not None and item != "":
                return item
            found = _deep_first(item, keys)
            if found is not None and found != "":
                return found
    elif isinstance(value, list):
        for item in value:
            found = _deep_first(item, keys)
            if found is not None and found != "":
                return found
    return None
