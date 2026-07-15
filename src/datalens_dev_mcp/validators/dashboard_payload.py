from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from datalens_dev_mcp.validators.dashboard_grid import validate_dashboard_grid
from datalens_dev_mcp.validators.datalens_names import find_unsafe_internal_names


@dataclass(frozen=True)
class DashboardPayloadIssue:
    severity: str
    rule: str
    path: str
    message: str
    object_type: str = ""
    duplicated_id: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "path": self.path,
            "message": self.message,
            "object_type": self.object_type,
            "duplicated_id": self.duplicated_id,
            "suggested_fix": self.suggested_fix,
        }


@dataclass(frozen=True)
class DashboardPayloadValidationResult:
    ok: bool
    issues: list[DashboardPayloadIssue]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.to_dict() for issue in self.issues]}


def validate_dashboard_payload(
    payload: dict[str, Any],
    *,
    current_dashboard: dict[str, Any] | None = None,
    preserved_control_ids: list[str] | None = None,
    project_contract: dict[str, Any] | None = None,
    strict: bool = True,
) -> DashboardPayloadValidationResult:
    issues: list[DashboardPayloadIssue] = []
    preserved = set(preserved_control_ids or [])
    contract = project_contract or {}
    issues.extend(_duplicate_item_id_issues(payload, preserved_control_ids=preserved))
    issues.extend(
        DashboardPayloadIssue(
            severity=issue.severity,
            rule=issue.rule,
            path=issue.path,
            message=issue.message,
            object_type=issue.object_type,
            suggested_fix=issue.suggested_fix,
        )
        for issue in validate_dashboard_grid(payload, current_dashboard=current_dashboard)
    )
    issues.extend(_nested_tab_issues(payload))
    issues.extend(_selector_collision_issues(payload, preserved_control_ids=preserved))
    issues.extend(_preserved_selector_issues(payload, current_dashboard=current_dashboard or {}, preserved_control_ids=preserved))
    issues.extend(_native_title_hint_issues(payload, current_dashboard=current_dashboard or {}))
    issues.extend(_inline_title_issues(payload, strict=strict))
    issues.extend(_selector_layout_issues(payload))
    issues.extend(_impact_tabs_scope_issues(payload))
    issues.extend(_date_range_contract_issues(payload, project_contract=contract))
    issues.extend(_debug_widget_issues(payload, project_contract=contract))
    issues.extend(_availability_default_issues(payload, project_contract=contract))
    issues.extend(_hidden_dependency_issues(payload))
    for unsafe in find_unsafe_internal_names(payload):
        issues.append(
            DashboardPayloadIssue(
                severity="error",
                rule="unsafe_internal_name",
                path=unsafe["path"],
                message=unsafe["reason"],
                object_type="internal_name",
                suggested_fix=unsafe["suggested"],
            )
        )
    ok = not any(issue.severity == "error" for issue in issues)
    return DashboardPayloadValidationResult(ok=ok, issues=issues)


def rewrite_duplicate_nested_tab_ids(payload: dict[str, Any]) -> dict[str, Any]:
    rewritten = deepcopy(payload)
    seen: set[str] = set()

    def walk(value: Any, path: str = "$", parent_id: str = "widget") -> None:
        if isinstance(value, dict):
            local_parent = str(value.get("id") or parent_id or "widget")
            for key in ("tabs", "widgetTabs", "widget_tabs"):
                tabs = value.get(key)
                if not isinstance(tabs, list):
                    continue
                for index, tab in enumerate(tabs):
                    if not isinstance(tab, dict):
                        continue
                    tab_id = str(tab.get("id") or "").strip()
                    if not tab_id or tab_id in seen:
                        base = _stable_id(f"{local_parent}_tab_{index + 1}")
                        tab_id = _unique_id(base, seen)
                        tab["id"] = tab_id
                    seen.add(tab_id)
            for item in value.values():
                walk(item, path=path, parent_id=local_parent)
        elif isinstance(value, list):
            for item in value:
                walk(item, path=path, parent_id=parent_id)

    walk(rewritten)
    return rewritten


