from __future__ import annotations

from collections import defaultdict
from typing import Any

from datalens_dev_mcp.validators.route_validator import ValidationResult


SELECTOR_ROW_WIDTH_TARGET = 94


LAYOUT_BLUEPRINTS = {
    "overview": {
        "selector_zone": "top compact row",
        "content_flow": ["kpi_row", "trend_or_comparison", "detail_or_navigation"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
    "self_service": {
        "selector_zone": "top or left dense filter panel",
        "content_flow": ["selector_panel", "summary", "comparison_or_trend", "detail_table"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
    "object_management": {
        "selector_zone": "status and owner filter row",
        "content_flow": ["status_summary", "action_queue", "reason_breakdown", "object_navigation"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
    "alerts_mailing": {
        "selector_zone": "minimal defaults",
        "content_flow": ["threshold_summary", "exception_table", "owner_action"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
    "analytical_tool": {
        "selector_zone": "method-safe filter workspace",
        "content_flow": ["method_note", "filters", "primary_analysis", "supporting_detail"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
    "experiment_report": {
        "selector_zone": "cohort and period controls",
        "content_flow": ["hypothesis", "cohort_metrics", "trend_context", "decision_block"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
    "project_ad_hoc": {
        "selector_zone": "scope filters only",
        "content_flow": ["status_strip", "milestones", "risk_action_table", "owner_block"],
        "selector_row_width": "94%",
        "native_metadata_required": True,
    },
}


def layout_blueprint_for_dashboard_type(dashboard_type: str | None) -> dict[str, Any]:
    normalized = (dashboard_type or "overview").strip().lower()
    resolved = normalized if normalized in LAYOUT_BLUEPRINTS else "overview"
    return {"dashboard_type": resolved, **LAYOUT_BLUEPRINTS.get(normalized, LAYOUT_BLUEPRINTS["overview"])}


def plan_selector_row_widths(names: list[str], *, target: int = SELECTOR_ROW_WIDTH_TARGET) -> dict[str, str]:
    if not names:
        raise ValueError("selector layout requires at least one control")
    if target <= 0 or target > 100:
        raise ValueError("selector row width target must be between 1 and 100")
    base = target // len(names)
    if base < 8:
        raise ValueError(
            f"selector row cannot fit {len(names)} controls into {target}% with readable widths; split the row"
        )
    remainder = target - (base * len(names))
    widths: dict[str, str] = {}
    for index, name in enumerate(names):
        widths[name] = f"{base + (1 if index < remainder else 0)}%"
    return widths


def _width_percent(value: Any) -> int | None:
    if not isinstance(value, str) or not value.endswith("%"):
        return None
    try:
        number = int(value.removesuffix("%"))
    except ValueError:
        return None
    return number if 0 < number <= 100 else None


def validate_selector_controls(controls: list[dict[str, Any]], *, target: int = SELECTOR_ROW_WIDTH_TARGET) -> ValidationResult:
    issues: list[str] = []
    row_widths: dict[str, int] = defaultdict(int)
    current_row = "row-1"
    for index, control in enumerate(controls):
        param = str(control.get("param") or f"control[{index}]")
        if control.get("labelPlacement") != "left":
            issues.append(f"{param}: labelPlacement must be left")
        width = _width_percent(control.get("width"))
        if width is None:
            issues.append(f"{param}: width must be a percentage string such as '16%'")
        else:
            row_widths[str(control.get("row") or current_row)] += width
        if control.get("lineBreak"):
            current_row = f"row-{len(row_widths) + 1}"
    for row, width in sorted(row_widths.items()):
        if width > target:
            issues.append(f"{row}: selector row width total {width}% exceeds {target}% target")
    return ValidationResult(ok=not issues, issues=issues)


def validate_dashboard_widget_tabs(dashboard: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    for tab_index, dashboard_tab in enumerate((dashboard.get("data") or {}).get("tabs") or []):
        for item_index, item in enumerate(dashboard_tab.get("items") or []):
            data = item.get("data") or {}
            tabs = data.get("tabs") or []
            if len(tabs) < 2:
                continue
            item_id = item.get("id") or f"tab[{tab_index}].item[{item_index}]"
            if data.get("hideTitle") is not False:
                issues.append(f"{item_id}: data.hideTitle must be false when one widget contains multiple inner tabs")
            for inner_index, inner_tab in enumerate(tabs):
                if not inner_tab.get("title"):
                    issues.append(f"{item_id}.tabs[{inner_index}]: title is required")
                if not inner_tab.get("chartId"):
                    issues.append(f"{item_id}.tabs[{inner_index}]: chartId is required")
    return ValidationResult(ok=not issues, issues=issues)
