from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, Protocol

from datalens_dev_mcp.dataset.contracts import TECHNICAL_MEASURES, validate_dataset_fields


class PreviewApi(Protocol):
    def read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def compile_preview_request(
    *,
    dataset_id: str,
    fields: list[dict[str, Any]],
    columns: list[str],
    filters: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    params: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
    max_pages: int = 1,
    tie_breaker_guids: list[str] | None = None,
) -> dict[str, Any]:
    field_report = validate_dataset_fields(fields)
    known = {str(field["guid"]) for field in field_report["fields"]}
    issues = list(field_report["issues"])
    normalized_columns = list(dict.fromkeys(str(value).strip() for value in columns if str(value).strip() in known))
    unknown_columns = [str(value) for value in columns if str(value) not in known]
    if unknown_columns:
        issues.append(
            {
                "code": "unknown_dataset_guid",
                "path": "columns",
                "message": "columns must contain exact Dataset field GUIDs: " + ", ".join(unknown_columns),
            }
        )
    if not normalized_columns:
        issues.append(
            {"code": "columns_empty", "path": "columns", "message": "at least one Dataset field GUID is required"}
        )
    normalized_filters: list[dict[str, Any]] = []
    for index, item in enumerate(filters or []):
        guid = str(item.get("guid") or "").strip()
        if guid.lower() in TECHNICAL_MEASURES:
            issues.append(
                {
                    "code": "technical_measure_filter_forbidden",
                    "path": f"filters[{index}].guid",
                    "message": "Measure Names and Measure Values cannot filter a chart",
                }
            )
        elif guid not in known:
            issues.append(
                {
                    "code": "unknown_filter_guid",
                    "path": f"filters[{index}].guid",
                    "message": "filter GUID is not in Dataset readback",
                }
            )
        else:
            normalized_filters.append(dict(item))
    normalized_sort = [dict(item) for item in sort or []]
    sort_guids = [str(item.get("guid") or "") for item in normalized_sort]
    for index, item in enumerate(normalized_sort):
        guid = str(item.get("guid") or "")
        if guid not in normalized_columns:
            issues.append(
                {
                    "code": "sort_guid_not_selected",
                    "path": f"sort[{index}].guid",
                    "message": "sort GUID must also be selected in columns",
                }
            )
        if item.get("direction") not in {"asc", "desc"}:
            issues.append(
                {
                    "code": "sort_direction_invalid",
                    "path": f"sort[{index}].direction",
                    "message": "sort direction must be asc or desc",
                }
            )
    tie_breakers = list(dict.fromkeys(tie_breaker_guids or []))
    if max_pages > 1 and (not normalized_sort or not tie_breakers):
        issues.append(
            {
                "code": "multipage_sort_not_deterministic",
                "path": "sort",
                "message": "multi-page preview requires sort and an explicit unique tie-breaker GUID",
            }
        )
    if not set(tie_breakers).issubset(set(sort_guids)):
        issues.append(
            {
                "code": "tie_breaker_not_sorted",
                "path": "tie_breaker_guids",
                "message": "every tie-breaker GUID must be present in sort",
            }
        )
    if not 1 <= limit <= 100_000 or offset < 0 or not 1 <= max_pages <= 100:
        issues.append(
            {
                "code": "preview_bound_invalid",
                "path": "limit",
                "message": "limit, offset or max_pages is outside the supported bound",
            }
        )
    request = {"datasetId": dataset_id, "columns": normalized_columns, "limit": limit, "offset": offset}
    if normalized_filters:
        request["filters"] = normalized_filters
    if normalized_sort:
        request["sort"] = normalized_sort
    if params:
        request["params"] = deepcopy(params)
    return {
        "ok": not issues,
        "issues": issues,
        "request": request,
        "max_pages": max_pages,
        "deterministic": bool(normalized_sort and tie_breakers),
    }


class DatasetPreviewService:
    def __init__(self, api: PreviewApi, *, dataset_query: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.api = api
        self.dataset_query = dataset_query

    def preview(self, **kwargs: Any) -> dict[str, Any]:
        compiled = compile_preview_request(**kwargs)
        if not compiled["ok"]:
            return compiled
        request = dict(compiled["request"])
        rows: list[Any] = []
        pages = 0
        for page_index in range(int(compiled["max_pages"])):
            request["offset"] = int(compiled["request"]["offset"]) + page_index * int(request["limit"])
            raw = self.dataset_query(request) if self.dataset_query is not None else self.api.read("getDatasetData", request)
            page_rows = _rows(raw, columns=request["columns"])
            if len(page_rows) > int(request["limit"]) or any(
                not isinstance(row, list) or len(row) != len(request["columns"]) for row in page_rows
            ):
                raise ValueError("getDatasetData response exceeds the requested rows/columns bound")
            rows.extend(page_rows)
            pages += 1
            if len(page_rows) < int(request["limit"]):
                break
        return {
            "ok": True,
            "columns": list(request["columns"]),
            "rows": rows,
            "page_count": pages,
            "complete": pages < int(compiled["max_pages"]) or (not rows) or len(page_rows) < int(request["limit"]),
            "evidence": "dataset_query_only",
        }


def _rows(raw: Mapping[str, Any], *, columns: list[str]) -> list[Any]:
    value: Any = raw
    while isinstance(value, Mapping) and isinstance(value.get("result"), Mapping):
        value = value["result"]
    if isinstance(value, Mapping) and isinstance(value.get("data"), Mapping):
        value = value["data"]
    rows = value.get("rows") if isinstance(value, Mapping) else None
    if not isinstance(rows, list):
        raise TypeError("getDatasetData response must contain a rows array; malformed is not empty")
    schema = value.get("schema")
    if not isinstance(schema, list) or any(not isinstance(column, Mapping) for column in schema):
        raise TypeError("getDatasetData response must contain a column schema")
    if [column.get("guid") for column in schema] != columns:
        raise ValueError("getDatasetData response schema must match requested column GUIDs and order")
    return list(rows)
