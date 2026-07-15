from __future__ import annotations

from dataclasses import dataclass
from typing import Any


GRID_COLUMNS = 36
_GEOMETRY_FIELDS = ("x", "y", "w", "h")
_FIXED_LAYOUT_PARENTS = frozenset({"__fixHead", "__fixGCont"})


@dataclass(frozen=True)
class DashboardGridIssue:
    severity: str
    rule: str
    path: str
    message: str
    object_type: str = "dashboard_layout"
    suggested_fix: str = ""


def validate_dashboard_grid(
    payload: dict[str, Any],
    *,
    current_dashboard: dict[str, Any] | None = None,
) -> list[DashboardGridIssue]:
    """Validate the native DataLens 36-column dashboard grid.

    The check is deliberately activated only for tabs that look like native
    dashboard tabs. This keeps the validator compatible with higher-level
    planning payloads whose ``items`` array contains string widget references
    rather than native dashboard item objects.
    """

    extracted = _extract_dashboard_tabs(payload)
    if extracted is None:
        return []
    tabs, tabs_path = extracted
    if not any(_looks_like_native_dashboard_tab(tab) for tab in tabs):
        return []

    current_extracted = _extract_dashboard_tabs(current_dashboard or {})
    current_tabs = current_extracted[0] if current_extracted is not None else []
    current_by_id = {
        str(tab.get("id")): tab
        for tab in current_tabs
        if isinstance(tab, dict) and str(tab.get("id") or "").strip()
    }

    issues: list[DashboardGridIssue] = []
    for tab_index, tab in enumerate(tabs):
        tab_path = f"{tabs_path}[{tab_index}]"
        if not isinstance(tab, dict):
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="malformed_dashboard_tab",
                    path=tab_path,
                    message="Dashboard tab must be an object with items/globalItems and layout arrays.",
                    suggested_fix="Emit a dashboard tab object with id, items, globalItems, and layout.",
                )
            )
            continue
        current_tab = _matching_current_tab(tab, tab_index, current_tabs, current_by_id)
        issues.extend(_validate_tab_grid(tab, tab_path=tab_path, current_tab=current_tab))
    return issues


def _looks_like_native_dashboard_tab(tab: Any) -> bool:
    if not isinstance(tab, dict):
        return False
    if "layout" in tab or "globalItems" in tab:
        return True
    raw_items = tab.get("items")
    return isinstance(raw_items, list) and any(isinstance(item, dict) for item in raw_items)


