from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from datalens_dev_mcp.validators.redaction import sanitize_value


DEFAULT_INLINE_CHAR_BUDGET = 20_000
WORKBOOK_ENTRY_PREVIEW_LIMIT = 12
RESPONSE_MODES = ("summary", "structure", "full", "artifact")
_MCP_RUN_ARTIFACT_DIR_VALUE = Path(os.environ.get("DATALENS_MCP_RUN_ARTIFACT_DIR", "artifacts/runtime/mcp_runs"))


def stable_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(stable_json_text(value).encode("utf-8")).hexdigest()


def serialized_metadata(value: Any) -> dict[str, Any]:
    text = stable_json_text(value)
    return {
        "serialized_chars": len(text),
        "serialized_bytes": len(text.encode("utf-8")),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def sanitize_response(value: Any) -> Any:
    return sanitize_value(value)


def project_dashboard_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="dashboard",
        response=response,
        summary=dashboard_summary(response),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_editor_chart_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="editor_chart",
        response=response,
        summary=editor_chart_summary(response),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_workbook_entries_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="workbook_entries",
        response=response,
        summary=workbook_entries_summary(response),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_audit_entries_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="audit_entries",
        response=response,
        summary=audit_entries_summary(response),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_wizard_chart_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="wizard_chart",
        response=response,
        summary=object_summary(response, object_key="chart", preferred_id="chartId"),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_dataset_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="dataset",
        response=response,
        summary=object_summary(response, object_key="dataset", preferred_id="datasetId"),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_connection_response(
    response: dict[str, Any],
    *,
    response_mode: str = "summary",
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    project_root: str | Path = ".",
    run_id: str = "",
) -> dict[str, Any]:
    return project_response(
        kind="connection",
        response=response,
        summary=object_summary(response, object_key="connection", preferred_id="connectionId"),
        response_mode=response_mode,
        inline_char_budget=inline_char_budget,
        project_root=project_root,
        run_id=run_id,
    )


def project_response(
    *,
    kind: str,
    response: dict[str, Any],
    summary: dict[str, Any],
    response_mode: str,
    inline_char_budget: int,
    project_root: str | Path,
    run_id: str,
) -> dict[str, Any]:
    mode = normalize_response_mode(response_mode)
    budget = max(0, int(inline_char_budget))
    sanitized = sanitize_response(response)
    sanitized_summary = sanitize_response(summary)
    full_metadata = serialized_metadata(sanitized)
    projected: dict[str, Any] = {
        "ok": True,
        "response_mode": mode,
        "requested_response_mode": mode,
        "summary_kind": kind,
        "summary": sanitized_summary,
        "full_response": full_metadata,
    }
    should_spill = mode == "artifact" or full_metadata["serialized_chars"] > budget
    if mode in {"summary", "structure"}:
        if should_spill:
            projected["artifact"] = write_full_artifact(
                kind=kind,
                response=sanitized,
                project_root=project_root,
                run_id=run_id,
                full_hash=full_metadata["sha256"],
            )
        return projected
    if mode == "artifact" or should_spill:
        projected["response_mode"] = "artifact"
        projected["artifact"] = write_full_artifact(
            kind=kind,
            response=sanitized,
            project_root=project_root,
            run_id=run_id,
            full_hash=full_metadata["sha256"],
        )
        return projected
    projected["response"] = sanitized
    return projected


def normalize_response_mode(response_mode: str) -> str:
    mode = str(response_mode or "summary").strip().lower()
    if mode not in RESPONSE_MODES:
        raise ValueError(f"response_mode must be one of {RESPONSE_MODES}")
    return mode


def write_full_artifact(
    *,
    kind: str,
    response: dict[str, Any],
    project_root: str | Path,
    run_id: str,
    full_hash: str,
) -> dict[str, Any]:
    safe_run_id = _safe_run_id(run_id or f"run_{full_hash[:12]}")
    root = Path(project_root)
    artifact_root = _MCP_RUN_ARTIFACT_DIR_VALUE
    if not artifact_root.is_absolute():
        artifact_root = root / artifact_root
    path = artifact_root / safe_run_id / f"{kind}.{full_hash[:12]}.full.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = stable_json_text(response) + "\n"
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path),
        "serialized_chars": len(text) - 1,
        "serialized_bytes": len(text.encode("utf-8")) - 1,
        "sha256": full_hash,
    }


