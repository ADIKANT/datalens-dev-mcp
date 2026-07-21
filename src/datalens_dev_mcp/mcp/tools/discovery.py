from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.concurrency import bounded_read_map, configured_read_workers
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.response_projection import (
    DEFAULT_INLINE_CHAR_BUDGET,
    normalize_response_mode,
    project_dashboard_response,
    project_connection_response,
    project_dataset_response,
    project_editor_chart_response,
    project_wizard_chart_response,
    project_workbook_entries_response,
)


def _client() -> DataLensApiClient:
    return DataLensApiClient(DataLensConfig.from_env())


def call_read(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _client().rpc_readonly(method, payload or {})


def dl_list_workbooks(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    return call_read("getWorkbooksList", {"page": page, "pageSize": page_size})


def dl_get_workbook_entries(
    workbook_id: str = "",
    workbook_ids: list[str] | None = None,
    scope: str | list[str] | None = None,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
    client: Any | None = None,
) -> dict[str, Any]:
    normalized_ids = _workbook_ids(workbook_id=workbook_id, workbook_ids=workbook_ids)
    normalized_scope = _normalized_workbook_scope(scope)
    normalized_response_mode = normalize_response_mode(response_mode)
    active_client = client or _client()
    if len(normalized_ids) == 1 and not workbook_ids:
        payload: dict[str, Any] = {"workbookId": normalized_ids[0]}
        if normalized_scope is not None:
            payload["scope"] = normalized_scope
        response = active_client.rpc_readonly("getWorkbookEntries", payload)
        return project_workbook_entries_response(
            response,
            response_mode=normalized_response_mode,
            inline_char_budget=inline_char_budget,
            project_root=project_root,
            run_id=run_id,
        )

    def read_one(item: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"workbookId": item}
        if normalized_scope is not None:
            payload["scope"] = normalized_scope
        try:
            return {"ok": True, "workbook_id": item, "response": active_client.rpc_readonly("getWorkbookEntries", payload)}
        except Exception as exc:  # noqa: BLE001 - batch reports item-level read failures.
            return {
                "ok": False,
                "workbook_id": item,
                "error": _batch_item_error(exc),
            }

    raw_items = bounded_read_map(
        normalized_ids,
        read_one,
        max_workers=configured_read_workers(active_client),
    )
    items: list[dict[str, Any]] = []
    for result in raw_items:
        if not result["ok"]:
            items.append(result)
            continue
        projected = project_workbook_entries_response(
            result["response"],
            response_mode="artifact",
            inline_char_budget=inline_char_budget,
            project_root=project_root,
            run_id=f"{run_id or 'workbook_entries_batch'}_{result['workbook_id']}",
        )
        items.append(
            {
                "ok": True,
                "workbook_id": result["workbook_id"],
                "summary": projected.get("summary") or {},
                "artifact": projected.get("artifact") or {},
                "full_response": projected.get("full_response") or {},
            }
        )
    succeeded = sum(1 for item in items if item.get("ok"))
    status = "completed" if succeeded == len(items) else "failed" if succeeded == 0 else "partial"
    return {
        "ok": succeeded == len(items),
        "status": status,
        "batch": True,
        "requested_response_mode": normalized_response_mode,
        "workbook_count": len(items),
        "succeeded": succeeded,
        "failed": len(items) - succeeded,
        "items": items,
    }


def _workbook_ids(*, workbook_id: str, workbook_ids: list[str] | None) -> list[str]:
    singular = str(workbook_id or "").strip()
    plural = [str(item or "").strip() for item in (workbook_ids or [])]
    if singular and plural:
        raise ValueError("exactly one of workbook_id or workbook_ids must be provided")
    values = [singular] if singular else plural
    if not values or any(not item for item in values):
        raise ValueError("exactly one of workbook_id or workbook_ids must be provided")
    if len(values) > 100:
        raise ValueError("workbook_ids supports at most 100 ids")
    if len(set(values)) != len(values):
        raise ValueError("workbook_ids must not contain duplicates")
    return values


def _normalized_workbook_scope(scope: str | list[str] | None) -> str | list[str] | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        normalized = scope.strip()
        if normalized.lower() in {"all", "*"}:
            return None
        if not normalized:
            raise ValueError("scope must be a non-empty string or list of non-empty strings")
        return normalized
    if not isinstance(scope, list) or not scope:
        raise ValueError("scope must be a non-empty string or list of non-empty strings")
    normalized_items = [str(item or "").strip() for item in scope]
    if any(not item for item in normalized_items):
        raise ValueError("scope list must contain only non-empty strings")
    if any(item.lower() in {"all", "*"} for item in normalized_items):
        if len(normalized_items) == 1:
            return None
        raise ValueError("scope all/* cannot be combined with specific scopes")
    if len(set(normalized_items)) != len(normalized_items):
        raise ValueError("scope list must not contain duplicates")
    return normalized_items


def _safe_batch_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    for marker in ("Authorization", "DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "Bearer ", "token", "iam"):
        text = text.replace(marker, "<redacted>")
    return text[:400]


def _batch_item_error(exc: Exception) -> dict[str, Any]:
    message = _safe_batch_error(exc)
    match = re.search(r"\bHTTP\s+(\d{3})\b", message, re.IGNORECASE)
    status = int(match.group(1)) if match else None
    error = {
        "category": "workbook_not_found" if status == 404 else "workbook_entries_read_failed",
        "message": message,
        "retryable": status in {429, 502, 503, 504},
    }
    if status is not None:
        error["http_status"] = status
    return error


def dl_get_dashboard(
    dashboard_id: str,
    branch: str = "saved",
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
) -> dict[str, Any]:
    response = call_read("getDashboard", {"dashboardId": dashboard_id, "branch": branch})
    return project_dashboard_response(
        response,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def dl_get_editor_chart(
    chart_id: str,
    branch: str = "saved",
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
) -> dict[str, Any]:
    response = call_read("getEditorChart", {"chartId": chart_id, "branch": branch})
    return project_editor_chart_response(
        response,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def dl_get_wizard_chart(
    chart_id: str,
    branch: str = "saved",
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
) -> dict[str, Any]:
    response = call_read("getWizardChart", {"chartId": chart_id, "branch": branch})
    return project_wizard_chart_response(
        response,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def dl_get_dataset(
    dataset_id: str,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
) -> dict[str, Any]:
    response = call_read("getDataset", {"datasetId": dataset_id})
    return project_dataset_response(
        response,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def dl_get_connection(
    connection_id: str,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
) -> dict[str, Any]:
    response = call_read("getConnection", {"connectionId": connection_id})
    return project_connection_response(
        response,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def dl_get_entries_relations(entry_ids: list[str]) -> dict[str, Any]:
    return call_read("getEntriesRelations", {"entryIds": entry_ids})