def _validate_tab_grid(
    tab: dict[str, Any],
    *,
    tab_path: str,
    current_tab: dict[str, Any] | None,
) -> list[DashboardGridIssue]:
    issues: list[DashboardGridIssue] = []
    items, item_issues = _collect_tab_items(tab, tab_path=tab_path)
    issues.extend(item_issues)

    raw_layout = tab.get("layout")
    if raw_layout is None:
        if items:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="missing_dashboard_layout",
                    path=f"{tab_path}.layout",
                    message="Tab has dashboard items but no layout array.",
                    suggested_fix="Add one layout record per items/globalItems id.",
                )
            )
        return issues
    if not isinstance(raw_layout, list):
        issues.append(
            DashboardGridIssue(
                severity="error",
                rule="malformed_dashboard_layout",
                path=f"{tab_path}.layout",
                message="Dashboard tab layout must be an array.",
                suggested_fix="Emit layout as an array of {i, x, y, w, h} objects.",
            )
        )
        return issues

    layouts, layout_issues = _collect_layout_records(raw_layout, path=f"{tab_path}.layout")
    issues.extend(layout_issues)
    issues.extend(_parent_layout_issues(layouts))

    item_ids = set(items)
    layout_ids = set(layouts)
    for item_id in sorted(item_ids - layout_ids):
        issues.append(
            DashboardGridIssue(
                severity="error",
                rule="missing_item_layout",
                path=items[item_id][1],
                message=f"Dashboard item/global item {item_id!r} has no matching layout record.",
                object_type=_height_kind(items[item_id][0]),
                suggested_fix=f"Add a layout record whose i is {item_id!r}.",
            )
        )
    for layout_id in sorted(layout_ids - item_ids):
        issues.append(
            DashboardGridIssue(
                severity="error",
                rule="orphan_layout_id",
                path=layouts[layout_id][1],
                message=f"Layout id {layout_id!r} does not match any tab item or global item.",
                suggested_fix="Remove the orphan layout record or restore the matching dashboard item.",
            )
        )

    current_overlap_pairs = _peer_overlap_pairs(current_tab or {})
    current_layouts: dict[str, tuple[dict[str, Any], str]] = {}
    raw_current_layout = (current_tab or {}).get("layout")
    if isinstance(raw_current_layout, list):
        current_layouts, _ = _collect_layout_records(raw_current_layout, path=f"{tab_path}.current_layout")
    for left_id, right_id in sorted(_peer_overlap_pairs(tab)):
        if (left_id, right_id) in current_overlap_pairs and _pair_geometry_unchanged(
            left_id,
            right_id,
            proposed_layouts=layouts,
            current_layouts=current_layouts,
        ):
            continue
        left = layouts.get(left_id)
        right = layouts.get(right_id)
        if left is None or right is None:
            continue
        issues.append(
            DashboardGridIssue(
                severity="error",
                rule="peer_layout_overlap",
                path=f"{left[1]}, {right[1]}",
                message=f"Peer dashboard items {left_id!r} and {right_id!r} overlap in the 36-column grid.",
                suggested_fix=(
                    "Move or resize one peer. Root items are compared with root siblings, while children of a "
                    "real layout parent are compared only with siblings inside that parent."
                ),
            )
        )

    issues.extend(
        _preserved_geometry_issues(
            layouts,
            current_tab=current_tab or {},
            tab_path=tab_path,
        )
    )

    for item_id in sorted(item_ids & layout_ids):
        item, item_path = items[item_id]
        layout, layout_path = layouts[item_id]
        issues.extend(_height_and_auto_height_issues(item, layout, item_path=item_path, layout_path=layout_path))
    return issues


def _collect_tab_items(
    tab: dict[str, Any],
    *,
    tab_path: str,
) -> tuple[dict[str, tuple[dict[str, Any], str]], list[DashboardGridIssue]]:
    items: dict[str, tuple[dict[str, Any], str]] = {}
    issues: list[DashboardGridIssue] = []
    for key in ("items", "globalItems"):
        raw_items = tab.get(key, [])
        if raw_items is None:
            raw_items = []
        if not isinstance(raw_items, list):
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="malformed_dashboard_items",
                    path=f"{tab_path}.{key}",
                    message=f"{key} must be an array.",
                    suggested_fix=f"Emit {key} as an array of dashboard item objects.",
                )
            )
            continue
        for index, item in enumerate(raw_items):
            item_path = f"{tab_path}.{key}[{index}]"
            if not isinstance(item, dict):
                issues.append(
                    DashboardGridIssue(
                        severity="error",
                        rule="malformed_dashboard_item",
                        path=item_path,
                        message="Dashboard item/global item must be an object with a stable id.",
                        suggested_fix="Emit an object with id, type, and data.",
                    )
                )
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                issues.append(
                    DashboardGridIssue(
                        severity="error",
                        rule="missing_dashboard_item_id",
                        path=f"{item_path}.id",
                        message="Dashboard item/global item id is missing or empty.",
                        suggested_fix="Assign a stable id and use the same value in layout.i.",
                    )
                )
                continue
            if item_id in items:
                issues.append(
                    DashboardGridIssue(
                        severity="error",
                        rule="duplicate_dashboard_item_id",
                        path=f"{items[item_id][1]}.id, {item_path}.id",
                        message=f"Dashboard item id {item_id!r} is duplicated within one tab.",
                        suggested_fix="Keep item/globalItems ids unique within each dashboard tab.",
                    )
                )
                continue
            items[item_id] = (item, item_path)
    return items, issues


