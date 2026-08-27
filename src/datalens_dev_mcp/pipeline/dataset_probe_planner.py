from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.pipeline.dataset_data_contract import (
    build_field_catalog,
    resolve_field_guids,
    validate_dataset_data_query,
)
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

DATE_TYPES = frozenset({"date", "genericdatetime", "datetimetz"})
NUMERIC_TYPES = frozenset({"integer", "uinteger", "float"})
DIMENSION_TYPES = frozenset({"string", "boolean"})


class DatasetProbePlanner:
    def plan(
        self,
        contract: dict[str, Any],
        target_graph: dict[str, Any],
        *,
        mode: str = "context_probe",
        requested_fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        params: list[dict[str, Any]] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        datasets = [
            item for item in target_graph.get("nodes") or []
            if isinstance(item, dict) and item.get("object_type") == "dataset"
        ]
        if not datasets:
            return {"ok": False, "status": "blocked", "issues": ["target graph has no dataset dependency"]}
        dataset_selection = _select_dataset(contract, target_graph, datasets)
        if not dataset_selection["ok"]:
            return dataset_selection
        dataset = dataset_selection["dataset"]
        catalog = build_field_catalog(list(dataset.get("field_catalog") or []))
        requested = list(requested_fields or []) or _acceptance_field_mentions(contract, catalog)
        chart_bound_guids = _chart_bound_guids(contract, target_graph, str(dataset.get("object_id") or ""))
        resolution = resolve_field_guids(requested, catalog, chart_bound_guids=chart_bound_guids)
        if not resolution["ok"]:
            return {
                "ok": False,
                "status": "blocked",
                "issues": ["field resolution is ambiguous or incomplete"],
                "field_resolution": resolution,
            }
        columns = _minimal_columns(catalog, required=resolution["guids"])
        unique = next((item["guid"] for item in catalog if item.get("unique") and item["guid"] in columns), "")
        date = next((item["guid"] for item in catalog if item.get("type") in DATE_TYPES and item["guid"] in columns), "")
        sort: list[dict[str, str]] = []
        if unique:
            if date and date != unique:
                sort.append({"guid": date, "direction": "desc"})
            sort.append({"guid": unique, "direction": "asc"})
        target = contract.get("target") or {}
        query = {
            "mode": mode,
            "datasetId": str(dataset.get("object_id") or ""),
            "workbookId": str(target.get("workbook_id") or ""),
            "columns": columns,
            "filters": list(filters or []),
            "params": list(params or []),
            "sort": sort,
            "limit": min(200, max(1, int(limit))),
            "offset": 0,
            "max_pages": 1,
            "tie_breaker_fields": [unique] if unique else [],
            "dataset_data_semantics": "unknown_experimental",
        }
        validated = validate_dataset_data_query(query, field_catalog=catalog)
        if not validated["ok"]:
            return {**validated, "field_catalog": catalog, "field_resolution": resolution}
        query_contract = dict(validated["contract"])
        limitations = [] if unique else ["bounded sample has no proven total order"]
        plan = {
            "schema_id": "dataset_probe_plan",
            "mode": mode,
            "dataset_id": str(dataset.get("object_id") or ""),
            "dataset_revision": str(dataset.get("saved_revision") or ""),
            "dataset_schema_hash": str(dataset.get("field_catalog_hash") or canonical_hash(catalog)),
            "field_catalog": catalog,
            "queries": [query_contract],
            "limitations": limitations,
            "budget": {
                "max_queries": 12,
                "max_rows_total": 2000,
                "max_cells_total": 20000,
                "max_bytes_total": 1000000,
                "max_pages_per_query": 3,
                "timeout_seconds": 60,
            },
        }
        plan["query_set_hash"] = canonical_hash(plan["queries"])
        return {"ok": True, "status": "ready", "plan": plan, "field_resolution": resolution}


def _minimal_columns(catalog: list[dict[str, Any]], *, required: list[str]) -> list[str]:
    chosen = list(dict.fromkeys(required))
    groups = (
        (lambda item: item.get("type") in DATE_TYPES, 1),
        (lambda item: item.get("type") in NUMERIC_TYPES, 2),
        (lambda item: item.get("type") in DIMENSION_TYPES and not item.get("sensitive") and not item.get("hidden"), 2),
        (lambda item: bool(item.get("unique")), 1),
    )
    for predicate, count in groups:
        for item in [row for row in catalog if predicate(row)][:count]:
            if item["guid"] not in chosen:
                chosen.append(item["guid"])
    if not chosen and catalog:
        chosen.append(catalog[0]["guid"])
    return chosen[:8]


def _acceptance_field_mentions(contract: dict[str, Any], catalog: list[dict[str, Any]]) -> list[str]:
    text = " ".join(str(item.get("statement") or "") for item in contract.get("acceptance") or [] if isinstance(item, dict))
    return [
        str(item.get("guid") or "")
        for item in catalog
        if re.search(rf"(?<![\w-]){re.escape(str(item.get('name') or ''))}(?![\w-])", text, re.IGNORECASE)
    ]


def _select_dataset(
    contract: dict[str, Any],
    graph: dict[str, Any],
    datasets: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {str(item.get("object_id") or ""): item for item in datasets}
    target_ids = {
        str(item)
        for item in (
            list((contract.get("scope") or {}).get("allowed_objects") or [])
            + list((contract.get("target") or {}).get("object_ids") or [])
        )
        if str(item)
    }
    direct = [by_id[item] for item in sorted(target_ids) if item in by_id]
    linked_ids = {
        str(edge.get("target") or "")
        for edge in graph.get("edges") or []
        if isinstance(edge, dict)
        and edge.get("relation") == "uses_dataset"
        and str(edge.get("source") or "") in target_ids
        and str(edge.get("target") or "") in by_id
    }
    linked = [by_id[item] for item in sorted(linked_ids)]
    candidates = direct or linked or datasets
    unique = {str(item.get("object_id") or ""): item for item in candidates}
    if len(unique) != 1:
        return {
            "ok": False,
            "status": "blocked",
            "issues": ["multiple dataset dependencies require an exact chart or dataset target"],
            "candidate_dataset_ids": sorted(unique),
        }
    return {"ok": True, "dataset": next(iter(unique.values()))}


def _chart_bound_guids(contract: dict[str, Any], graph: dict[str, Any], dataset_id: str) -> list[str]:
    chart_ids = {
        str(edge.get("source") or "")
        for edge in graph.get("edges") or []
        if isinstance(edge, dict)
        and edge.get("relation") == "uses_dataset"
        and str(edge.get("target") or "") == dataset_id
    }
    scoped = set((contract.get("scope") or {}).get("allowed_objects") or [])
    if scoped and chart_ids & scoped:
        chart_ids &= scoped
    return sorted(
        {
            str(guid)
            for node in graph.get("nodes") or []
            if isinstance(node, dict) and str(node.get("object_id") or "") in chart_ids
            for guid in node.get("field_guids") or []
            if str(guid)
        }
    )
