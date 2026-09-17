from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, InputContractError, safe_diagnostic_id

TECHNICAL_MEASURES = frozenset({"measure names", "measure values"})
_LOD_RE = re.compile(r"\b(FIXED|INCLUDE|EXCLUDE)\b", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(AGO|AT_DATE)\s*\(", re.IGNORECASE)
_AGG_RE = re.compile(r"\b(SUM|AVG|MIN|MAX|COUNT|COUNTD|COUNTUNIQUE)\s*\(", re.IGNORECASE)


def dataset_validation_summary(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Provider metadata only; never echo component messages, SQL or data."""
    sources, fields = dataset.get("sources"), dataset.get("result_schema")
    errors = dataset.get("component_errors")
    items = errors.get("items") if isinstance(errors, Mapping) else None
    if not isinstance(sources, list) or not isinstance(fields, list) or not isinstance(items, list):
        return {"status": "unverified", "evidence": "provider_metadata_only"}
    codes = set()
    count = 0
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("errors"), list):
            return {"status": "unverified", "evidence": "provider_metadata_only"}
        for error in item["errors"]:
            count += 1
            code = safe_diagnostic_id(error.get("code")) if isinstance(error, Mapping) else None
            if code:
                codes.add(code)
    invalid_sources = sum(isinstance(source, Mapping) and source.get("valid") is False for source in sources)
    invalid_fields = sum(isinstance(field, Mapping) and field.get("valid") is False for field in fields)
    valid_flags = bool(sources and fields) and all(
        isinstance(item, Mapping) and item.get("valid") is True for item in [*sources, *fields]
    )
    status = "invalid" if count or invalid_sources or invalid_fields else "valid" if valid_flags else "unverified"
    return {"status": status, "error_count": count, "error_codes": sorted(codes)[:20],
            "invalid_source_count": invalid_sources, "invalid_field_count": invalid_fields,
            "evidence": "provider_metadata_only"}


def validate_provider_dataset(api: Any, readback: dict[str, Any], *, refresh_source_ids: list[str] | None = None,
                              include_state: bool = False) -> dict[str, Any]:
    """Validate current saved state and optionally refresh exact source schemas without saving."""
    identity, snapshot = readback["identity"], readback["object"]
    dataset = snapshot.get("dataset")
    if not isinstance(dataset, dict) or not isinstance(dataset.get("sources"), list):
        raise InputContractError("Provider validation requires a full Dataset read")
    sources = {source["id"] for source in dataset["sources"] if isinstance(source, Mapping) and "id" in source}
    if refresh_source_ids is not None and (not isinstance(refresh_source_ids, list)
            or not refresh_source_ids or any(not isinstance(value, str) or value not in sources
                                             for value in refresh_source_ids)
            or len(set(refresh_source_ids)) != len(refresh_source_ids)):
        raise InputContractError("refresh_source_ids must be distinct source IDs from this Dataset")
    data: dict[str, Any] = {"dataset": dataset}
    if refresh_source_ids:
        data["updates"] = [{"action": "refresh_source", "source": {"id": value, "force_update_fields": False}}
                           for value in refresh_source_ids]
    response = api.read("validateDataset", {"datasetId": identity["object_id"], "data": data})
    state = response.get("dataset") if isinstance(response, Mapping) else None
    if not isinstance(state, dict):
        raise DataLensApiError("validateDataset response.dataset must be an object", method="validateDataset",
                               remote_code="invalid_response", stage="response_validation")
    validation = dataset_validation_summary(state)
    result = {"ok": validation["status"] == "valid", "identity": identity, "validation": validation,
              "proof_level": "provider_validation_only", "persisted": False, "provider_writes": 0}
    if include_state:
        result["validated_dataset"] = state
    return result


def calculation_level(field: Mapping[str, Any]) -> str:
    formula = str(field.get("formula") or "")
    if _LOD_RE.search(formula):
        return "lod"
    if _TIME_RE.search(formula):
        return "window"
    if _AGG_RE.search(formula) or str(field.get("aggregation") or "").lower() not in {"", "none"}:
        return "aggregate"
    return "row"


def validate_dataset_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(fields):
        if not isinstance(raw, dict):
            issues.append(
                {"code": "field_shape_invalid", "path": f"fields[{index}]", "message": "field must be an object"}
            )
            continue
        guid = str(raw.get("guid") or "").strip()
        title = str(raw.get("title") or raw.get("name") or guid).strip()
        if not guid:
            issues.append(
                {
                    "code": "field_guid_missing",
                    "path": f"fields[{index}].guid",
                    "message": "dataset field GUID is required",
                }
            )
            continue
        if guid.lower() in TECHNICAL_MEASURES or title.lower() in TECHNICAL_MEASURES:
            issues.append(
                {
                    "code": "technical_measure_is_not_dataset_field",
                    "path": f"fields[{index}]",
                    "message": "Measure Names and Measure Values are chart-generated technical fields, not Dataset fields",
                }
            )
            continue
        if guid in seen:
            issues.append(
                {
                    "code": "field_guid_duplicate",
                    "path": f"fields[{index}].guid",
                    "message": f"duplicate field GUID: {guid}",
                }
            )
            continue
        seen.add(guid)
        level = calculation_level(raw)
        item = dict(raw)
        item["guid"] = guid
        item["title"] = title
        item.setdefault("name", title)
        item.setdefault("calc_mode", "formula" if item.get("formula") else "direct")
        item["calculation_level"] = level
        normalized.append(item)
    return {
        "ok": not issues,
        "fields": normalized,
        "issues": issues,
        "limits": {"formula_validation": "known_field_rules_only", "provider_planner_required": True},
    }


def validate_visualization_fields(fields: list[dict[str, Any]], field_guids: list[str]) -> dict[str, Any]:
    """Apply cross-field restrictions to used fields and their named dependencies.

    This is a conservative local check, not the provider's formula parser.
    Unused Dataset fields cannot make an otherwise independent chart invalid.
    """
    by_guid = {str(field.get("guid")): field for field in fields}
    by_title = {str(field.get("title") or field.get("name")): str(field.get("guid")) for field in fields}
    pending, visited = list(field_guids), set()
    selected = []
    issues = []
    for guid in dict.fromkeys(field_guids):
        if guid not in by_guid:
            issues.append(
                {
                    "code": "visualization_field_guid_unknown",
                    "path": "visualization.fields",
                    "message": f"field GUID is absent from Dataset readback: {guid}",
                }
            )
    while pending:
        guid = pending.pop()
        if guid in visited:
            continue
        visited.add(guid)
        field = by_guid.get(guid)
        if field is None:
            continue
        selected.append(field)
        for title in re.findall(r"\[([^\]]+)\]", str(field.get("formula") or "")):
            if title in by_title:
                pending.append(by_title[title])
    formulas = [str(field.get("formula") or "") for field in selected]
    if any(_LOD_RE.search(formula) for formula in formulas) and any(_TIME_RE.search(formula) for formula in formulas):
        issues.append(
            {
                "code": "lod_with_time_intelligence",
                "path": "visualization.fields",
                "message": "DataLens does not support LOD in the same visualization as AGO or AT_DATE, even across fields",
            }
        )
    return {
        "ok": not issues,
        "field_guids": sorted(visited),
        "issues": issues,
        "limits": {"formula_validation": "known_cross-field_rules_only", "provider_planner_required": True},
    }


def wire_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report = validate_dataset_fields(fields)
    return [{key: value for key, value in item.items() if key != "calculation_level"} for item in report["fields"]]


def extract_dataset_fields(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [
        payload.get("result_schema"),
        payload.get("resultSchema"),
        payload.get("fields"),
    ]
    for key in ("dataset", "entry", "data", "result", "response"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            candidates.extend((nested.get("result_schema"), nested.get("resultSchema"), nested.get("fields")))
            nested_data = nested.get("data")
            if isinstance(nested_data, Mapping):
                candidates.extend(
                    (nested_data.get("result_schema"), nested_data.get("resultSchema"), nested_data.get("fields"))
                )
    for value in candidates:
        if isinstance(value, (list, tuple)):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    # The full API-v2 Dataset state may be inside data.dataset (or result.data).
    # Follow only known response envelopes, never arbitrary business objects.
    for key in ("dataset", "entry", "data", "result", "response"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            fields = extract_dataset_fields(nested)
            if fields:
                return fields
    return []