def _duplicate_item_id_issues(payload: Any, *, preserved_control_ids: set[str]) -> list[DashboardPayloadIssue]:
    occurrences: dict[str, list[tuple[str, str]]] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("id"), str) and not _is_root_dashboard_tab_path(path):
                item_id = value["id"]
                occurrences.setdefault(item_id, []).append((path + ".id", _object_type(value, path)))
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    issues: list[DashboardPayloadIssue] = []
    for item_id, paths in sorted(occurrences.items()):
        if len(paths) <= 1:
            continue
        object_types = {object_type for _, object_type in paths}
        if item_id in preserved_control_ids and object_types <= {"selector", "control"}:
            continue
        issues.append(
            DashboardPayloadIssue(
                severity="error",
                rule="duplicate_item_id",
                path=", ".join(path for path, _ in paths),
                message=f"Dashboard id {item_id!r} appears {len(paths)} times.",
                object_type="/".join(sorted(object_types)),
                duplicated_id=item_id,
                suggested_fix="Regenerate stable ids per widget, chart, selector, and nested tab.",
            )
        )
    return issues


def _nested_tab_issues(payload: Any) -> list[DashboardPayloadIssue]:
    tab_occurrences: dict[str, list[tuple[str, str]]] = {}
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str, parent_id: str = "") -> None:
        if isinstance(value, dict):
            local_parent = str(value.get("id") or parent_id or "")
            for key in ("tabs", "widgetTabs", "widget_tabs"):
                if key == "tabs" and path == "$":
                    continue
                tabs = value.get(key)
                if not isinstance(tabs, list):
                    continue
                for index, tab in enumerate(tabs):
                    tab_path = f"{_join_path(path, key)}[{index}]"
                    if not isinstance(tab, dict):
                        issues.append(
                            DashboardPayloadIssue(
                                severity="error",
                                rule="malformed_nested_tab",
                                path=tab_path,
                                message="Nested widget tab must be an object.",
                                object_type="nested_widget_tab",
                                suggested_fix="Use objects with id and chartId/chart_id.",
                            )
                        )
                        continue
                    tab_id = str(tab.get("id") or "").strip()
                    if not tab_id:
                        issues.append(
                            DashboardPayloadIssue(
                                severity="error",
                                rule="missing_nested_tab_id",
                                path=f"{tab_path}.id",
                                message="Nested widget tab id is missing or empty.",
                                object_type="nested_widget_tab",
                                suggested_fix=f"Use a stable id such as {_stable_id(local_parent)}_tab_{index + 1}.",
                            )
                        )
                        continue
                    tab_occurrences.setdefault(tab_id, []).append((f"{tab_path}.id", local_parent))
            for key, item in value.items():
                walk(item, _join_path(path, key), local_parent)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", parent_id)

    walk(payload, "$")
    for tab_id, paths in sorted(tab_occurrences.items()):
        if len(paths) <= 1:
            continue
        issues.append(
            DashboardPayloadIssue(
                severity="error",
                rule="duplicate_nested_tab_id",
                path=", ".join(path for path, _ in paths),
                message=f"Nested widget tab id {tab_id!r} is duplicated.",
                object_type="nested_widget_tab",
                duplicated_id=tab_id,
                suggested_fix="Run nested tab id reflow and keep tab ids unique across the dashboard payload.",
            )
        )
    return issues


def _selector_collision_issues(payload: Any, *, preserved_control_ids: set[str]) -> list[DashboardPayloadIssue]:
    by_id: dict[str, set[str]] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            item_id = value.get("id")
            if isinstance(item_id, str) and item_id:
                by_id.setdefault(item_id, set()).add(_object_type(value, path))
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    issues: list[DashboardPayloadIssue] = []
    for item_id, types in sorted(by_id.items()):
        if item_id in preserved_control_ids and types <= {"selector", "control"}:
            continue
        if ("selector" in types or "control" in types) and len(types - {"selector", "control"}) > 0:
            issues.append(
                DashboardPayloadIssue(
                    severity="error",
                    rule="selector_id_collision",
                    path="$",
                    message=f"Selector/control id {item_id!r} collides with chart/widget ids.",
                    object_type="/".join(sorted(types)),
                    duplicated_id=item_id,
                    suggested_fix="Use separate id namespaces for selectors/controls, widgets, nested tabs, and charts.",
                )
            )
    return issues


def _preserved_selector_issues(
    payload: Any,
    *,
    current_dashboard: dict[str, Any],
    preserved_control_ids: set[str],
) -> list[DashboardPayloadIssue]:
    if not current_dashboard or not preserved_control_ids:
        return []
    current_ids = _selector_ids(current_dashboard)
    proposed_ids = _selector_ids(payload)
    issues: list[DashboardPayloadIssue] = []
    for control_id in sorted(preserved_control_ids):
        if control_id in current_ids and control_id not in proposed_ids:
            issues.append(
                DashboardPayloadIssue(
                    severity="error",
                    rule="missing_preserved_control",
                    path="$",
                    message=f"Preserved global control {control_id!r} existed in current dashboard but is absent from proposed payload.",
                    object_type="selector",
                    suggested_fix="Carry the exact existing selector/control id forward or remove it from preserved_control_ids.",
                )
            )
    return issues


