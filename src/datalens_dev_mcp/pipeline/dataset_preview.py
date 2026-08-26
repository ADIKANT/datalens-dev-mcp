from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import write_json


FILTER_OPERATIONS = {
    "in",
    "nin",
    "isnull",
    "isnotnull",
    "between",
    "eq",
    "ne",
    "gt",
    "lt",
    "gte",
    "lte",
    "istartswith",
    "startswith",
    "iendswith",
    "endswith",
    "icontains",
    "contains",
    "noticontains",
    "notcontains",
    "leneq",
    "lenne",
    "lengt",
    "lengte",
    "lenlt",
    "lenlte",
}
ZERO_VALUE_OPERATIONS = {"isnull", "isnotnull"}
TWO_VALUE_OPERATIONS = {"between"}


def compile_dataset_preview_request(
    *,
    dataset_id: str,
    columns: list[str],
    dataset_fields: list[dict[str, Any]],
    workbook_id: str = "",
    filters: list[dict[str, Any]] | None = None,
    params: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
    max_pages: int = 1,
    tie_breaker_fields: list[str] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    normalized_columns = _nonempty_unique(columns)
    if not str(dataset_id).strip():
        issues.append("dataset_id is required")
    if not normalized_columns:
        issues.append("columns must contain at least one dataset field GUID")
    if normalized_columns != list(columns):
        issues.append("columns must be non-empty unique GUID strings")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100_000:
        issues.append("limit must be an integer between 1 and 100000")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        issues.append("offset must be a non-negative integer")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 100:
        issues.append("max_pages must be an integer between 1 and 100")

    field_guids = {str(item.get("guid") or "") for item in dataset_fields if isinstance(item, dict)}
    unknown_columns = sorted(set(normalized_columns) - field_guids)
    if unknown_columns:
        issues.append("unknown dataset columns: " + ", ".join(unknown_columns))

    normalized_filters = list(filters or [])
    for index, item in enumerate(normalized_filters):
        if not isinstance(item, dict):
            issues.append(f"filters[{index}] must be an object")
            continue
        guid = str(item.get("guid") or "")
        operation = str(item.get("operation") or "")
        values = item.get("values")
        if guid not in field_guids:
            issues.append(f"filters[{index}].guid is not a dataset field")
        if operation not in FILTER_OPERATIONS:
            issues.append(f"filters[{index}].operation is unsupported: {operation or '<empty>'}")
            continue
        value_count = len(values) if isinstance(values, list) else 0
        if values is not None and not isinstance(values, list):
            issues.append(f"filters[{index}].values must be an array")
        elif operation in ZERO_VALUE_OPERATIONS and value_count != 0:
            issues.append(f"filters[{index}] operation {operation} requires zero values")
        elif operation in TWO_VALUE_OPERATIONS and value_count != 2:
            issues.append(f"filters[{index}] operation {operation} requires exactly two values")
        elif operation not in ZERO_VALUE_OPERATIONS | TWO_VALUE_OPERATIONS and value_count < 1:
            issues.append(f"filters[{index}] operation {operation} requires at least one value")

    normalized_sort = list(sort or [])
    sort_guids: list[str] = []
    for index, item in enumerate(normalized_sort):
        if not isinstance(item, dict):
            issues.append(f"sort[{index}] must be an object")
            continue
        guid = str(item.get("guid") or "")
        direction = str(item.get("direction") or "")
        sort_guids.append(guid)
        if guid not in normalized_columns:
            issues.append(f"sort[{index}].guid must also be present in columns")
        if direction not in {"asc", "desc"}:
            issues.append(f"sort[{index}].direction must be asc or desc")
    if len(sort_guids) != len(set(sort_guids)):
        issues.append("sort GUIDs must be unique")
    if offset > 0 and not normalized_sort:
        issues.append("offset greater than zero requires a non-empty sort")

    discovered_unique = sorted(
        str(item.get("guid"))
        for item in dataset_fields
        if isinstance(item, dict) and item.get("guid") and bool(item.get("unique") or item.get("isUnique"))
    )
    tie_breakers = _nonempty_unique(tie_breaker_fields or discovered_unique)
    if tie_breakers and not set(tie_breakers).issubset(set(sort_guids)):
        issues.append("tie_breaker_fields must be present in sort")
    if max_pages > 1 and not normalized_sort:
        issues.append("multi-page dataset preview requires a non-empty sort")
    if max_pages > 1 and not tie_breakers:
        issues.append("multi-page dataset preview requires a known unique tie-breaker field")

    payload: dict[str, Any] = {
        "datasetId": str(dataset_id),
        "columns": normalized_columns,
        "limit": limit,
        "offset": offset,
    }
    if workbook_id:
        payload["workbookId"] = workbook_id
    if normalized_filters:
        payload["filters"] = normalized_filters
    if params:
        payload["params"] = list(params)
    if normalized_sort:
        payload["sort"] = normalized_sort
    return {
        "ok": not issues,
        "status": "validated" if not issues else "blocked",
        "issues": issues,
        "payload": payload,
        "paging": {
            "max_pages": max_pages,
            "tie_breaker_fields": tie_breakers,
            "deterministic": bool(normalized_sort and tie_breakers),
        },
        "experimental": True,
    }


def preview_dataset_data(
    *,
    dataset_id: str,
    columns: list[str],
    workbook_id: str = "",
    filters: list[dict[str, Any]] | None = None,
    params: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
    max_pages: int = 1,
    tie_breaker_fields: list[str] | None = None,
    inline_row_limit: int = 20,
    inline_byte_budget: int = 8_000,
    project_root: str | Path = ".",
    artifact_name: str = "dataset-preview",
    client: Any | None = None,
    dataset_readback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if client is None:
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        client = DataLensApiClient(DataLensConfig.from_env())
    readback = dataset_readback or client.rpc_readonly(
        "getDataset",
        {"datasetId": dataset_id, "branch": "saved"},
    )
    fields = extract_dataset_fields(readback)
    compiled = compile_dataset_preview_request(
        dataset_id=dataset_id,
        workbook_id=workbook_id,
        columns=columns,
        dataset_fields=fields,
        filters=filters,
        params=params,
        sort=sort,
        limit=limit,
        offset=offset,
        max_pages=max_pages,
        tie_breaker_fields=tie_breaker_fields,
    )
    if not compiled["ok"]:
        question = None
        if max_pages > 1 and any("tie-breaker" in issue for issue in compiled["issues"]):
            question = (
                "Какое поле или набор полей образует уникальный ключ датасета для стабильной пагинации? "
                "Это нельзя доказать по текущей схеме readback."
            )
        return {
            **compiled,
            "schema_id": "dataset_preview_result",
            "question": question,
            "dataset_field_count": len(fields),
        }

    all_rows: list[dict[str, Any]] = []
    response_schema: list[dict[str, Any]] = []
    page_receipts: list[dict[str, Any]] = []
    next_offset = int(offset)
    for page_number in range(1, max_pages + 1):
        payload = dict(compiled["payload"])
        payload["offset"] = next_offset
        response = client.rpc_readonly("getDatasetData", payload)
        page_schema = response.get("schema") if isinstance(response, dict) else None
        page_rows = response.get("rows") if isinstance(response, dict) else None
        if not isinstance(page_schema, list) or not isinstance(page_rows, list):
            return _runtime_error("getDatasetData response must contain schema and rows arrays", compiled)
        if not response_schema:
            response_schema = [dict(item) for item in page_schema if isinstance(item, dict)]
        elif page_schema != response_schema:
            return _runtime_error("getDatasetData schema changed between pages", compiled)
        try:
            typed_rows = rows_to_typed_dicts(response_schema, page_rows)
        except ValueError as exc:
            return _runtime_error(str(exc), compiled)
        all_rows.extend(typed_rows)
        page_receipts.append({"page": page_number, "offset": next_offset, "row_count": len(typed_rows)})
        if len(page_rows) < limit:
            break
        next_offset += limit

    artifact_payload = {
        "schema_id": "dataset_preview_artifact",
        "experimental": True,
        "request": compiled["payload"],
        "paging": compiled["paging"],
        "schema": response_schema,
        "rows": all_rows,
        "page_receipts": page_receipts,
    }
    safe_name = _safe_artifact_name(artifact_name)
    dataset_fingerprint = hashlib.sha256(dataset_id.encode("utf-8")).hexdigest()[:12]
    artifact_path = Path(project_root) / "artifacts" / "data_evidence" / f"{safe_name}-{dataset_fingerprint}.json"
    write_json(artifact_path, artifact_payload)
    inline_rows = _bounded_inline_rows(all_rows, max(0, inline_row_limit), max(800, inline_byte_budget))
    return {
        "ok": True,
        "status": "completed",
        "schema_id": "dataset_preview_result",
        "experimental": True,
        "dataset_field_count": len(fields),
        "schema": response_schema,
        "row_count": len(all_rows),
        "rows": inline_rows,
        "truncated": len(inline_rows) < len(all_rows),
        "page_receipts": page_receipts,
        "paging": compiled["paging"],
        "artifact_path": str(artifact_path),
    }


def extract_dataset_fields(value: Any) -> list[dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            guid = str(item.get("guid") or "").strip()
            name = str(item.get("name") or item.get("title") or "").strip()
            field_type = str(item.get("type") or item.get("dataType") or "").strip()
            if guid and (name or field_type):
                fields.setdefault(
                    guid,
                    {
                        "guid": guid,
                        "name": name or guid,
                        "type": field_type or "unsupported",
                        "unique": bool(item.get("unique") or item.get("isUnique")),
                    },
                )
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return [fields[key] for key in sorted(fields)]


def rows_to_typed_dicts(schema: list[dict[str, Any]], rows: list[Any]) -> list[dict[str, Any]]:
    guids = [str(item.get("guid") or "") for item in schema]
    if not guids or any(not guid for guid in guids) or len(set(guids)) != len(guids):
        raise ValueError("getDatasetData schema GUIDs must be non-empty and unique")
    result: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(schema):
            raise ValueError(f"rows[{row_index}] length does not match schema")
        result.append(
            {
                guids[index]: _typed_value(value, str(schema[index].get("type") or ""))
                for index, value in enumerate(row)
            }
        )
    return result


def _typed_value(value: Any, field_type: str) -> Any:
    if value is None:
        return None
    try:
        if field_type in {"integer", "uinteger"} and not isinstance(value, bool):
            return int(value)
        if field_type == "float" and not isinstance(value, bool):
            return float(value)
        if field_type == "boolean" and isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1"}:
                return True
            if normalized in {"false", "0"}:
                return False
    except (TypeError, ValueError):
        return value
    return value


def _bounded_inline_rows(rows: list[dict[str, Any]], row_limit: int, byte_budget: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows[:row_limit]:
        candidate = result + [row]
        if len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > byte_budget:
            break
        result.append(row)
    return result


def _nonempty_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _safe_artifact_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value))
    return normalized.strip("-")[:80] or "dataset-preview"


def _runtime_error(message: str, compiled: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "provider_failure",
        "schema_id": "dataset_preview_result",
        "experimental": True,
        "error": {"category": "dataset_preview_response_invalid", "message": message},
        "paging": compiled.get("paging") or {},
    }