def _collect_layout_records(
    raw_layout: list[Any],
    *,
    path: str,
) -> tuple[dict[str, tuple[dict[str, Any], str]], list[DashboardGridIssue]]:
    layouts: dict[str, tuple[dict[str, Any], str]] = {}
    issues: list[DashboardGridIssue] = []
    for index, layout in enumerate(raw_layout):
        layout_path = f"{path}[{index}]"
        if not isinstance(layout, dict):
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="malformed_layout_record",
                    path=layout_path,
                    message="Layout record must be an object with i, x, y, w, and h.",
                    suggested_fix="Emit a complete native DataLens grid record.",
                )
            )
            continue
        layout_id = str(layout.get("i") or "").strip()
        if not layout_id:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="missing_layout_id",
                    path=f"{layout_path}.i",
                    message="Layout record i is missing or empty.",
                    suggested_fix="Set layout.i to the matching dashboard item/global item id.",
                )
            )
        elif layout_id in layouts:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="duplicate_layout_id",
                    path=f"{layouts[layout_id][1]}.i, {layout_path}.i",
                    message=f"Layout id {layout_id!r} appears more than once in one tab.",
                    suggested_fix="Keep exactly one layout record per dashboard item/global item id.",
                )
            )
        else:
            layouts[layout_id] = (layout, layout_path)

        missing_fields = [field for field in _GEOMETRY_FIELDS if field not in layout]
        for field in missing_fields:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="missing_layout_geometry",
                    path=f"{layout_path}.{field}",
                    message=f"Layout record is missing required {field!r} geometry.",
                    suggested_fix="Provide integer x, y, w, and h values.",
                )
            )
        if missing_fields:
            continue

        for field in _GEOMETRY_FIELDS:
            value = layout.get(field)
            minimum = 1 if field in {"w", "h"} else 0
            if type(value) is not int or value < minimum:
                issues.append(
                    DashboardGridIssue(
                        severity="error",
                        rule="invalid_layout_geometry",
                        path=f"{layout_path}.{field}",
                        message=(
                            f"Layout {field} must be a {'positive' if minimum else 'nonnegative'} finite integer; "
                            f"got {value!r}."
                        ),
                        suggested_fix=f"Use an integer >= {minimum}.",
                    )
                )
        if _valid_geometry(layout) and layout["x"] + layout["w"] > GRID_COLUMNS:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="layout_exceeds_36_columns",
                    path=layout_path,
                    message=(
                        f"Layout item {layout_id!r} ends at column {layout['x'] + layout['w']}; "
                        f"the native dashboard grid has {GRID_COLUMNS} columns."
                    ),
                    suggested_fix="Reduce x or w so x + w <= 36.",
                )
            )
    return layouts, issues


def _preserved_geometry_issues(
    proposed_layouts: dict[str, tuple[dict[str, Any], str]],
    *,
    current_tab: dict[str, Any],
    tab_path: str,
) -> list[DashboardGridIssue]:
    if not current_tab:
        return []
    raw_current_layout = current_tab.get("layout")
    if not isinstance(raw_current_layout, list):
        return []
    current_layouts, _ = _collect_layout_records(raw_current_layout, path=f"{tab_path}.current_layout")
    issues: list[DashboardGridIssue] = []
    for item_id in sorted(set(proposed_layouts) & set(current_layouts)):
        proposed, proposed_path = proposed_layouts[item_id]
        current, _ = current_layouts[item_id]
        if not (_valid_geometry(proposed) and _valid_geometry(current)):
            continue
        proposed_geometry = tuple(proposed[field] for field in _GEOMETRY_FIELDS)
        current_geometry = tuple(current[field] for field in _GEOMETRY_FIELDS)
        if proposed_geometry == current_geometry:
            continue
        issues.append(
            DashboardGridIssue(
                severity="warning",
                rule="existing_layout_geometry_changed",
                path=proposed_path,
                message=(
                    f"Existing item {item_id!r} changed x/y/w/h from {current_geometry} to {proposed_geometry} "
                    "while current_dashboard preservation is active."
                ),
                suggested_fix=(
                    "Confirm the geometry change is intentional, then verify clipping, whitespace, scrollbars, "
                    "labels, and overlap in the target browser viewport."
                ),
            )
        )
    return issues