def _native_title_hint_issues(payload: Any, *, current_dashboard: dict[str, Any]) -> list[DashboardPayloadIssue]:
    issues: list[DashboardPayloadIssue] = []
    legacy_missing_ids = _legacy_missing_native_metadata_ids(current_dashboard)

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            tabs = value.get("tabs") or value.get("widgetTabs") or value.get("widget_tabs")
            item_id = str(value.get("id") or value.get("widgetId") or value.get("chartId") or "").strip()
            if item_id and isinstance(tabs, list) and len(tabs) > 1:
                if item_id and item_id in legacy_missing_ids:
                    for key, item in value.items():
                        walk(item, _join_path(path, key))
                    return
                title = value.get("native_title") or value.get("title") or (value.get("nativeMetadata") or {}).get("title")
                hint = value.get("native_hint") or value.get("hint") or (value.get("nativeMetadata") or {}).get("hint")
                if not title or not hint:
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error",
                            rule="missing_native_title_hint",
                            path=path,
                            message="Multi-tab dashboard blocks require native title and hint metadata.",
                            object_type=_object_type(value, path),
                            suggested_fix="Set native_title/native_hint or equivalent nativeMetadata fields on the block.",
                        )
                    )
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _inline_title_issues(payload: Any, *, strict: bool) -> list[DashboardPayloadIssue]:
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            title = str(value.get("native_title") or value.get("title") or "").strip()
            object_type = _object_type(value, path)
            if title and object_type in {"advanced_editor", "editor_chart", "widget"}:
                body_text = _joined_strings(value.get("tabs") or value.get("body") or value.get("data") or value)
                lowered = body_text.lower()
                title_pattern = r"<\s*h[1-6]\b[^>]*>\s*" + re.escape(title.lower()) + r"\b"
                if re.search(title_pattern, lowered):
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error" if strict else "warning",
                            rule="duplicate_inline_title",
                            path=path,
                            message="Advanced Editor body renders a visible title that duplicates dashboard native metadata.",
                            object_type=object_type,
                            suggested_fix="Remove inline h1/h2 title from Editor body and keep the dashboard native title/hint.",
                        )
                    )
            hint = str(value.get("native_hint") or value.get("hint") or "").strip()
            if object_type in {"advanced_editor", "editor_chart", "widget"}:
                body_text = _joined_strings(value.get("tabs") or value.get("body") or value.get("data") or value)
                lowered = body_text.lower()
                if hint and hint.lower() in lowered:
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error" if strict else "warning",
                            rule="duplicate_inline_hint",
                            path=path,
                            message="Advanced Editor body renders a visible hint that duplicates dashboard native metadata.",
                            object_type=object_type,
                            suggested_fix="Remove inline hint text from Editor body and keep the dashboard native hint.",
                        )
                    )
                if re.search(r"data-id\s*=\s*['\"]hint['\"]|class\s*=\s*['\"][^'\"]*\bhint\b", lowered):
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error" if strict else "warning",
                            rule="inline_hint_ui",
                            path=path,
                            message="Advanced Editor body renders a hint control instead of native dashboard hint metadata.",
                            object_type=object_type,
                            suggested_fix="Remove in-body hint controls and use native dashboard/widget metadata.",
                        )
                    )
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _selector_layout_issues(payload: Any) -> list[DashboardPayloadIssue]:
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if _object_type(value, path) in {"selector", "control"}:
                label = value.get("labelPlacement", value.get("label_placement", "left"))
                width = str(value.get("width", ""))
                if label != "left":
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error",
                            rule="selector_label_placement",
                            path=path,
                            message="Selector labelPlacement must be left by default.",
                            object_type="selector",
                            suggested_fix="Set labelPlacement to left unless an explicit project rule overrides it.",
                        )
                    )
                if width and not width.endswith("%"):
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error",
                            rule="selector_width_unit",
                            path=path,
                            message="Selector width must use percent units.",
                            object_type="selector",
                            suggested_fix="Use widths like 24%, 48%, or 96%.",
                        )
                    )
            for key, item in value.items():
                if key == "selector_rows" and isinstance(item, list):
                    issues.extend(_selector_row_width_issues(item, _join_path(path, key)))
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _selector_row_width_issues(rows: list[Any], path: str) -> list[DashboardPayloadIssue]:
    issues: list[DashboardPayloadIssue] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        total = 0.0
        for item in row:
            if isinstance(item, dict):
                width_value = item.get("width_pct")
                if isinstance(width_value, (int, float)):
                    total += float(width_value)
                    continue
                width = str(item.get("width", "")).strip()
                if width.endswith("%"):
                    try:
                        total += float(width[:-1])
                    except ValueError:
                        pass
        if row and total > 96.0 + 0.01:
            issues.append(
                DashboardPayloadIssue(
                    severity="error",
                    rule="selector_row_width_total",
                    path=f"{path}[{row_index}]",
                    message=f"Selector row widths must be <= 96%, got {total:g}%.",
                    object_type="selector_row",
                    suggested_fix="Split controls into another selector row or reduce widths without going below minimums.",
                )
            )
    return issues


