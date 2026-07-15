from __future__ import annotations

from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.response_projection import (
    DEFAULT_INLINE_CHAR_BUDGET,
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
    workbook_id: str,
    scope: str | None = None,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str = ".",
    run_id: str = "",
) -> dict[str, Any]:
    payload = {"workbookId": workbook_id}
    if scope:
        payload["scope"] = scope
    response = call_read("getWorkbookEntries", payload)
    return project_workbook_entries_response(
        response,
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


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