def _parent_layout_issues(
    layouts: dict[str, tuple[dict[str, Any], str]],
) -> list[DashboardGridIssue]:
    issues: list[DashboardGridIssue] = []
    parent_by_child: dict[str, str] = {}
    for child_id, (child, child_path) in layouts.items():
        parent_id = str(child.get("parent") or "").strip()
        if not parent_id or parent_id in _FIXED_LAYOUT_PARENTS:
            continue
        parent_by_child[child_id] = parent_id
        if parent_id == child_id:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="self_layout_parent",
                    path=f"{child_path}.parent",
                    message=f"Layout item {child_id!r} cannot be its own parent.",
                    suggested_fix="Remove parent or reference a real container layout id.",
                )
            )
            continue
        parent_record = layouts.get(parent_id)
        if parent_record is None:
            issues.append(
                DashboardGridIssue(
                    severity="error",
                    rule="orphan_layout_parent",
                    path=f"{child_path}.parent",
                    message=(
                        f"Layout item {child_id!r} references unknown parent {parent_id!r}; only a real layout id "
                        "or the fixed sentinels __fixHead/__fixGCont are valid."
                    ),
                    suggested_fix="Restore the parent layout, use a supported fixed sentinel, or remove parent.",
                )
            )
            continue
        parent, parent_path = parent_record
        if _valid_geometry(child) and _valid_geometry(parent):
            horizontal_overflow = child["x"] + child["w"] > parent["w"]
            vertical_overflow = child["y"] + child["h"] > parent["h"]
            if horizontal_overflow or vertical_overflow:
                issues.append(
                    DashboardGridIssue(
                        severity="error",
                        rule="child_layout_exceeds_parent_bounds",
                        path=f"{child_path}, {parent_path}",
                        message=(
                            f"Child layout {child_id!r} at ({child['x']}, {child['y']}, {child['w']}, {child['h']}) "
                            f"does not fit inside parent {parent_id!r} size ({parent['w']}, {parent['h']})."
                        ),
                        suggested_fix="Use parent-relative child geometry with x + w <= parent.w and y + h <= parent.h.",
                    )
                )

    cycles: set[tuple[str, ...]] = set()
    for start in parent_by_child:
        chain: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in parent_by_child:
            if current in positions:
                cycle = tuple(sorted(chain[positions[current] :]))
                if len(cycle) > 1:
                    cycles.add(cycle)
                break
            positions[current] = len(chain)
            chain.append(current)
            next_parent = parent_by_child[current]
            if next_parent == current or next_parent not in layouts:
                break
            current = next_parent
    for cycle in sorted(cycles):
        paths = ", ".join(f"{layouts[item_id][1]}.parent" for item_id in cycle)
        issues.append(
            DashboardGridIssue(
                severity="error",
                rule="layout_parent_cycle",
                path=paths,
                message=f"Layout parent cycle detected among {', '.join(repr(item_id) for item_id in cycle)}.",
                suggested_fix="Break the cycle so each child chain terminates at a root item or supported fixed sentinel.",
            )
        )
    return issues


def _pair_geometry_unchanged(
    left_id: str,
    right_id: str,
    *,
    proposed_layouts: dict[str, tuple[dict[str, Any], str]],
    current_layouts: dict[str, tuple[dict[str, Any], str]],
) -> bool:
    for item_id in (left_id, right_id):
        proposed = proposed_layouts.get(item_id)
        current = current_layouts.get(item_id)
        if proposed is None or current is None:
            return False
        if not (_valid_geometry(proposed[0]) and _valid_geometry(current[0])):
            return False
        if any(proposed[0][field] != current[0][field] for field in _GEOMETRY_FIELDS):
            return False
        if str(proposed[0].get("parent") or "").strip() != str(current[0].get("parent") or "").strip():
            return False
    return True


