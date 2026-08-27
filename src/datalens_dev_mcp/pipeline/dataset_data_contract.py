from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.dataset_preview import compile_dataset_preview_request
from datalens_dev_mcp.pipeline.dataset_fields import physical_dataset_field_type, semantic_dataset_field_role
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

DATASET_DATA_SEMANTICS = frozenset({"unknown_experimental", "current_default", "published_only", "saved_current"})
DECLARED_DATASET_TYPES = frozenset(
    {
        "integer",
        "uinteger",
        "float",
        "boolean",
        "string",
        "date",
        "genericdatetime",
        "datetimetz",
        "array_int",
        "array_float",
        "array_str",
        "geopoint",
        "geopolygon",
        "hierarchy",
        "tree_str",
        "tree_int",
        "tree_float",
        "markup",
        "heatmap",
        "unsupported",
    }
)
DATASET_DATA_API_CONTRACT_HASH = canonical_hash(
    {
        "method": "getDatasetData",
        "request": ["datasetId", "workbookId", "columns", "filters", "params", "sort", "limit", "offset"],
        "response": {"schema": "field[]", "rows": "positional[]"},
        "revision_parameter": False,
        "experimental": True,
    }
)


def build_field_catalog(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for item in fields:
        if not isinstance(item, dict):
            continue
        guid = str(item.get("guid") or "").strip()
        if not guid:
            continue
        catalog.append(
            {
                "guid": guid,
                "name": str(item.get("name") or item.get("title") or guid),
                "type": physical_dataset_field_type(item),
                "semantic_role": semantic_dataset_field_role(item),
                "aggregation": str(item.get("aggregation") or ""),
                "formula": str(item.get("formula") or ""),
                "source": str(item.get("source") or item.get("sourceColumn") or ""),
                "hidden": bool(item.get("hidden") or item.get("isHidden")),
                "unique": bool(item.get("unique") or item.get("isUnique")),
                "sensitive": bool(item.get("sensitive") or item.get("pii")),
            }
        )
    return sorted(catalog, key=lambda item: item["guid"])


def resolve_field_guids(
    requested: list[str],
    catalog: list[dict[str, Any]],
    *,
    chart_bound_guids: list[str] | None = None,
) -> dict[str, Any]:
    by_guid = {str(item.get("guid") or ""): item for item in catalog}
    by_name: dict[str, list[str]] = {}
    for item in catalog:
        by_name.setdefault(str(item.get("name") or ""), []).append(str(item.get("guid") or ""))
    bound = set(chart_bound_guids or [])
    resolved: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw in requested:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in by_guid:
            guid = value
        else:
            candidates = by_name.get(value, [])
            narrowed = [guid for guid in candidates if guid in bound]
            if len(narrowed) == 1:
                guid = narrowed[0]
            elif len(candidates) == 1:
                guid = candidates[0]
            elif candidates:
                ambiguous.append({"name": value, "candidate_guids": sorted(candidates)})
                continue
            else:
                missing.append(value)
                continue
        if guid not in resolved:
            resolved.append(guid)
    return {
        "ok": not ambiguous and not missing,
        "guids": resolved,
        "ambiguous": ambiguous,
        "missing": missing,
    }


def validate_dataset_data_query(
    query: dict[str, Any],
    *,
    field_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    compiled = compile_dataset_preview_request(
        dataset_id=str(query.get("datasetId") or query.get("dataset_id") or ""),
        workbook_id=str(query.get("workbookId") or query.get("workbook_id") or ""),
        columns=[str(item) for item in query.get("columns") or []],
        dataset_fields=field_catalog,
        filters=list(query.get("filters") or []),
        params=list(query.get("params") or []),
        sort=list(query.get("sort") or []),
        limit=query.get("limit", 100),
        offset=query.get("offset", 0),
        max_pages=query.get("max_pages", 1),
        tie_breaker_fields=list(query.get("tie_breaker_fields") or []),
    )
    payload = dict(compiled.get("payload") or {})
    contract = {
        "schema_id": "dataset_data_query",
        "mode": str(query.get("mode") or "context_probe"),
        "payload": payload,
        "paging": dict(compiled.get("paging") or {}),
        "dataset_data_semantics": str(query.get("dataset_data_semantics") or "unknown_experimental"),
        "api_contract_hash": DATASET_DATA_API_CONTRACT_HASH,
    }
    issues = list(compiled.get("issues") or [])
    if contract["mode"] not in {"context_probe", "assertion_probe", "diagnostic_probe"}:
        issues.append("dataset probe mode is unsupported")
    if contract["dataset_data_semantics"] not in DATASET_DATA_SEMANTICS:
        issues.append("dataset_data_semantics is unsupported")
    contract["query_hash"] = dataset_data_query_hash(contract)
    return {
        "ok": not issues,
        "status": "validated" if not issues else "blocked",
        "issues": issues,
        "contract": contract,
    }


def dataset_data_query_hash(contract: dict[str, Any]) -> str:
    material = dict(contract)
    material.pop("query_hash", None)
    return canonical_hash(material)