def dashboard_summary(response: dict[str, Any]) -> dict[str, Any]:
    entry = _entry(response, "dashboard")
    data = _data(response, entry, "dashboard")
    tabs = _as_list(data.get("tabs"))
    items = _dashboard_items(data, tabs)
    links = _as_list(data.get("links"))
    selectors = _as_list(data.get("selectors") or data.get("controls"))
    chart_ids = sorted(
        {
            str(item.get("chartId") or item.get("chart_id") or item.get("entryId") or "")
            for item in items
            if isinstance(item, dict) and (item.get("chartId") or item.get("chart_id") or item.get("entryId"))
        }
    )
    selector_impact = [
        {
            "source": link.get("from") or link.get("source") or link.get("selectorId") or link.get("selector_id"),
            "target": link.get("to") or link.get("target") or link.get("chartId") or link.get("chart_id"),
            "param": link.get("param") or link.get("parameter") or link.get("field"),
        }
        for link in links
        if isinstance(link, dict)
    ]
    return {
        "identity": _identity(entry, response, preferred_id="dashboardId"),
        "workbook_id": _first(entry, response, keys=("workbookId", "workbook_id")),
        "title": _title(entry, data),
        "branch": str(response.get("branch") or entry.get("branch") or ""),
        "tabs": [
            {
                "id": tab.get("id") or tab.get("tabId") or tab.get("key"),
                "title": tab.get("title") or tab.get("name"),
                "item_count": len(_as_list(tab.get("items"))),
            }
            for tab in tabs
            if isinstance(tab, dict)
        ],
        "counts": {
            "tabs": len(tabs),
            "items": len(items),
            "controls": _control_count(items, selectors),
            "widgets": max(0, len(items) - _control_count(items, selectors)),
            "links": len(links),
            "linked_objects": len(chart_ids),
        },
        "selector_impact_wiring": {
            "count": len(selector_impact),
            "targets": sorted({str(item["target"]) for item in selector_impact if item.get("target")}),
            "links": selector_impact[:50],
        },
        "linked_object_ids": chart_ids[:100],
        "data_metadata": serialized_metadata(data),
    }


def editor_chart_summary(response: dict[str, Any]) -> dict[str, Any]:
    entry = _entry(response, "chart")
    data = _data(response, entry, "chart")
    links = _as_list(response.get("links") or entry.get("links") or data.get("links"))
    section_metadata = []
    for name in sorted(data):
        value = data[name]
        text = stable_json_text(value)
        section_metadata.append(
            {
                "name": name,
                "serialized_chars": len(text),
                "serialized_bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "identity": _identity(entry, response, preferred_id="chartId"),
        "workbook_id": _first(entry, response, keys=("workbookId", "workbook_id")),
        "type": entry.get("type") or entry.get("scope") or response.get("type") or "editor_chart",
        "title": _title(entry, data),
        "annotation": data.get("annotation") or data.get("description") or "",
        "links": {
            "count": len(links),
            "ids": [
                str(link.get("id") or link.get("linkId") or link.get("target") or link.get("to"))
                for link in links
                if isinstance(link, dict) and (link.get("id") or link.get("linkId") or link.get("target") or link.get("to"))
            ][:100],
        },
        "data_sections": section_metadata,
        "data_metadata": serialized_metadata(data),
    }


def workbook_entries_summary(response: dict[str, Any]) -> dict[str, Any]:
    entries = _as_list(response.get("entries") or response.get("items") or response.get("result"))
    rows = []
    type_counts: Counter[str] = Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("scope") or entry.get("type") or "unknown")
        type_counts[entry_type] += 1
        if len(rows) < WORKBOOK_ENTRY_PREVIEW_LIMIT:
            rows.append(
                {
                    "entry_id": entry.get("entryId") or entry.get("id"),
                    "type": entry_type,
                    "title": _truncate_text(entry.get("displayKey") or entry.get("title") or entry.get("name"), 120),
                    "workbook_id": entry.get("workbookId") or entry.get("workbook_id"),
                }
            )
    return {
        "count": len(entries),
        "pagination": {
            "page": response.get("page"),
            "page_size": response.get("pageSize") or response.get("page_size"),
            "total": response.get("total") or response.get("totalCount") or response.get("total_count"),
        },
        "type_counts": dict(sorted(type_counts.items())),
        "entries": rows,
        "entry_preview_limit": WORKBOOK_ENTRY_PREVIEW_LIMIT,
        "entries_truncated": len(entries) > len(rows),
        "full_response": serialized_metadata(response),
    }