def _height_and_auto_height_issues(
    item: dict[str, Any],
    layout: dict[str, Any],
    *,
    item_path: str,
    layout_path: str,
) -> list[DashboardGridIssue]:
    if not _valid_geometry(layout):
        return []
    issues: list[DashboardGridIssue] = []
    height = layout["h"]
    kind = _height_kind(item)
    if kind == "title" and height != 2:
        issues.append(
            _height_warning(
                rule="atypical_title_height",
                path=layout_path,
                message=f"Title item height is {height}; the proven dashboard convention is h=2.",
                kind=kind,
                suggested_fix="Use h=2 for a new title, or preserve the existing live height when intentionally different.",
            )
        )
    elif kind == "control" and height not in {2, 3}:
        issues.append(
            _height_warning(
                rule="atypical_control_height",
                path=layout_path,
                message=f"Control item height is {height}; compact native controls are commonly h=2 or h=3.",
                kind=kind,
                suggested_fix="Review row wrapping and measured runtime height before keeping a taller control slot.",
            )
        )
    elif kind == "kpi" and height != 6:
        issues.append(
            _height_warning(
                rule="atypical_kpi_height",
                path=layout_path,
                message=f"KPI/metric item height is {height}; h=6 is the dominant native KPI reference size.",
                kind=kind,
                suggested_fix="Use h=6 as the starting point, then verify the real title/value rendering at mounted size.",
            )
        )
    elif kind == "table" and height < 10:
        issues.append(
            _height_warning(
                rule="atypical_table_height",
                path=layout_path,
                message=f"Table item height is {height}; dashboard tables generally need a larger slot than h=9.",
                kind=kind,
                suggested_fix="Increase the table slot or prove the compact row count/pagination in runtime QA.",
            )
        )

    auto_height_values, invalid_paths = _auto_height_values(item, item_path=item_path)
    for invalid_path in invalid_paths:
        issues.append(
            DashboardGridIssue(
                severity="warning",
                rule="invalid_auto_height_value",
                path=invalid_path,
                message="autoHeight is present but is not boolean; DataLens may normalize or ignore it.",
                object_type=kind,
                suggested_fix="Use true/false or omit autoHeight and preserve the measured live grid height.",
            )
        )
    if auto_height_values == {True, False}:
        issues.append(
            DashboardGridIssue(
                severity="warning",
                rule="mixed_widget_auto_height",
                path=item_path,
                message="One dashboard item mixes autoHeight=true and autoHeight=false across its item/inner tabs.",
                object_type=kind,
                suggested_fix="Use one intentional autoHeight policy per mounted item and verify its fixed grid h in readback/runtime.",
            )
        )
    if True in auto_height_values and height > 30 and kind not in {"table"}:
        issues.append(
            DashboardGridIssue(
                severity="warning",
                rule="auto_height_large_fixed_slot",
                path=layout_path,
                message=f"autoHeight=true is paired with a very tall fixed slot h={height}.",
                object_type=kind,
                suggested_fix="Confirm that the large fixed slot is intentional and not compensating for clipped content.",
            )
        )
    return issues


def _height_warning(
    *,
    rule: str,
    path: str,
    message: str,
    kind: str,
    suggested_fix: str,
) -> DashboardGridIssue:
    return DashboardGridIssue(
        severity="warning",
        rule=rule,
        path=path,
        message=message,
        object_type=kind,
        suggested_fix=suggested_fix,
    )


def _height_kind(item: dict[str, Any]) -> str:
    raw_type = str(item.get("type") or item.get("entry_type") or "").lower()
    if raw_type == "title":
        return "title"
    if "control" in raw_type or "selector" in raw_type:
        return "control"
    text = _joined_item_text(item).lower()
    if "table" in raw_type or "table" in text:
        return "table"
    if any(token in text for token in ("kpi", "metric", "indicator")):
        return "kpi"
    return "widget"


