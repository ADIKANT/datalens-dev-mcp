from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


MIN_WIDTH_BY_KIND = {
    "date_range": 14.0,
    "single_select": 12.0,
    "multi_select": 16.0,
    "search_select": 18.0,
    "granularity": 10.0,
}
ROW_WIDTH_SUM_MAX_PCT = 96.0


@dataclass(frozen=True)
class SelectorFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectorLayoutResult:
    ok: bool
    publish_allowed: bool
    row_count: int
    selector_count: int
    row_widths_pct: list[float]
    findings: list[SelectorFinding] = field(default_factory=list)
    schema_version: str = "2026-07-01.selector_layout_contract.v1"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


class SelectorLayoutContract:
    def __init__(self, *, row_width_sum_max_pct: float = ROW_WIDTH_SUM_MAX_PCT) -> None:
        self.row_width_sum_max_pct = float(row_width_sum_max_pct)

    def width_for(self, selector: dict[str, Any]) -> float:
        kind = _selector_kind(selector)
        label = str(selector.get("label") or selector.get("title") or selector.get("name") or "")
        minimum = MIN_WIDTH_BY_KIND.get(kind, MIN_WIDTH_BY_KIND["single_select"])
        label_extra = max(0, len(label.strip()) - 12) * 0.45
        option_extra = 2.0 if selector.get("multi") or kind == "multi_select" else 0.0
        return min(48.0, max(minimum, round(minimum + label_extra + option_extra, 1)))

    def compute_rows(self, selectors: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        rows: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_width = 0.0
        for selector in selectors:
            item = dict(selector)
            width = _width_value(item)
            if width <= 0:
                width = self.width_for(item)
                item["width"] = f"{width:g}%"
            if current and current_width + width > self.row_width_sum_max_pct:
                rows.append(current)
                current = []
                current_width = 0.0
            current.append(item)
            current_width += width
        if current:
            rows.append(current)
        return rows


def validate_selector_layout_contract(
    payload: dict[str, Any],
    *,
    available_target_ids: set[str] | None = None,
    available_fields: set[str] | None = None,
) -> SelectorLayoutResult:
    selectors = _selectors(payload)
    rows = _selector_rows(payload, selectors)
    findings: list[SelectorFinding] = []
    row_widths: list[float] = []
    known_targets = set(available_target_ids or _target_ids(payload))
    known_fields = set(available_fields or _available_fields(payload))
    for row_index, row in enumerate(rows):
        total = 0.0
        for selector_index, selector in enumerate(row):
            path = f"$.selector_rows[{row_index}][{selector_index}]"
            width = _width_value(selector)
            minimum = MIN_WIDTH_BY_KIND.get(_selector_kind(selector), MIN_WIDTH_BY_KIND["single_select"])
            if width <= 0:
                findings.append(_finding("selector_width_missing", f"{path}.width", "selector width must be a percent value"))
            elif width < minimum:
                findings.append(
                    _finding(
                        "selector_width_below_minimum",
                        f"{path}.width",
                        f"selector width {width:g}% is below {_selector_kind(selector)} minimum {minimum:g}%",
                    )
                )
            total += max(width, 0.0)
            findings.extend(_selector_wiring_findings(selector, path=path, known_targets=known_targets, known_fields=known_fields))
            native_shape = _native_control_shape(selector)
            if not native_shape["ok"]:
                findings.append(
                    _finding(
                        "selector_not_control_node",
                        f"{path}.object_type",
                        native_shape["message"],
                    )
                )
        row_widths.append(round(total, 3))
        if total > ROW_WIDTH_SUM_MAX_PCT + 0.001:
            findings.append(
                _finding(
                    "selector_row_width_over_budget",
                    f"$.selector_rows[{row_index}]",
                    f"selector row width sum must be <= 96%, got {total:g}%",
                )
            )
    if not rows and selectors:
        findings.append(_finding("selector_rows_missing", "$.selector_rows", "selector rows were not computed"))
    body_text = _joined_strings(payload).lower()
    if "selector" in body_text and "advanced editor" in body_text and not selectors:
        findings.append(
            _finding(
                "selector_inside_chart_body",
                "$",
                "selector-looking UI in an Advanced Editor body is not a native control widget",
            )
        )
    errors = [finding for finding in findings if finding.severity == "error"]
    return SelectorLayoutResult(
        ok=not errors,
        publish_allowed=not errors,
        row_count=len(rows),
        selector_count=len(selectors) or sum(len(row) for row in rows),
        row_widths_pct=row_widths,
        findings=findings,
    )


def _selectors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("selectors") or payload.get("controls") or []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _selector_rows(payload: dict[str, Any], selectors: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    raw = payload.get("selector_rows") or payload.get("selectorRows")
    if isinstance(raw, list):
        rows: list[list[dict[str, Any]]] = []
        for row in raw:
            if isinstance(row, list):
                rows.append([item for item in row if isinstance(item, dict)])
        return rows
    return SelectorLayoutContract().compute_rows(selectors)


def _selector_wiring_findings(
    selector: dict[str, Any],
    *,
    path: str,
    known_targets: set[str],
    known_fields: set[str],
) -> list[SelectorFinding]:
    findings: list[SelectorFinding] = []
    selector_id = str(selector.get("selector_id") or selector.get("id") or "").strip()
    if not selector_id:
        findings.append(_finding("selector_id_missing", f"{path}.id", "selector id is required"))
    targets = selector.get("target_widget_ids") or selector.get("targetWidgetIds") or selector.get("targets") or []
    if not isinstance(targets, list) or not targets:
        findings.append(_finding("selector_targets_missing", f"{path}.target_widget_ids", "selector targets are required"))
    else:
        unknown = [str(item) for item in targets if str(item) not in known_targets]
        nondeterministic = [str(item) for item in targets if str(item).strip().lower() in {"*", "all", "__all__", "dashboard"}]
        if nondeterministic:
            findings.append(
                _finding(
                    "selector_nondeterministic_target_id",
                    f"{path}.target_widget_ids",
                    f"selector targets must be explicit object ids, got: {', '.join(nondeterministic)}",
                )
            )
        if unknown:
            findings.append(
                _finding(
                    "selector_unknown_target_id",
                    f"{path}.target_widget_ids",
                    f"selector targets unknown object ids: {', '.join(unknown)}",
                )
            )
    field = str(selector.get("target_field_or_parameter") or selector.get("field") or selector.get("param") or "").strip()
    if not field:
        findings.append(_finding("selector_field_missing", f"{path}.target_field_or_parameter", "selector field/parameter is required"))
    elif known_fields and field not in known_fields:
        findings.append(_finding("selector_unknown_field", f"{path}.field", f"selector field {field!r} is absent from source schema"))
    if "default_value_policy" not in selector and "defaultValue" not in selector and "default_value" not in selector:
        findings.append(
            _finding("selector_default_policy_missing", f"{path}.default_value_policy", "selector default value policy is required")
        )
    affected = selector.get("affected_tabs") or selector.get("impactTabsIds") or selector.get("impact_tabs_ids")
    if affected is not None and not isinstance(affected, list):
        findings.append(_finding("selector_affected_tabs_shape", f"{path}.affected_tabs", "affected tabs must be a list"))
    return findings


def _target_ids(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for container_key in ("objects", "widgets", "items", "charts", "visuals"):
        raw = payload.get(container_key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                for key in ("object_id", "id", "chart_id", "chartId", "widget_id", "widgetId"):
                    if item.get(key):
                        ids.add(str(item[key]))
    return ids


def _available_fields(payload: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for key in ("fields", "source_fields", "dataset_fields"):
        raw = payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("name"):
                    fields.add(str(item["name"]))
                elif isinstance(item, str):
                    fields.add(item)
    return fields


def _width_value(selector: dict[str, Any]) -> float:
    width = selector.get("width_pct")
    if isinstance(width, (int, float)):
        return float(width)
    raw = str(selector.get("width") or "").strip()
    if raw.endswith("%"):
        try:
            return float(raw[:-1])
        except ValueError:
            return 0.0
    return 0.0


def _selector_kind(selector: dict[str, Any]) -> str:
    raw = str(selector.get("kind") or selector.get("selector_kind") or selector.get("controlType") or selector.get("type") or "").lower()
    if "date" in raw or "period" in raw:
        return "date_range"
    if "multi" in raw:
        return "multi_select"
    if "search" in raw:
        return "search_select"
    if "granularity" in raw or "grain" in raw:
        return "granularity"
    return "single_select"


def _object_type(selector: dict[str, Any]) -> str:
    return str(selector.get("object_type") or selector.get("entry_type") or selector.get("route") or "").strip().lower()


def _native_control_shape(selector: dict[str, Any]) -> dict[str, Any]:
    object_type = str(selector.get("object_type") or "").strip().lower()
    entry_type = str(selector.get("entry_type") or "").strip().lower()
    route = str(selector.get("route") or selector.get("selected_route") or "").strip().lower()
    explicit_type = entry_type or object_type
    if explicit_type:
        if explicit_type == "control_node":
            return {"ok": True, "message": ""}
        return {
            "ok": False,
            "message": f"selector must materialize as native control_node, got {explicit_type}",
        }
    if route and route not in {"editor_js_control"}:
        return {
            "ok": False,
            "message": f"selector route must compile to control_node, got {route}",
        }
    return {"ok": True, "message": ""}


def _joined_strings(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_joined_strings(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_joined_strings(item))
    elif isinstance(value, str):
        parts.append(value)
    return "\n".join(parts)


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> SelectorFinding:
    return SelectorFinding(rule=rule, severity=severity, path=path, message=message)
