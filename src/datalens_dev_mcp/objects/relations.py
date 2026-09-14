from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

SCOPE_TO_OBJECT_TYPE = {
    "dash": "dashboard",
    "dashboard": "dashboard",
    "dataset": "dataset",
    "connection": "connection",
    "wizard": "wizard_chart",
    "wizard_chart": "wizard_chart",
    "chart": "wizard_chart",
    "editor": "editor_chart",
    "editor_chart": "editor_chart",
    "advanced-chart": "editor_chart",
    "ql": "ql_chart",
    "ql_chart": "ql_chart",
    "html_page": "html_page",
}

EDITOR_SUBTYPES = {"table_node", "d3_node", "advanced-chart_node", "markdown_node", "control_node"}


def object_identity(entry: Mapping[str, Any]) -> tuple[str, str]:
    nested = entry.get("entry") if isinstance(entry.get("entry"), Mapping) else {}
    object_id = str(
        entry.get("entryId")
        or entry.get("id")
        or entry.get("objectId")
        or entry.get("workbookId")
        or nested.get("entryId")
        or nested.get("id")
        or ""
    ).strip()
    scope = str(entry.get("scope") or entry.get("type") or nested.get("scope") or nested.get("type") or "").lower()
    if not scope and entry.get("workbookId") and not (entry.get("entryId") or entry.get("id")):
        scope = "workbook"
    subtype = str(entry.get("subtype") or entry.get("type") or nested.get("type") or "").lower()
    if scope == "widget" or scope == subtype:
        if subtype.endswith("_wizard_node"):
            return object_id, "wizard_chart"
        if subtype.endswith("_ql_node"):
            return object_id, "ql_chart"
        if subtype in EDITOR_SUBTYPES:
            return object_id, "editor_chart"
    return object_id, SCOPE_TO_OBJECT_TYPE.get(scope, scope.replace("-node", "_node"))


def compact_object_index(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        object_id, object_type = object_identity(entry)
        if not object_id:
            continue
        nested = entry.get("entry") if isinstance(entry.get("entry"), Mapping) else {}
        item: dict[str, Any] = {
            "id": object_id,
            "type": str(entry.get("scope") or entry.get("type") or nested.get("scope") or object_type),
            "object_type": object_type,
        }
        subtype = entry.get("subtype") or entry.get("type") or nested.get("type")
        if subtype and subtype != item["type"]:
            item["subtype"] = str(subtype)
        name = (entry.get("name") or entry.get("title") or entry.get("displayKey")
                or nested.get("name") or nested.get("title") or nested.get("displayKey"))
        if name:
            item["name"] = str(name)
        for source, destination in (("key", "key"), ("workbookId", "workbook_id"),
                                    ("collectionId", "collection_id"), ("revId", "revision_id"),
                                    ("savedId", "saved_revision_id"), ("publishedId", "published_revision_id"),
                                    ("hidden", "hidden")):
            value = entry.get(source, nested.get(source))
            if value is not None and not (source == "key" and value == name):
                item[destination] = value
        result.append(item)
    return sorted(result, key=lambda item: str(item["id"]))


def relation_entries(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    value: Any = response
    while isinstance(value, Mapping) and isinstance(value.get("result"), Mapping):
        value = value["result"]
    if isinstance(value, Mapping) and isinstance(value.get("response"), Mapping):
        value = value["response"]
    if not isinstance(value, Mapping):
        return []
    candidates = value.get("entries") or value.get("relations") or []
    return [dict(item) for item in candidates if isinstance(item, Mapping)]
