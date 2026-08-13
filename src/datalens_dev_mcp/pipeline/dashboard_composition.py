from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from datalens_dev_mcp.editor.render_contract import canonical_sha256
from datalens_dev_mcp.editor.title_contract import TITLE_MODES, looks_technical_title
from datalens_dev_mcp.validators.datalens_names import sanitize_datalens_internal_name


COMPOSITION_SCHEMA_ID = "dashboard_composition"
GRID_COLUMNS = 36
SELECTOR_ROW_WIDTH_PERCENT = 94
KPI_FAMILIES = frozenset(
    {
        "kpi_value_only",
        "kpi_value_delta",
        "kpi_value_sparkline",
        "kpi_value_delta_sparkline",
    }
)
SPARKLINE_KPI_FAMILIES = frozenset(
    {"kpi_value_sparkline", "kpi_value_delta_sparkline"}
)
TABLE_FAMILIES = frozenset({"table_node", "pivot_table", "table_drilldown"})
SELECTOR_FAMILIES = frozenset(
    {
        "date_range_selector",
        "dynamic_selector",
        "selector_family_dynamic",
        "single_select_dropdown",
        "multi_select_dropdown",
        "search_selector",
        "selector_family_static",
        "selector_group",
    }
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class DashboardCompositionError(ValueError):
    pass


def build_dashboard_composition(
    components: list[dict[str, Any]],
    *,
    requested: dict[str, Any] | None = None,
    dashboard_id: str = "dashboard_target",
    dashboard_title: str = "Dashboard",
) -> dict[str, Any]:
    """Build and validate the hash-bound 36-column dashboard composition."""

    normalized_components = _normalize_components(components)
    component_by_id = {item["widget_id"]: item for item in normalized_components}
    if requested is None:
        tabs = _automatic_tabs(normalized_components)
        selection_origin = "safe_defaults"
    else:
        if not isinstance(requested, dict):
            raise DashboardCompositionError("dashboard_composition must be an object")
        tabs = _normalize_requested_tabs(requested, component_by_id)
        selection_origin = "explicit_contract"

    composition: dict[str, Any] = {
        "schema_id": COMPOSITION_SCHEMA_ID,
        "operation": str((requested or {}).get("operation") or "create"),
        "dashboard_id": str((requested or {}).get("dashboard_id") or dashboard_id),
        "dashboard_title": str((requested or {}).get("dashboard_title") or dashboard_title),
        "dashboard_internal_name": str(
            (requested or {}).get("dashboard_internal_name")
            or sanitize_datalens_internal_name(
                str((requested or {}).get("dashboard_title") or dashboard_title)
            )
        ),
        "workbook_id": str((requested or {}).get("workbook_id") or "workbook_target"),
        "grid_columns": GRID_COLUMNS,
        "selection_origin": selection_origin,
        "defaults": {
            "selector_row_width_percent": SELECTOR_ROW_WIDTH_PERCENT,
            "gap_after": 0,
            "max_standard_kpis_per_row": 3,
            "sparkline_kpi": {"w": 12, "h": 8},
            "compact_kpi": {"w": 12, "h": 6},
        },
        "tabs": tabs,
    }
    composition["mounts"] = _mounts(tabs)
    composition["payload_skeleton"] = _payload_skeleton(composition)
    composition["payload_skeleton_sha256"] = canonical_sha256(
        composition["payload_skeleton"]
    )
    issues = validate_dashboard_composition(composition, components=normalized_components)
    composition["validation"] = {"ok": not issues, "issues": issues}
    composition["sha256"] = canonical_sha256(
        {
            key: value
            for key, value in composition.items()
            if key not in {"sha256", "validation"}
        }
    )
    if issues:
        raise DashboardCompositionError("invalid dashboard composition: " + "; ".join(issues))
    return composition


def validate_dashboard_composition(
    composition: dict[str, Any],
    *,
    components: list[dict[str, Any]] | None = None,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(composition, dict):
        return ["dashboard_composition must be an object"]
    if composition.get("schema_id") != COMPOSITION_SCHEMA_ID:
        issues.append(f"schema_id must be {COMPOSITION_SCHEMA_ID}")
    if composition.get("operation") not in {"create", "update"}:
        issues.append("dashboard_composition.operation must be create or update")
    if sanitize_datalens_internal_name(str(composition.get("dashboard_internal_name") or "")) != composition.get(
        "dashboard_internal_name"
    ):
        issues.append("dashboard_internal_name must be a safe lowercase DataLens name")
    if composition.get("grid_columns") != GRID_COLUMNS:
        issues.append(f"grid_columns must be {GRID_COLUMNS}")
    tabs = composition.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        issues.append("tabs must be a non-empty array")
        return issues

    component_by_id = {
        str(item.get("widget_id") or ""): item
        for item in (components or [])
        if isinstance(item, dict)
    }
    mounted: list[str] = []
    tab_ids: set[str] = set()
    for tab_index, tab in enumerate(tabs):
        tab_path = f"tabs[{tab_index}]"
        if not isinstance(tab, dict):
            issues.append(f"{tab_path} must be an object")
            continue
        tab_id = str(tab.get("id") or "").strip()
        if not tab_id:
            issues.append(f"{tab_path}.id is required")
        elif tab_id in tab_ids:
            issues.append(f"duplicate tab id {tab_id}")
        tab_ids.add(tab_id)
        if not str(tab.get("title") or "").strip():
            issues.append(f"{tab_path}.title is required")
        rows = tab.get("rows")
        if not isinstance(rows, list) or not rows:
            issues.append(f"{tab_path}.rows must be a non-empty array")
            continue
        expected_y = 0
        for row_index, row in enumerate(rows):
            row_path = f"{tab_path}.rows[{row_index}]"
            if not isinstance(row, dict):
                issues.append(f"{row_path} must be an object")
                continue
            row_y = row.get("y")
            if row_y != expected_y:
                issues.append(f"{row_path}.y must be {expected_y}; undeclared vertical gaps are forbidden")
            items = row.get("items")
            if not isinstance(items, list) or not items:
                issues.append(f"{row_path}.items must be a non-empty array")
                continue
            heights: set[int] = set()
            width_total = 0
            kpi_count = 0
            cursor_x = 0
            four_kpi_override = bool(
                row.get("density_override") == "four_kpi_9_columns"
                and _valid_four_kpi_browser_proof(row.get("browser_proof"))
            )
            row_widget_ids: set[str] = set()
            row_items_by_id: dict[str, dict[str, Any]] = {}
            for item_index, item in enumerate(items):
                item_path = f"{row_path}.items[{item_index}]"
                if not isinstance(item, dict):
                    issues.append(f"{item_path} must be an object")
                    continue
                widget_id = str(item.get("widget_id") or "").strip()
                if not widget_id:
                    issues.append(f"{item_path}.widget_id is required")
                    continue
                mounted.append(widget_id)
                row_widget_ids.add(widget_id)
                row_items_by_id[widget_id] = item
                if item.get("x") != cursor_x:
                    issues.append(f"{item_path}.x must be {cursor_x}")
                width = item.get("w")
                height = item.get("h")
                if not isinstance(width, int) or isinstance(width, bool) or not 1 <= width <= GRID_COLUMNS:
                    issues.append(f"{item_path}.w must be an integer from 1 to {GRID_COLUMNS}")
                    width = 0
                if not isinstance(height, int) or isinstance(height, bool) or height < 1:
                    issues.append(f"{item_path}.h must be a positive integer")
                else:
                    heights.add(height)
                cursor_x += width
                width_total += width

                component = component_by_id.get(widget_id, {})
                family = str(item.get("family") or component.get("family") or "")
                if family in KPI_FAMILIES:
                    kpi_count += 1
                    expected_height = 8 if family in SPARKLINE_KPI_FAMILIES else 6
                    expected_width = 9 if four_kpi_override else 12
                    if item.get("w") != expected_width or item.get("h") != expected_height:
                        issues.append(
                            f"{item_path}: standard {family} geometry must be {expected_width}x{expected_height}"
                        )
                issues.extend(_title_issues(item, component, item_path))
                issues.extend(_selector_issues(item, component, item_path))
                issues.extend(_table_issues(item, component, item_path))
                issues.extend(_comparison_context_issues(item, component, item_path))
            if width_total > GRID_COLUMNS:
                issues.append(f"{row_path}: width total {width_total} exceeds {GRID_COLUMNS}")
            if len(heights) > 1:
                issues.append(f"{row_path}: adjacent blocks must have identical heights")
            if kpi_count > 3:
                override = row.get("density_override")
                proof = row.get("browser_proof")
                if override != "four_kpi_9_columns" or not _valid_four_kpi_browser_proof(proof):
                    issues.append(f"{row_path}: more than three KPI requires explicit override and browser proof")
                elif any(item.get("w") != 9 for item in items):
                    issues.append(f"{row_path}: four-KPI override requires width 9 for every item")
            for item_index, item in enumerate(items):
                auxiliary_for = str(item.get("auxiliary_for") or "").strip()
                if not auxiliary_for:
                    continue
                item_path = f"{row_path}.items[{item_index}]"
                target = row_items_by_id.get(auxiliary_for)
                if auxiliary_for not in row_widget_ids or target is None:
                    issues.append(f"{item_path}.auxiliary_for must reference a selector in the same row")
                elif target.get("role") != "selector":
                    issues.append(f"{item_path}.auxiliary_for must reference a selector")
                elif item.get("y") != target.get("y") or item.get("h") != target.get("h"):
                    issues.append(f"{item_path}: selector auxiliary must share height and vertical alignment")
            gap_after = row.get("gap_after", 0)
            if not isinstance(gap_after, int) or isinstance(gap_after, bool) or gap_after < 0:
                issues.append(f"{row_path}.gap_after must be a non-negative integer")
                gap_after = 0
            if gap_after and row.get("spacer_declared") is not True:
                issues.append(f"{row_path}: non-zero gap_after requires spacer_declared=true")
            expected_y += (max(heights) if heights else 0) + gap_after

    if len(mounted) != len(set(mounted)):
        issues.append("each widget must be mounted exactly once")
    if component_by_id:
        expected = set(component_by_id)
        actual = set(mounted)
        if expected != actual:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            if missing:
                issues.append("composition is missing widgets: " + ", ".join(missing))
            if extra:
                issues.append("composition contains unknown widgets: " + ", ".join(extra))
    mounts = composition.get("mounts")
    if isinstance(mounts, list) and mounts != _mounts(tabs):
        issues.append("mount -> tab -> widget relationships are stale")
    if "sha256" in composition:
        expected_sha = canonical_sha256(
            {key: value for key, value in composition.items() if key not in {"sha256", "validation"}}
        )
        if composition.get("sha256") != expected_sha:
            issues.append("dashboard composition hash is stale")
    return issues


def _normalize_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(components, list) or not components:
        raise DashboardCompositionError("at least one generated component is required")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(components):
        if not isinstance(raw, dict):
            raise DashboardCompositionError(f"components[{index}] must be an object")
        item = deepcopy(raw)
        widget_id = str(item.get("widget_id") or "").strip()
        if not widget_id:
            raise DashboardCompositionError(f"components[{index}].widget_id is required")
        if widget_id in seen:
            raise DashboardCompositionError(f"duplicate widget_id {widget_id}")
        if item.get("ok") is False:
            raise DashboardCompositionError(f"component {widget_id} is not ready")
        seen.add(widget_id)
        item["widget_id"] = widget_id
        normalized.append(item)
    return normalized


def _automatic_tabs(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_role = ""
    for component in components:
        role = _role(component)
        if role == "kpi":
            can_join = current_role == role and len(current) < 3
        elif role == "chart":
            can_join = current_role == role and len(current) < 2
        else:
            can_join = current_role == role and role == "selector" and len(current) < 2
        if current and not can_join:
            buckets.append(current)
            current = []
        current.append(component)
        current_role = role
    if current:
        buckets.append(current)
    rows: list[dict[str, Any]] = []
    y = 0
    for index, bucket in enumerate(buckets):
        role = _role(bucket[0])
        width = GRID_COLUMNS // len(bucket)
        remainder = GRID_COLUMNS - width * len(bucket)
        items: list[dict[str, Any]] = []
        x = 0
        row_height = max(_default_height(item) for item in bucket)
        for item_index, component in enumerate(bucket):
            item_width = width + (1 if item_index < remainder else 0)
            if role == "kpi":
                item_width = 12
                row_height = _default_height(component)
            mounted = _mount_item(component, x=x, y=y, w=item_width, h=row_height)
            items.append(mounted)
            x += item_width
        rows.append(
            {
                "id": f"row_{index + 1}",
                "role": role,
                "y": y,
                "gap_after": 0,
                "items": items,
            }
        )
        y += row_height
    return [{"id": "main", "title": "Main", "rows": rows}]


def _normalize_requested_tabs(
    requested: dict[str, Any],
    components: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_tabs = requested.get("tabs")
    if not isinstance(raw_tabs, list) or not raw_tabs:
        raise DashboardCompositionError("dashboard_composition.tabs must be a non-empty array")
    tabs: list[dict[str, Any]] = []
    for tab_index, raw_tab in enumerate(raw_tabs):
        if not isinstance(raw_tab, dict):
            raise DashboardCompositionError(f"tabs[{tab_index}] must be an object")
        rows: list[dict[str, Any]] = []
        y = 0
        for row_index, raw_row in enumerate(raw_tab.get("rows") or []):
            if not isinstance(raw_row, dict):
                raise DashboardCompositionError(f"tabs[{tab_index}].rows[{row_index}] must be an object")
            raw_items = raw_row.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raise DashboardCompositionError(f"tabs[{tab_index}].rows[{row_index}].items is required")
            item_count = len(raw_items)
            default_width = GRID_COLUMNS // item_count
            x = 0
            preliminary: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for raw_item in raw_items:
                declaration = {"widget_id": raw_item} if isinstance(raw_item, str) else deepcopy(raw_item)
                if not isinstance(declaration, dict):
                    raise DashboardCompositionError("composition row item must be a widget id or object")
                widget_id = str(declaration.get("widget_id") or "").strip()
                component = components.get(widget_id)
                if component is None:
                    raise DashboardCompositionError(f"composition references unknown widget {widget_id!r}")
                preliminary.append((declaration, component))
            row_height = int(raw_row.get("h") or max(_default_height(item) for _, item in preliminary))
            items: list[dict[str, Any]] = []
            for item_index, (declaration, component) in enumerate(preliminary):
                family = str(component.get("family") or "")
                if declaration.get("w") is not None:
                    width = int(declaration["w"])
                elif family in KPI_FAMILIES:
                    width = 9 if raw_row.get("density_override") == "four_kpi_9_columns" else 12
                else:
                    width = default_width + (1 if item_index < GRID_COLUMNS % item_count else 0)
                height = int(declaration.get("h") or row_height)
                mounted = _mount_item(component, x=x, y=y, w=width, h=height)
                for key in (
                    "table_contract",
                    "selector_group",
                    "auxiliary_for",
                    "chart_id",
                    "widget_tabs",
                    "native_metadata",
                ):
                    if key in declaration:
                        mounted[key] = deepcopy(declaration[key])
                items.append(mounted)
                x += width
            gap_after = int(raw_row.get("gap_after", 0))
            row = {
                "id": str(raw_row.get("id") or f"row_{row_index + 1}"),
                "role": str(raw_row.get("role") or _role(preliminary[0][1])),
                "y": y,
                "gap_after": gap_after,
                "items": items,
            }
            for key in ("spacer_declared", "density_override", "browser_proof"):
                if key in raw_row:
                    row[key] = deepcopy(raw_row[key])
            rows.append(row)
            y += row_height + gap_after
        tabs.append(
            {
                "id": str(raw_tab.get("id") or f"tab_{tab_index + 1}"),
                "title": str(raw_tab.get("title") or "").strip(),
                "rows": rows,
            }
        )
    return tabs


def _mount_item(component: dict[str, Any], *, x: int, y: int, w: int, h: int) -> dict[str, Any]:
    title_contract = (
        component.get("title_contract")
        if isinstance(component.get("title_contract"), dict)
        else {}
    )
    native_metadata = (
        title_contract.get("native_metadata")
        if isinstance(title_contract.get("native_metadata"), dict)
        else component.get("native_metadata")
        if isinstance(component.get("native_metadata"), dict)
        else {}
    )
    item = {
        "widget_id": component["widget_id"],
        "role": _role(component),
        "route": str(component.get("route") or ""),
        "family": str(component.get("family") or ""),
        "display_title": str(component.get("display_title") or ""),
        "title_mode": str(component.get("title_mode") or "native_title"),
        "title_contract_sha256": str(component.get("title_contract_sha256") or ""),
        "native_metadata": {
            "title": str(native_metadata.get("title") or component.get("display_title") or ""),
            "hint": str(native_metadata.get("hint") or ""),
            "hideTitle": bool(
                native_metadata.get(
                    "hideTitle",
                    str(component.get("title_mode") or "native_title")
                    not in {"native_title", "tab_strip"},
                )
            ),
            "enableHint": bool(native_metadata.get("enableHint", False)),
        },
        "x": x,
        "y": y,
        "w": w,
        "h": h,
    }
    for key in (
        "selector_contract",
        "table_contract",
        "protected_renderer_identity",
        "comparison_context",
        "widget_tabs",
    ):
        if isinstance(component.get(key), dict):
            item[key] = deepcopy(component[key])
        elif key == "widget_tabs" and isinstance(component.get(key), list):
            item[key] = deepcopy(component[key])
    if str(component.get("chart_id") or "").strip():
        item["chart_id"] = str(component["chart_id"]).strip()
    return item


def _role(component: dict[str, Any]) -> str:
    family = str(component.get("family") or "")
    if family in KPI_FAMILIES:
        return "kpi"
    if family in SELECTOR_FAMILIES:
        return "selector"
    if family == "md_methodology_block":
        return "comparison_context"
    if family in TABLE_FAMILIES:
        return "table"
    return "chart"


def _default_height(component: dict[str, Any]) -> int:
    family = str(component.get("family") or "")
    if family in SPARKLINE_KPI_FAMILIES:
        return 8
    if family in KPI_FAMILIES:
        return 6
    if family == "selector_group":
        contract = component.get("selector_contract") if isinstance(component.get("selector_contract"), dict) else {}
        rows = contract.get("rows") if isinstance(contract.get("rows"), list) else []
        return 3 if len(rows) == 2 else 2
    if family in SELECTOR_FAMILIES:
        return 2
    if family == "md_methodology_block":
        context = component.get("comparison_context") if isinstance(component.get("comparison_context"), dict) else {}
        return min(3, max(1, int(context.get("line_count") or 3)))
    if family in TABLE_FAMILIES:
        return 15
    return 14


def _title_issues(item: dict[str, Any], component: dict[str, Any], path: str) -> list[str]:
    issues: list[str] = []
    mode = str(item.get("title_mode") or "")
    if mode not in TITLE_MODES:
        issues.append(f"{path}.title_mode must be a registered title mode")
    if component:
        if item.get("route") != component.get("route"):
            issues.append(f"{path}.route differs from the generated route")
        if str(component.get("title_mode") or "native_title") != mode:
            issues.append(f"{path}.title_mode differs from the generated title contract")
        if str(component.get("display_title") or "") != str(item.get("display_title") or ""):
            issues.append(f"{path}.display_title differs from the generated title contract")
    title = str(item.get("display_title") or "")
    if mode != "tab_only" and not title:
        issues.append(f"{path}.display_title is required")
    if looks_technical_title(title):
        issues.append(f"{path}.display_title looks like a technical object id")
    native_metadata = item.get("native_metadata") if isinstance(item.get("native_metadata"), dict) else {}
    expected_hidden = mode not in {"native_title", "tab_strip"}
    if native_metadata.get("hideTitle") is not expected_hidden:
        issues.append(f"{path}.native_metadata.hideTitle conflicts with title_mode")
    if expected_hidden and native_metadata.get("enableHint") is True:
        issues.append(f"{path}: native hint is forbidden when runtime owns title chrome")
    widget_tabs = item.get("widget_tabs") if isinstance(item.get("widget_tabs"), list) else []
    if mode == "tab_strip" and len(widget_tabs) < 2:
        issues.append(f"{path}: tab_strip requires at least two declared widget_tabs")
    return issues


def _selector_issues(item: dict[str, Any], component: dict[str, Any], path: str) -> list[str]:
    family = str(item.get("family") or component.get("family") or "")
    if family not in SELECTOR_FAMILIES:
        return []
    issues: list[str] = []
    contract = (
        item.get("selector_contract")
        if isinstance(item.get("selector_contract"), dict)
        else component.get("selector_contract")
        if isinstance(component.get("selector_contract"), dict)
        else {}
    )
    if not contract:
        return [f"{path}: selector_contract is required"]
    if contract.get("ok") is not True:
        issues.append(f"{path}: selector_contract must be valid")
    if family != "selector_group":
        if item.get("h") != 2:
            issues.append(f"{path}: single selector height must be 2")
        return issues
    if contract:
        controls = contract.get("controls") if isinstance(contract.get("controls"), list) else []
        rows = contract.get("rows") if isinstance(contract.get("rows"), list) else []
        if not controls:
            issues.append(f"{path}: selector controls are required")
        if len(rows) not in {1, 2}:
            issues.append(f"{path}: selector_group must contain one or two rows")
        if controls and any(control.get("labelPlacement") != "left" for control in controls if isinstance(control, dict)):
            issues.append(f"{path}: selector labels must be left-aligned")
        if controls and any(control.get("updateOnChange") is not True for control in controls if isinstance(control, dict)):
            issues.append(f"{path}: selectors must apply immediately")
        if contract.get("showApplyButton") is not False:
            issues.append(f"{path}: selector Apply button must be disabled")
        for row_index, row in enumerate(rows):
            row_controls = row.get("controls") if isinstance(row, dict) and isinstance(row.get("controls"), list) else []
            total = sum(
                int(str(control.get("width") or "0").removesuffix("%"))
                for control in row_controls
                if isinstance(control, dict)
                and str(control.get("width") or "").removesuffix("%").isdigit()
            )
            if total != SELECTOR_ROW_WIDTH_PERCENT:
                issues.append(f"{path}.selector_row[{row_index}] must total exactly 94%")
        expected_height = 3 if len(rows) == 2 else 2
        if item.get("h") != expected_height:
            issues.append(f"{path}: selector height must be {expected_height}")
        for control in controls:
            if not isinstance(control, dict):
                continue
            if control.get("multiple") and control.get("emptyMeansAll") is not True:
                issues.append(f"{path}: blank multiselect must mean all values")
            if control.get("multiple") and control.get("restoreDefaultAfterClear") is not False:
                issues.append(f"{path}: Clear must not repopulate a multiselect")
    return issues


def _comparison_context_issues(
    item: dict[str, Any],
    component: dict[str, Any],
    path: str,
) -> list[str]:
    if str(item.get("role") or _role(component)) != "comparison_context":
        return []
    context = (
        item.get("comparison_context")
        if isinstance(item.get("comparison_context"), dict)
        else component.get("comparison_context")
        if isinstance(component.get("comparison_context"), dict)
        else {}
    )
    line_count = int(context.get("line_count") or 3)
    expected_height = min(3, max(1, line_count))
    return (
        []
        if item.get("h") == expected_height
        else [f"{path}: comparison context height must be {expected_height} for {line_count} lines"]
    )


def _valid_four_kpi_browser_proof(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("passed") is not True:
        return False
    widths = sorted(
        item
        for item in value.get("viewport_widths") or []
        if isinstance(item, int) and not isinstance(item, bool)
    )
    return widths == [720, 1200, 1440] and bool(
        _SHA256_RE.fullmatch(str(value.get("artifact_sha256") or ""))
    )


def _table_issues(item: dict[str, Any], component: dict[str, Any], path: str) -> list[str]:
    family = str(item.get("family") or component.get("family") or "")
    if family not in TABLE_FAMILIES:
        return []
    contract = (
        item.get("table_contract")
        if isinstance(item.get("table_contract"), dict)
        else component.get("table_contract")
        if isinstance(component.get("table_contract"), dict)
        else {}
    )
    issues: list[str] = []
    if contract.get("sticky_column_kind") == "constant":
        issues.append(f"{path}: a constant column cannot be sticky")
    for index, group in enumerate(contract.get("header_groups") or []):
        if isinstance(group, dict) and not str(group.get("title") or "").strip():
            issues.append(f"{path}.header_groups[{index}]: empty grouped header is forbidden")
    for index, column in enumerate(contract.get("columns") or []):
        if not isinstance(column, dict):
            continue
        if column.get("label_clipped") is True and not str(column.get("display_label") or "").strip():
            issues.append(f"{path}.columns[{index}]: clipped label requires display_label")
    return issues


def _mounts(tabs: list[dict[str, Any]]) -> list[dict[str, str]]:
    mounts: list[dict[str, str]] = []
    for tab in tabs:
        for row in tab.get("rows") or []:
            for item in row.get("items") or []:
                mounts.append(
                    {
                        "mount_id": f"{tab.get('id')}:{item.get('widget_id')}",
                        "tab_id": str(tab.get("id") or ""),
                        "widget_id": str(item.get("widget_id") or ""),
                    }
                )
    return mounts


def _payload_skeleton(composition: dict[str, Any]) -> dict[str, Any]:
    data = {
        "counter": 1,
        "salt": "standard-dashboard",
        "schemeVersion": 8,
        "settings": {},
        "tabs": [
            {
                "id": tab["id"],
                "title": tab["title"],
                "connections": [],
                "aliases": {},
                "globalItems": [],
                "settings": {},
                "items": [
                    _payload_widget(item)
                    for row in tab["rows"]
                    for item in row["items"]
                ],
                "layout": [
                    {
                        "i": item["widget_id"],
                        "x": item["x"],
                        "y": item["y"],
                        "w": item["w"],
                        "h": item["h"],
                    }
                    for row in tab["rows"]
                    for item in row["items"]
                ],
            }
            for tab in composition["tabs"]
        ],
    }
    if composition.get("operation") == "update":
        return {
            "mode": "save",
            "entry": {
                "entryId": composition["dashboard_id"],
                "data": data,
                "meta": {"title": composition["dashboard_title"]},
            },
        }
    return {
        "entry": {
            "workbookId": composition["workbook_id"],
            "name": composition["dashboard_internal_name"],
            "data": data,
            "meta": {"title": composition["dashboard_title"]},
        }
    }


def _payload_widget(item: dict[str, Any]) -> dict[str, Any]:
    widget_id = str(item["widget_id"])
    mode = str(item.get("title_mode") or "native_title")
    native = item.get("native_metadata") if isinstance(item.get("native_metadata"), dict) else {}
    raw_tabs = item.get("widget_tabs") if isinstance(item.get("widget_tabs"), list) else []
    if raw_tabs:
        tabs = [
            {
                "id": str(tab.get("id") or f"{widget_id}_tab_{index + 1}"),
                "title": str(tab.get("title") or item.get("display_title") or ""),
                "chartId": str(tab.get("chartId") or tab.get("chart_id") or ""),
                "isDefault": bool(tab.get("isDefault", tab.get("is_default", index == 0))),
                "params": deepcopy(tab.get("params") or {}),
                "autoHeight": bool(tab.get("autoHeight", False)),
                "description": str(tab.get("description") or ""),
                "enableDescription": bool(tab.get("enableDescription", False)),
                "hint": str(tab.get("hint") or ""),
                "enableHint": bool(tab.get("enableHint", False)),
            }
            for index, tab in enumerate(raw_tabs)
            if isinstance(tab, dict)
        ]
    else:
        tabs = [
            {
                "id": f"{widget_id}_tab",
                "title": str(native.get("title") or item.get("display_title") or ""),
                "chartId": str(item.get("chart_id") or widget_id),
                "isDefault": True,
                "params": {},
                "autoHeight": False,
                "description": "",
                "enableDescription": False,
                "hint": str(native.get("hint") or ""),
                "enableHint": bool(native.get("enableHint", False)),
            }
        ]
    return {
        "id": widget_id,
        "namespace": "default",
        "type": "widget",
        "data": {
            "hideTitle": mode not in {"native_title", "tab_strip"},
            "tabs": tabs,
        },
    }