def _joined_item_text(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"id", "type", "entry_type", "title", "name", "visualization", "tabs", "data"}:
                parts.append(_joined_item_text(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_joined_item_text(item))
    elif isinstance(value, str):
        parts.append(value)
    return " ".join(parts)


def _auto_height_values(item: dict[str, Any], *, item_path: str) -> tuple[set[bool], list[str]]:
    values: set[bool] = set()
    invalid_paths: list[str] = []

    def collect(value: dict[str, Any], path: str) -> None:
        for key in ("autoHeight", "auto_height"):
            if key not in value:
                continue
            raw = value[key]
            if type(raw) is bool:
                values.add(raw)
            else:
                invalid_paths.append(f"{path}.{key}")

    collect(item, item_path)
    data = item.get("data")
    if isinstance(data, dict):
        collect(data, f"{item_path}.data")
        tabs = data.get("tabs")
        if isinstance(tabs, list):
            for index, tab in enumerate(tabs):
                if isinstance(tab, dict):
                    collect(tab, f"{item_path}.data.tabs[{index}]")
    return values, invalid_paths


def _peer_overlap_pairs(tab: dict[str, Any]) -> set[tuple[str, str]]:
    raw_layout = tab.get("layout")
    if not isinstance(raw_layout, list):
        return set()
    valid_layout_ids = {
        str(layout.get("i") or "").strip()
        for layout in raw_layout
        if isinstance(layout, dict) and str(layout.get("i") or "").strip()
    }
    peer_groups: dict[str, list[dict[str, Any]]] = {}
    for layout in raw_layout:
        if not isinstance(layout, dict) or not str(layout.get("i") or "").strip() or not _valid_geometry(layout):
            continue
        parent_id = str(layout.get("parent") or "").strip()
        if parent_id in _FIXED_LAYOUT_PARENTS:
            continue
        if parent_id and parent_id not in valid_layout_ids:
            continue
        peer_groups.setdefault(parent_id or "__root__", []).append(layout)
    pairs: set[tuple[str, str]] = set()
    for peers in peer_groups.values():
        for left_index, left in enumerate(peers):
            for right in peers[left_index + 1 :]:
                left_id = str(left["i"])
                right_id = str(right["i"])
                if left_id == right_id or not _rectangles_overlap(left, right):
                    continue
                pairs.add(tuple(sorted((left_id, right_id))))
    return pairs


def _rectangles_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["x"] < right["x"] + right["w"]
        and right["x"] < left["x"] + left["w"]
        and left["y"] < right["y"] + right["h"]
        and right["y"] < left["y"] + left["h"]
    )


def _valid_geometry(layout: dict[str, Any]) -> bool:
    return all(
        field in layout
        and type(layout[field]) is int
        and layout[field] >= (1 if field in {"w", "h"} else 0)
        for field in _GEOMETRY_FIELDS
    )


def _extract_dashboard_tabs(payload: dict[str, Any]) -> tuple[list[Any], str] | None:
    entry = payload.get("entry")
    if isinstance(entry, dict):
        data = entry.get("data")
        if isinstance(data, dict) and isinstance(data.get("tabs"), list):
            return data["tabs"], "$.entry.data.tabs"
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("tabs"), list):
        return data["tabs"], "$.data.tabs"
    if isinstance(payload.get("tabs"), list):
        return payload["tabs"], "$.tabs"
    return None


def _matching_current_tab(
    proposed_tab: dict[str, Any],
    tab_index: int,
    current_tabs: list[Any],
    current_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    tab_id = str(proposed_tab.get("id") or "").strip()
    if tab_id and tab_id in current_by_id:
        return current_by_id[tab_id]
    if tab_index < len(current_tabs) and isinstance(current_tabs[tab_index], dict):
        return current_tabs[tab_index]
    return None
