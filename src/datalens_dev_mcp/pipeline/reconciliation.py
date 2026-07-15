from __future__ import annotations

from typing import Any

from datalens_dev_mcp.validators.datalens_names import sanitize_datalens_internal_name


def reconcile_partial_creates(
    *,
    workbook_id: str,
    planned_objects: list[dict[str, Any]],
    entries_payload: dict[str, Any],
) -> dict[str, Any]:
    entries = [_normalize_entry(entry) for entry in _extract_entries(entries_payload)]
    objects: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    matched_entry_ids: set[str] = set()

    for planned in planned_objects:
        normalized = _normalize_planned(planned)
        matches = [
            entry
            for entry in entries
            if _type_compatible(normalized["object_type"], entry["object_type"])
            and (
                normalized["internal_name"]
                and normalized["internal_name"] in entry["internal_names"]
                or normalized["display_title"]
                and normalized["display_title"] in entry["display_titles"]
            )
        ]
        for match in matches:
            matched_entry_ids.add(match["entry_id"])
        if len(matches) > 1:
            status = "duplicate"
            recommended_action = "manual_review"
            duplicates.append(
                {
                    "internal_name": normalized["internal_name"],
                    "display_title": normalized["display_title"],
                    "object_type": normalized["object_type"],
                    "entry_ids": [match["entry_id"] for match in matches],
                }
            )
        elif len(matches) == 1:
            status = "existing"
            recommended_action = "reuse"
        else:
            status = "missing"
            recommended_action = "create"
        objects.append(
            {
                "planned": normalized,
                "status": status,
                "existing_object_id": matches[0]["entry_id"] if len(matches) == 1 else "",
                "matches": matches,
                "duplicates": len(matches) > 1,
                "recommended_action": recommended_action,
            }
        )

    planned_types = {_normalize_object_type(item.get("object_type", "")) for item in planned_objects}
    orphans = [
        {
            "entry_id": entry["entry_id"],
            "object_type": entry["object_type"],
            "display_titles": entry["display_titles"],
            "internal_names": sorted(entry["internal_names"]),
        }
        for entry in entries
        if entry["entry_id"] not in matched_entry_ids and (not planned_types or entry["object_type"] in planned_types)
    ]
    return {
        "ok": True,
        "workbook_id": workbook_id,
        "objects": objects,
        "manual_review_required": bool(duplicates),
        "reuse_existing_objects": [item for item in objects if item["recommended_action"] == "reuse"],
        "missing_objects": [item for item in objects if item["recommended_action"] == "create"],
        "duplicates_detected": duplicates,
        "orphan_candidates": orphans,
        "delete_attempted": False,
        "delete_supported": False,
    }


def _extract_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("entries"), list):
        return payload["entries"]
    if isinstance(payload.get("pages"), list):
        entries: list[dict[str, Any]] = []
        for page in payload["pages"]:
            if isinstance(page, dict) and isinstance(page.get("entries"), list):
                entries.extend(page["entries"])
        return entries
    return []


def _normalize_planned(planned: dict[str, Any]) -> dict[str, str]:
    display_title = str(planned.get("display_title") or planned.get("title") or planned.get("name") or "").strip()
    internal_name = str(planned.get("internal_name") or planned.get("name") or "").strip()
    if internal_name:
        internal_name = sanitize_datalens_internal_name(internal_name)
    elif display_title:
        internal_name = sanitize_datalens_internal_name(display_title)
    return {
        "display_title": display_title,
        "internal_name": internal_name,
        "object_type": _normalize_object_type(str(planned.get("object_type") or planned.get("type") or "")),
    }


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry.get("entryId") or entry.get("id") or "").strip()
    display_titles = _compact_strings(
        entry.get("displayKey"),
        entry.get("title"),
        entry.get("displayTitle"),
        entry.get("name"),
        (entry.get("data") or {}).get("title") if isinstance(entry.get("data"), dict) else "",
    )
    raw_names = _compact_strings(
        entry.get("name"),
        entry.get("key"),
        (entry.get("data") or {}).get("name") if isinstance(entry.get("data"), dict) else "",
        (entry.get("meta") or {}).get("name") if isinstance(entry.get("meta"), dict) else "",
    )
    internal_names = sorted({sanitize_datalens_internal_name(value) for value in raw_names if value})
    return {
        "entry_id": entry_id,
        "object_type": _normalize_object_type(str(entry.get("scope") or entry.get("type") or "")),
        "display_titles": display_titles,
        "internal_names": internal_names,
    }


def _compact_strings(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalize_object_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"advanced_chart_node", "advanced_chart", "advanced_editor", "chart", "editor"}:
        return "editor_chart"
    if normalized in {"table_node", "markdown_node", "control_node", "advanced_chart_node"}:
        return "editor_chart"
    if "chart" in normalized and "wizard" not in normalized:
        return "editor_chart"
    if "wizard" in normalized:
        return "wizard_chart"
    if "dashboard" in normalized:
        return "dashboard"
    if "dataset" in normalized:
        return "dataset"
    if "connection" in normalized or "connector" in normalized:
        return "connector"
    return normalized or "unknown"


def _type_compatible(planned_type: str, entry_type: str) -> bool:
    return planned_type in {"", "unknown"} or entry_type in {"", "unknown"} or planned_type == entry_type
