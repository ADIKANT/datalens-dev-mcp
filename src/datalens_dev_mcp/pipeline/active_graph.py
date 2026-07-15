from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


EntryRole = Literal["active_on_requested_tab", "active_elsewhere", "shared_dependency", "dormant", "unknown"]


@dataclass(frozen=True)
class ActiveGraphEntry:
    entry_id: str
    role: EntryRole
    hydrated: bool
    entry_type: str = ""
    referenced_by: list[str] = field(default_factory=list)
    write_scope: str = "blocked_until_classified"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_active_dashboard_graph(
    *,
    dashboard: dict[str, Any],
    workbook_entries: list[dict[str, Any]] | None = None,
    dashboard_id: str = "",
    workbook_id: str = "",
    requested_tab: str = "",
    saved_rev: str = "",
    published_rev: str = "",
) -> dict[str, Any]:
    entries_by_id = {_entry_id(entry): entry for entry in workbook_entries or [] if _entry_id(entry)}
    requested_items, other_items = _split_dashboard_items(dashboard, requested_tab=requested_tab)
    active_refs = _collect_references(requested_items)
    other_refs = _collect_references(other_items)
    shared_refs = _collect_external_control_references(requested_items)
    all_ids = set(entries_by_id) | set(active_refs) | set(other_refs) | set(shared_refs)
    rows: list[ActiveGraphEntry] = []
    for entry_id in sorted(all_ids):
        referenced_by = active_refs.get(entry_id, []) + other_refs.get(entry_id, []) + shared_refs.get(entry_id, [])
        if entry_id in shared_refs:
            role: EntryRole = "shared_dependency"
            write_scope = "allowed_if_backward_compatible"
        elif entry_id in active_refs:
            role = "active_on_requested_tab"
            write_scope = "allowed_if_in_scope"
        elif entry_id in other_refs:
            role = "active_elsewhere"
            write_scope = "requires_cross_tab_compatibility"
        elif entry_id in entries_by_id:
            role = "dormant"
            write_scope = "excluded"
        else:
            role = "unknown"
            write_scope = "blocked_until_hydrated"
        rows.append(
            ActiveGraphEntry(
                entry_id=entry_id,
                entry_type=_entry_type(entries_by_id.get(entry_id, {})),
                role=role,
                referenced_by=sorted(set(referenced_by)),
                hydrated=entry_id in entries_by_id,
                write_scope=write_scope,
            )
        )
    return {
        "schema_version": "datalens.active-dashboard-graph.v1",
        "dashboard_id": dashboard_id or str(dashboard.get("dashboardId") or dashboard.get("entryId") or ""),
        "workbook_id": workbook_id or str(dashboard.get("workbookId") or ""),
        "requested_tab": requested_tab,
        "branch_pair": {"saved_rev": saved_rev, "published_rev": published_rev, "same": bool(saved_rev and saved_rev == published_rev)},
        "entries": [row.to_dict() for row in rows],
        "blocked_reasons": [f"unhydrated_active_dependency:{row.entry_id}" for row in rows if row.role != "dormant" and not row.hydrated],
    }


def _split_dashboard_items(dashboard: dict[str, Any], *, requested_tab: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tabs = dashboard.get("tabs") or dashboard.get("dashboardTabs") or []
    if not isinstance(tabs, list) or not tabs:
        items = _items_from_container(dashboard)
        return items, []
    requested: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        tab_id = str(tab.get("id") or tab.get("tabId") or tab.get("key") or "")
        target = requested if not requested_tab or tab_id == requested_tab else other
        target.extend(_items_from_container(tab))
    return requested, other


def _items_from_container(container: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key in ("items", "widgets", "controls", "blocks"):
        raw = container.get(key)
        if isinstance(raw, list):
            result.extend(item for item in raw if isinstance(item, dict))
    return result


def _collect_references(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for item in items:
        owner = _item_label(item)
        for key in ("entryId", "entry_id", "chartId", "chart_id", "targetEntryId", "target_entry_id"):
            value = str(item.get(key) or "").strip()
            if value:
                refs.setdefault(value, []).append(owner)
        for tab in item.get("tabs") or []:
            if isinstance(tab, dict):
                value = str(tab.get("chartId") or tab.get("entryId") or "").strip()
                if value:
                    refs.setdefault(value, []).append(f"{owner}:tab:{tab.get('id') or tab.get('tabId') or ''}")
    return refs


def _collect_external_control_references(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for item in items:
        item_type = str(item.get("type") or item.get("entry_type") or "").lower()
        if "control" not in item_type and "selector" not in item_type:
            continue
        owner = _item_label(item)
        for key in (
            "external_entry_id",
            "externalEntryId",
            "sourceEntryId",
            "source_entry_id",
            "controlEntryId",
            "control_entry_id",
            "selectorEntryId",
            "selector_entry_id",
        ):
            value = str(item.get(key) or "").strip()
            if value:
                refs.setdefault(value, []).append(owner)
    return refs


def _item_label(item: dict[str, Any]) -> str:
    item_id = str(item.get("id") or item.get("itemId") or item.get("controlId") or item.get("entryId") or "item")
    item_type = str(item.get("type") or item.get("entry_type") or "item")
    return f"{item_type}:{item_id}"


def _entry_id(entry: dict[str, Any]) -> str:
    nested = entry.get("entry") if isinstance(entry.get("entry"), dict) else {}
    return str(entry.get("entryId") or entry.get("id") or nested.get("entryId") or nested.get("id") or "").strip()


def _entry_type(entry: dict[str, Any]) -> str:
    nested = entry.get("entry") if isinstance(entry.get("entry"), dict) else {}
    return str(entry.get("type") or entry.get("entry_type") or entry.get("scope") or nested.get("scope") or "")

