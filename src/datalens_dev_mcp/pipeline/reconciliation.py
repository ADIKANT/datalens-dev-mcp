from __future__ import annotations

from typing import Any

from datalens_dev_mcp.validators.datalens_names import sanitize_datalens_internal_name


def validate_entries_reconciliation_evidence(
    entries_payload: dict[str, Any],
    *,
    expected_workbook_id: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    entries: list[dict[str, Any]] = []
    if not isinstance(entries_payload, dict):
        issues.append("entries_payload must be an object")
    elif "entries" in entries_payload:
        raw_entries = entries_payload.get("entries")
        if not isinstance(raw_entries, list) or not all(
            isinstance(entry, dict) for entry in raw_entries
        ):
            issues.append("entries_payload.entries must be an array of objects")
        else:
            entries = list(raw_entries)
        if str(entries_payload.get("nextPageToken") or "").strip():
            issues.append("entries_payload is incomplete because nextPageToken is present")
    elif "pages" in entries_payload:
        pages = entries_payload.get("pages")
        if not isinstance(pages, list) or not pages:
            issues.append("entries_payload.pages must be a non-empty array")
        else:
            for index, page in enumerate(pages):
                if not isinstance(page, dict) or not isinstance(page.get("entries"), list):
                    issues.append(f"entries_payload.pages[{index}].entries must be an array")
                    continue
                if not all(isinstance(entry, dict) for entry in page["entries"]):
                    issues.append(
                        f"entries_payload.pages[{index}].entries must contain only objects"
                    )
                    continue
                entries.extend(page["entries"])
            last_page = pages[-1] if isinstance(pages[-1], dict) else {}
            if str(last_page.get("nextPageToken") or "").strip():
                issues.append(
                    "entries_payload pages are incomplete because the last page has nextPageToken"
                )
    else:
        issues.append("entries_payload must contain entries or complete pages")
    observed_workbook_id = str(
        entries_payload.get("workbookId")
        or entries_payload.get("workbook_id")
        or ""
    ).strip() if isinstance(entries_payload, dict) else ""
    if (
        expected_workbook_id
        and observed_workbook_id
        and observed_workbook_id != expected_workbook_id
    ):
        issues.append(
            "entries_payload workbook identity does not match the planned workbook"
        )
    return {
        "ok": not issues,
        "issues": issues,
        "entry_count": len(entries),
        "complete": not issues,
        "workbook_id": observed_workbook_id or expected_workbook_id,
    }


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
    display_key = str(entry.get("displayKey") or "").strip()
    key = str(entry.get("key") or "").strip()
    display_titles = _compact_strings(
        display_key,
        _entry_leaf(display_key),
        entry.get("title"),
        entry.get("displayTitle"),
        entry.get("name"),
        (entry.get("data") or {}).get("title") if isinstance(entry.get("data"), dict) else "",
    )
    raw_names = _compact_strings(
        entry.get("name"),
        key,
        _entry_leaf(key),
        _entry_leaf(display_key),
        (entry.get("data") or {}).get("name") if isinstance(entry.get("data"), dict) else "",
        (entry.get("meta") or {}).get("name") if isinstance(entry.get("meta"), dict) else "",
    )
    internal_names = sorted({sanitize_datalens_internal_name(value) for value in raw_names if value})
    scope = str(entry.get("scope") or "").strip()
    entry_type = str(entry.get("type") or "").strip()
    type_source = (
        entry_type
        if scope.lower() in {"widget", "chart"} and entry_type
        else scope or entry_type
    )
    return {
        "entry_id": entry_id,
        "object_type": _normalize_object_type(type_source),
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


def _entry_leaf(value: str) -> str:
    return value.rstrip("/").rsplit("/", 1)[-1].strip() if value else ""


def _normalize_object_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"dash", "dashboard"}:
        return "dashboard"
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