def audit_entries_summary(response: dict[str, Any]) -> dict[str, Any]:
    entries = _as_list(response.get("entries") or response.get("items") or response.get("result"))
    rows: list[dict[str, Any]] = []
    scope_counts: Counter[str] = Counter()
    deleted_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        scope = str(entry.get("scope") or "unknown")
        scope_counts[scope] += 1
        if entry.get("isDeleted") is True:
            deleted_count += 1
        if len(rows) < WORKBOOK_ENTRY_PREVIEW_LIMIT:
            rows.append(
                {
                    "entry_id": entry.get("entryId") or entry.get("id"),
                    "scope": scope,
                    "type": entry.get("type"),
                    "is_deleted": entry.get("isDeleted") is True,
                    "updated_at": entry.get("updatedAt"),
                    "scope_policy": "audit_only" if scope == "artifact" else "audit_projection",
                }
            )
    return {
        "count": len(entries),
        "deleted_count": deleted_count,
        "scope_counts": dict(sorted(scope_counts.items())),
        "entries": rows,
        "entry_preview_limit": WORKBOOK_ENTRY_PREVIEW_LIMIT,
        "entries_truncated": len(entries) > len(rows),
        "next_page_token_present": bool(response.get("nextPageToken")),
        "scope_policy": {
            "artifact": "audit_only_not_generic_object",
            "compute": "inventory_and_audit_only_without_direct_hydration",
        },
        "full_response": serialized_metadata(response),
    }


def object_summary(response: dict[str, Any], *, object_key: str, preferred_id: str) -> dict[str, Any]:
    entry = _entry(response, object_key)
    data = _data(response, entry, object_key)
    if object_key == "dataset":
        return dataset_summary(response, entry=entry, data=data, preferred_id=preferred_id)
    if object_key == "connection":
        return connection_summary(response, entry=entry, data=data, preferred_id=preferred_id)
    return {
        "identity": _identity(entry, response, preferred_id=preferred_id),
        "workbook_id": _first(entry, response, keys=("workbookId", "workbook_id")),
        "type": entry.get("type") or entry.get("scope") or response.get("type") or object_key,
        "title": _title(entry, data),
        "data_metadata": serialized_metadata(data),
        "full_response": serialized_metadata(response),
        "top_level_keys": sorted(response)[:100],
    }


def dataset_summary(
    response: dict[str, Any],
    *,
    entry: dict[str, Any],
    data: dict[str, Any],
    preferred_id: str,
) -> dict[str, Any]:
    dataset_payload = _first_nonempty_dict(entry, data)
    fields = _dataset_fields(dataset_payload, data)
    sources = _dataset_sources(dataset_payload, data)
    sql_fragments = _bounded_sql_fragments(dataset_payload)
    connection_ids = sorted(_dataset_connection_ids(dataset_payload))
    return {
        "identity": _identity(entry, response, preferred_id=preferred_id),
        "workbook_id": _first(entry, response, keys=("workbookId", "workbook_id")),
        "type": entry.get("type") or entry.get("scope") or response.get("type") or "dataset",
        "title": _title(entry, data),
        "sources": {
            "count": len(sources),
            "types": sorted({str(source.get("type") or source.get("sourceType") or source.get("kind") or "unknown") for source in sources}),
        },
        "fields": {
            "count": len(fields),
            "items": [_compact_field(field) for field in fields[:50]],
            "truncated": len(fields) > 50,
        },
        "connection_ids": connection_ids[:50],
        "sql_fragments": sql_fragments,
        "validation": {
            "validate_dataset_available": True,
            "readback_available": True,
            "supported_readback_modes": ["summary", "structure", "artifact", "full"],
        },
        "data_metadata": serialized_metadata(data),
        "full_response": serialized_metadata(response),
        "top_level_keys": sorted(response)[:100],
    }