def _impact_tabs_scope_issues(payload: Any) -> list[DashboardPayloadIssue]:
    tab_ids = _tab_ids(payload)
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if _object_type(value, path) in {"selector", "control"}:
                impact_tabs = value.get("impactTabsIds", value.get("impact_tabs_ids"))
                if impact_tabs is not None and not isinstance(impact_tabs, list):
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error",
                            rule="selector_impact_tabs_scope",
                            path=path,
                            message="Selector impactTabsIds must be a list of known tab ids.",
                            object_type="selector",
                            suggested_fix="Use a list of existing dashboard or nested widget tab ids.",
                        )
                    )
                elif isinstance(impact_tabs, list):
                    unknown = [str(item) for item in impact_tabs if str(item) not in tab_ids]
                    if unknown:
                        issues.append(
                            DashboardPayloadIssue(
                                severity="error",
                                rule="selector_impact_tabs_scope",
                                path=path,
                                message=f"Selector impactTabsIds reference unknown tab ids: {', '.join(unknown)}.",
                                object_type="selector",
                                suggested_fix="Scope impactTabsIds to ids present in tabs/widgetTabs.",
                            )
                        )
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _date_range_contract_issues(payload: Any, *, project_contract: dict[str, Any]) -> list[DashboardPayloadIssue]:
    if not _requires_date_range_control(project_contract):
        return []
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if _object_type(value, path) in {"selector", "control"} and _looks_like_date_selector(value):
                text = _joined_strings(value).lower()
                control_type = str(value.get("controlType") or value.get("control_type") or value.get("variant") or "").lower()
                if "preset" in control_type or "preset" in text or "last_" in text:
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error",
                            rule="date_range_selector_regression",
                            path=path,
                            message="Date-range selector contract forbids reverting to old preset controls.",
                            object_type="selector",
                            suggested_fix="Keep the project date-range control shape and do not replace it with preset shortcuts.",
                        )
                    )
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _debug_widget_issues(payload: Any, *, project_contract: dict[str, Any]) -> list[DashboardPayloadIssue]:
    if project_contract.get("allow_debug_widgets") or project_contract.get("allow_service_widgets"):
        return []
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            object_type = _object_type(value, path)
            if object_type in {"widget", "chart", "advanced_editor"}:
                text = " ".join(
                    str(value.get(key) or "")
                    for key in ("id", "name", "title", "type", "entry_type", "description")
                ).lower()
                if any(token in text for token in ("debug", "service_widget", "service widget", "dev_only", "test_widget")):
                    issues.append(
                        DashboardPayloadIssue(
                            severity="error",
                            rule="debug_widget_in_publish_layout",
                            path=path,
                            message="Debug/service widgets must not appear in publish layout unless explicitly allowed.",
                            object_type=object_type,
                            suggested_fix="Remove the widget from the publish payload or set an explicit project allow flag.",
                        )
                    )
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _availability_default_issues(payload: Any, *, project_contract: dict[str, Any]) -> list[DashboardPayloadIssue]:
    evidence = project_contract.get("availability_evidence") or project_contract.get("source_availability") or {}
    if not isinstance(evidence, dict) or evidence.get("status") not in {"available", "AVAILABLE", "runtime_available"}:
        return []
    issues: list[DashboardPayloadIssue] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            default_text = " ".join(
                str(value.get(key) or "") for key in ("default", "defaultValue", "default_value", "emptyValue", "statusText")
            ).lower()
            if "no table" in default_text or "no_table" in default_text:
                issues.append(
                    DashboardPayloadIssue(
                        severity="error",
                        rule="stale_no_table_default",
                        path=path,
                        message="Availability evidence is available but payload still forces a NO TABLE style default.",
                        object_type=_object_type(value, path),
                        suggested_fix="Use the live evidence-backed availability/default state instead of stale fallback flags.",
                    )
                )
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return issues


