from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from datalens_dev_mcp.pipeline.dataset_data_contract import DATASET_DATA_API_CONTRACT_HASH
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

COMPLEX_RAW_TYPES = frozenset(
    {"geopoint", "geopolygon", "hierarchy", "tree_str", "tree_int", "tree_float", "markup", "heatmap", "unsupported"}
)


def normalize_dataset_data_response(
    response: dict[str, Any],
    *,
    request_hash: str,
    observed_at: str,
    expected_schema: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    schema = response.get("schema") if isinstance(response, dict) else None
    rows = response.get("rows") if isinstance(response, dict) else None
    if not isinstance(schema, list) or not isinstance(rows, list):
        raise TypeError("getDatasetData response must contain schema and rows arrays")
    normalized_schema = [dict(item) for item in schema if isinstance(item, dict)]
    guids = [str(item.get("guid") or "") for item in normalized_schema]
    if len(normalized_schema) != len(schema) or not guids or any(not item for item in guids) or len(set(guids)) != len(guids):
        raise ValueError("getDatasetData schema GUIDs must be non-empty and unique")
    if expected_schema is not None and normalized_schema != expected_schema:
        raise ValueError("getDatasetData schema changed between pages")
    typed_rows: list[dict[str, dict[str, Any]]] = []
    plain_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(normalized_schema):
            raise ValueError(f"rows[{row_index}] length does not match schema")
        typed: dict[str, dict[str, Any]] = {}
        plain: dict[str, Any] = {}
        for index, value in enumerate(row):
            guid = guids[index]
            representation = normalize_dataset_value(value, str(normalized_schema[index].get("type") or "unsupported"))
            typed[guid] = representation
            plain[guid] = representation["normalized"] if representation["parse_status"] == "parsed" else representation["raw"]
        typed_rows.append(typed)
        plain_rows.append(plain)
    schema_hash = canonical_hash(normalized_schema)
    return {
        "schema_id": "normalized_dataset_data_page",
        "request_hash": request_hash,
        "schema_hash": schema_hash,
        "observed_at": observed_at,
        "api_contract_hash": DATASET_DATA_API_CONTRACT_HASH,
        "schema": normalized_schema,
        "typed_rows": typed_rows,
        "plain_rows": plain_rows,
        "row_count": len(plain_rows),
    }


def normalize_dataset_value(value: Any, declared_type: str) -> dict[str, Any]:
    field_type = str(declared_type or "unsupported").lower()
    if value is None:
        return _value(value, None, field_type, "null")
    if field_type in COMPLEX_RAW_TYPES:
        return _value(value, None, field_type, "unsupported" if field_type == "unsupported" else "raw_preserved")
    try:
        if field_type in {"integer", "uinteger"} and not isinstance(value, bool):
            normalized = int(value)
            if field_type == "uinteger" and normalized < 0:
                return _value(value, None, field_type, "invalid")
            return _value(value, normalized, field_type, "parsed")
        if field_type == "float" and not isinstance(value, bool):
            normalized = float(value)
            return _value(value, normalized, field_type, "parsed" if math.isfinite(normalized) else "invalid")
        if field_type == "boolean":
            if isinstance(value, bool):
                return _value(value, value, field_type, "parsed")
            if isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0"}:
                return _value(value, value.strip().lower() in {"true", "1"}, field_type, "parsed")
            return _value(value, None, field_type, "invalid")
        if field_type == "date":
            normalized = date.fromisoformat(str(value)[:10]).isoformat()
            return _value(value, normalized, field_type, "parsed")
        if field_type in {"genericdatetime", "datetimetz"}:
            text = str(value).replace("Z", "+00:00")
            normalized = datetime.fromisoformat(text).isoformat()
            return _value(value, normalized, field_type, "parsed")
        if field_type in {"array_int", "array_float", "array_str"}:
            if not isinstance(value, list):
                return _value(value, None, field_type, "raw_preserved")
            converter = int if field_type == "array_int" else float if field_type == "array_float" else str
            if any(isinstance(item, (dict, list)) for item in value):
                return _value(value, None, field_type, "raw_preserved")
            return _value(value, [converter(item) for item in value], field_type, "parsed")
        if field_type == "string":
            return _value(value, str(value), field_type, "parsed")
    except (TypeError, ValueError, OverflowError):
        return _value(value, None, field_type, "invalid")
    return _value(value, None, field_type, "raw_preserved")


def _value(raw: Any, normalized: Any, declared_type: str, parse_status: str) -> dict[str, Any]:
    return {
        "raw": raw,
        "normalized": normalized,
        "declared_type": declared_type,
        "parse_status": parse_status,
    }