def connection_summary(
    response: dict[str, Any],
    *,
    entry: dict[str, Any],
    data: dict[str, Any],
    preferred_id: str,
) -> dict[str, Any]:
    connection_payload = _first_nonempty_dict(entry, data)
    return {
        "identity": _identity(entry, response, preferred_id=preferred_id),
        "workbook_id": _first(entry, response, keys=("workbookId", "workbook_id")),
        "type": entry.get("type") or entry.get("scope") or response.get("type") or "connection",
        "title": _title(entry, data),
        "connection_kind": connection_payload.get("type") or connection_payload.get("sourceType") or connection_payload.get("kind") or "",
        "data_metadata": serialized_metadata(data),
        "full_response": serialized_metadata(response),
        "top_level_keys": sorted(response)[:100],
    }


def _entry(response: dict[str, Any], object_key: str) -> dict[str, Any]:
    for wrapper_key in ("result", "response"):
        nested_response = response.get(wrapper_key)
        if isinstance(nested_response, dict):
            nested = _entry(nested_response, object_key)
            if nested and nested is not nested_response:
                return nested
            if _looks_like_object(nested_response, object_key):
                return nested_response
    if isinstance(response.get("entry"), dict):
        return response["entry"]
    nested = response.get(object_key)
    if isinstance(nested, dict) and isinstance(nested.get("entry"), dict):
        return nested["entry"]
    if isinstance(nested, dict):
        return nested
    return response if isinstance(response, dict) else {}


def _data(response: dict[str, Any], entry: dict[str, Any], object_key: str) -> dict[str, Any]:
    for wrapper_key in ("result", "response"):
        nested_response = response.get(wrapper_key)
        if isinstance(nested_response, dict):
            nested_data = _data(nested_response, entry, object_key)
            if nested_data:
                return nested_data
    if isinstance(entry.get("data"), dict):
        return entry["data"]
    nested = response.get(object_key)
    if isinstance(nested, dict) and isinstance(nested.get("data"), dict):
        return nested["data"]
    if isinstance(response.get("data"), dict):
        return response["data"]
    return {}


def _identity(entry: dict[str, Any], response: dict[str, Any], *, preferred_id: str) -> dict[str, Any]:
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    return {
        "id": _first(entry, response, result, metadata, keys=("entryId", preferred_id, "id")),
        "rev_id": _first(entry, response, result, metadata, keys=("revId", "rev_id", "revisionId", "revision_id", "revision")),
        "saved_id": _first(entry, response, result, metadata, keys=("savedId", "saved_id")),
        "name": _first(entry, response, keys=("name",)),
    }