def _hidden_dependency_issues(payload: dict[str, Any]) -> list[DashboardPayloadIssue]:
    dependencies = payload.get("selector_dependencies")
    detail_columns = payload.get("detail_columns") or payload.get("source_table_columns")
    if not isinstance(dependencies, dict) or not isinstance(detail_columns, list):
        return []
    available = {str(column.get("name") if isinstance(column, dict) else column) for column in detail_columns}
    issues: list[DashboardPayloadIssue] = []
    for selector_id, fields in dependencies.items():
        for field in fields if isinstance(fields, list) else []:
            if str(field) not in available:
                issues.append(
                    DashboardPayloadIssue(
                        severity="error",
                        rule="missing_hidden_filter_field",
                        path="$.detail_columns",
                        message=f"Selector {selector_id!r} depends on hidden/detail field {field!r}, but the field is absent.",
                        object_type="detail_table",
                        suggested_fix="Keep hidden selector/filter columns in detail/source tables even when not visible.",
                    )
                )
    return issues


def _legacy_missing_native_metadata_ids(payload: Any) -> set[str]:
    ids: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            tabs = value.get("tabs") or value.get("widgetTabs") or value.get("widget_tabs")
            item_id = str(value.get("id") or value.get("widgetId") or value.get("chartId") or "").strip()
            if item_id and isinstance(tabs, list) and len(tabs) > 1:
                title = value.get("native_title") or value.get("title") or (value.get("nativeMetadata") or {}).get("title")
                hint = value.get("native_hint") or value.get("hint") or (value.get("nativeMetadata") or {}).get("hint")
                if not title or not hint:
                    ids.add(item_id)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return ids


def _tab_ids(payload: Any) -> set[str]:
    ids: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("tabs", "widgetTabs", "widget_tabs"):
                tabs = value.get(key)
                if isinstance(tabs, list):
                    for tab in tabs:
                        if isinstance(tab, dict) and isinstance(tab.get("id"), str):
                            ids.add(tab["id"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return ids


def _requires_date_range_control(project_contract: dict[str, Any]) -> bool:
    text = " ".join(
        str(project_contract.get(key) or "")
        for key in (
            "date_range_selector",
            "date_range_control",
            "date_selector_contract",
            "period_selector_contract",
        )
    ).lower()
    return bool(project_contract.get("require_date_range_selector") or ("date" in text and "range" in text))


def _looks_like_date_selector(value: dict[str, Any]) -> bool:
    text = " ".join(
        str(value.get(key) or "") for key in ("id", "name", "title", "param", "field", "type", "controlType", "control_type")
    ).lower()
    return any(token in text for token in ("date", "period", "range", "dt", "dttm"))


def _selector_ids(payload: Any) -> set[str]:
    ids: set[str] = set()

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if _object_type(value, path) in {"selector", "control"} and isinstance(value.get("id"), str):
                ids.add(value["id"])
            for key, item in value.items():
                walk(item, _join_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return ids


def _object_type(value: dict[str, Any], path: str) -> str:
    raw = str(value.get("type") or value.get("entry_type") or "").lower()
    if "selector" in raw:
        return "selector"
    if "control" in raw:
        return "control"
    if "advanced" in raw or "editor" in raw:
        return "advanced_editor"
    if "widget" in raw:
        return "widget"
    if "chart" in raw:
        return "chart"
    lowered_path = path.lower()
    if "selector" in lowered_path:
        return "selector"
    if "control" in lowered_path:
        return "control"
    if "tab" in lowered_path:
        return "nested_widget_tab"
    return raw or "object"


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


def _stable_id(value: str) -> str:
    rendered = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    while "__" in rendered:
        rendered = rendered.replace("__", "_")
    return rendered or "tab"


def _unique_id(base: str, seen: set[str]) -> str:
    if base not in seen:
        return base
    index = 2
    while f"{base}_{index}" in seen:
        index += 1
    return f"{base}_{index}"


def _join_path(path: str, key: Any) -> str:
    if path == "$":
        return f"$.{key}"
    return f"{path}.{key}"


def _is_root_dashboard_tab_path(path: str) -> bool:
    return path.startswith("$.tabs[") and "]." not in path.removeprefix("$.tabs[")
