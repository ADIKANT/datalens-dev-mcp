from __future__ import annotations

from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.reconciliation import reconcile_partial_creates


def dl_reconcile_partial_creates(
    workbook_id: str,
    planned_objects: list[dict[str, Any]],
    entries_payload: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    if not workbook_id:
        return {"ok": False, "error": {"category": "missing_input", "message": "workbook_id is required"}}
    if not planned_objects:
        return {"ok": False, "error": {"category": "missing_input", "message": "planned_objects is required"}}
    payload = entries_payload
    if payload is None:
        active_client = client or DataLensApiClient(DataLensConfig.from_env())
        payload = active_client.rpc("getWorkbookEntries", {"workbookId": workbook_id})
    return reconcile_partial_creates(workbook_id=workbook_id, planned_objects=planned_objects, entries_payload=payload)