def _first(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
    return ""


def _title(entry: dict[str, Any], data: dict[str, Any]) -> str:
    return str(data.get("title") or data.get("name") or entry.get("displayKey") or entry.get("name") or "")


def _looks_like_object(value: dict[str, Any], object_key: str) -> bool:
    preferred = {
        "dataset": ("datasetId", "dataset_id"),
        "connection": ("connectionId", "connection_id"),
        "dashboard": ("dashboardId", "entryId"),
        "chart": ("chartId", "entryId"),
    }.get(object_key, ("entryId", "id"))
    return any(value.get(key) for key in (*preferred, "id"))


def _first_nonempty_dict(*values: dict[str, Any]) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _dataset_fields(*sources: dict[str, Any]) -> list[dict[str, Any]]:
    for source in sources:
        for key in ("fields", "fieldItems", "datasetFields"):
            fields = source.get(key)
            if isinstance(fields, list):
                return [field for field in fields if isinstance(field, dict)]
        nested = source.get("dataset")
        if isinstance(nested, dict):
            fields = _dataset_fields(nested)
            if fields:
                return fields
    return []


def _dataset_sources(*sources: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        for key in ("sources", "source", "dataSources", "connections"):
            value = source.get(key)
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                rows.append(value)
        nested = source.get("dataset")
        if isinstance(nested, dict):
            rows.extend(_dataset_sources(nested))
    return rows


def _compact_field(field: dict[str, Any]) -> dict[str, Any]:
    formula = str(field.get("formula") or field.get("calc") or field.get("expression") or "")
    item = {
        "name": str(field.get("name") or field.get("title") or field.get("guid") or field.get("id") or ""),
        "guid": str(field.get("guid") or field.get("id") or field.get("fieldId") or ""),
        "type": str(field.get("type") or field.get("dataType") or ""),
        "aggregation": str(field.get("aggregation") or field.get("aggregationType") or ""),
    }
    if formula:
        item["formula"] = {
            "serialized_chars": len(formula),
            "sha256": hashlib.sha256(formula.encode("utf-8")).hexdigest(),
            "preview": formula[:120],
            "truncated": len(formula) > 120,
        }
    return item


def _dataset_connection_ids(source: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    if isinstance(source, dict):
        for key, value in source.items():
            lowered = str(key).lower()
            if lowered in {"connectionid", "connection_id", "connid", "conn_id"} and isinstance(value, str) and value:
                ids.add(value)
            elif isinstance(value, dict):
                ids.update(_dataset_connection_ids(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        ids.update(_dataset_connection_ids(item))
    return ids


def _bounded_sql_fragments(source: dict[str, Any]) -> list[dict[str, Any]]:
    fragments = []
    for path, value in _iter_string_values(source):
        key = path.rsplit(".", 1)[-1].lower()
        if any(token in key for token in ("sql", "query", "statement")) and value:
            fragments.append(
                {
                    "path": path,
                    "serialized_chars": len(value),
                    "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                }
            )
    return fragments[:20]


def _iter_string_values(value: Any, path: str = "$") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_iter_string_values(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_iter_string_values(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        rows.append((path, value))
    return rows


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _dashboard_items(data: dict[str, Any], tabs: list[Any]) -> list[Any]:
    items: list[Any] = []
    seen_ids: set[str] = set()

    def add_item(item: dict[str, Any]) -> None:
        item_id = str(item.get("id") or item.get("widgetId") or item.get("chartId") or item.get("entryId") or "")
        if item_id and item_id in seen_ids:
            return
        items.append(item)
        if item_id:
            seen_ids.add(item_id)

    for item in _iter_dashboard_leaf_items(data.get("items")):
        add_item(item)
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        for item in _iter_dashboard_leaf_items(tab):
            add_item(item)
    return items


def _iter_dashboard_leaf_items(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            found.extend(_iter_dashboard_leaf_items(item))
        return found
    if not isinstance(value, dict):
        return found
    if _is_dashboard_leaf_item(value):
        found.append(value)
    for key in ("items", "widgets", "children", "tabs", "sections", "blocks", "grid", "layout"):
        nested = value.get(key)
        if nested is not None:
            found.extend(_iter_dashboard_leaf_items(nested))
    return found


def _is_dashboard_leaf_item(item: dict[str, Any]) -> bool:
    if item.get("chartId") or item.get("chart_id") or item.get("entryId"):
        return True
    item_type = str(item.get("type") or item.get("kind") or item.get("scope") or "").lower()
    return "control" in item_type or "selector" in item_type


def _control_count(items: list[Any], selectors: list[Any]) -> int:
    if selectors:
        return len(selectors)
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or item.get("kind") or "").lower()
        if "control" in item_type or "selector" in item_type:
            count += 1
    return count


def _safe_run_id(run_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(run_id or "").strip())
    return cleaned[:80] or "run"
