from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.editor.selector_contract import selector_params
from datalens_dev_mcp.pipeline.layout_contract import (
    SELECTOR_ROW_WIDTH_TARGET,
    layout_blueprint_for_dashboard_type,
    validate_selector_controls,
)
from datalens_dev_mcp.validators.route_validator import ValidationResult


RELATION_SCHEMA_VERSION = "2026-07-20.dashboard_object_relations.v3"


def build_default_dashboard_relations(
    *,
    brief: dict[str, Any],
    widget_id: str,
    selector_param: str | None = None,
    selector_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_fields = list((brief.get("data_contract") or {}).get("fields") or [])
    fields = [name for item in raw_fields if (name := _field_name(item))]
    field_names = set(fields)
    contract_id = (brief.get("data_contract") or {}).get("contract_id") or "DATA-001"
    decisions = brief.get("chart_decisions") or []
    decision = decisions[0] if decisions else {}
    chart_id = decision.get("widget_id") or widget_id
    route = decision.get("route") or "editor_advanced"
    family = decision.get("family") or "kpi_value_sparkline"
    normalized_selector_contract = selector_contract or {}
    if normalized_selector_contract and normalized_selector_contract.get("ok") is not True:
        raise ValueError("dashboard relations require a complete normalized selector contract")
    relation_params = (
        selector_params(normalized_selector_contract)
        if normalized_selector_contract
        else [str(selector_param).strip()]
        if str(selector_param or "").strip()
        else []
    )
    selector_id = _selector_id(relation_params) if relation_params else ""
    source_fields = [parameter for parameter in relation_params if parameter in field_names]
    dashboard_type = brief.get("dashboard_type") or brief.get("dashboard_blueprint", {}).get("dashboard_type") or "overview"
    layout_blueprint = layout_blueprint_for_dashboard_type(dashboard_type)
    native_metadata = {
        "title": decision.get("title") or brief.get("dashboard_name") or "DataLens Widget",
        "hint": decision.get("hint") or f"{family} on {route}; source and field dependencies are declared in object relations.",
        "hideTitle": False,
        "enableHint": True,
    }
    return {
        "schema_version": RELATION_SCHEMA_VERSION,
        "dashboard": {
            "dashboard_id_placeholder": "dashboard_target",
            "name": brief.get("dashboard_name") or "DataLens Dashboard",
            "dashboard_type": layout_blueprint["dashboard_type"],
        },
        "layout_blueprint": layout_blueprint,
        "tabs": [
            {
                "tab_id": "main",
                "title": "Main",
                "widgets": [widget_id, *([selector_id] if selector_id else [])],
                "relation": "tab_to_widget",
            }
        ],
        "widgets": [
            {
                "widget_id": widget_id,
                "object_id_placeholder": chart_id,
                "tab_id": "main",
                "chart_id": chart_id,
                "route": route,
                "layout": {"x": 0, "y": 8, "w": 94, "h": 24, "width": "94%"},
                "native_metadata": native_metadata,
            },
            *(
                [
                    {
                        "widget_id": selector_id,
                        "object_id_placeholder": selector_id,
                        "tab_id": "main",
                        "selector_id": selector_id,
                        "route": "editor_js_control",
                        "layout": {"x": 0, "y": 0, "w": 94, "h": 4, "width": "94%"},
                    }
                ]
                if selector_id
                else []
            ),
        ],
        "charts": [
            {
                "chart_id": chart_id,
                "widget_id": widget_id,
                "family": family,
                "route": route,
                "dataset_dependencies": [contract_id],
                "field_dependencies": fields,
                "calculated_field_dependencies": [],
                "native_metadata": native_metadata,
            }
        ],
        "chart_relations": [
            {
                "source_chart_id": chart_id,
                "target_chart_id": "",
                "relation_kind": "none",
                "description": "No chart-to-chart relation declared yet.",
            }
        ],
        "selectors": (
            [
                _selector_relation(
                    selector_id=selector_id,
                    widget_id=widget_id,
                    parameters=relation_params,
                    source_fields=source_fields,
                    contract=normalized_selector_contract,
                )
            ]
            if selector_id
            else []
        ),
        "dashboard_filters": [
            {
                "filter_id": f"filter_{_technical_token(parameter)}",
                "param": parameter,
                "selector_id": selector_id,
                "targets": [widget_id],
            }
            for parameter in relation_params
        ],
        "navigation_relations": [
            {
                "source_id": widget_id,
                "target_id": "",
                "relation_kind": "not_declared",
                "description": "Navigation target must be filled before live dashboard assembly when drill paths are required.",
            }
        ],
        "datasets": [
            {
                "dataset_id": contract_id,
                "fields": fields,
                "calculated_fields": [],
            }
        ],
    }


def validate_dashboard_relations(relations: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    widgets = {item.get("widget_id") for item in relations.get("widgets") or []}
    charts = {item.get("chart_id") for item in relations.get("charts") or []}
    tabs = {item.get("tab_id") for item in relations.get("tabs") or []}
    controls = []
    selector_parameters: dict[str, list[str]] = {}
    for selector in relations.get("selectors") or []:
        selector_id = selector.get("selector_id") or "selector"
        parameters = _selector_relation_params(selector)
        binding_parameters = _selector_binding_params(selector)
        selector_parameters[str(selector_id)] = parameters
        if not isinstance(selector.get("params"), list):
            issues.append(f"{selector_id}: params must explicitly list every selector parameter")
        if not parameters:
            issues.append(f"{selector_id}: selector must declare one parameter or a complete param_from/param_to pair")
        if len(parameters) != len(set(parameters)):
            issues.append(f"{selector_id}: selector parameters must be unique")
        if parameters != binding_parameters:
            issues.append(
                f"{selector_id}: params must match the param or param_from/param_to binding exactly"
            )
        if not str(selector.get("label") or "").strip():
            issues.append(f"{selector_id}: selector label is required")
        controls.append(selector)
        targets = selector.get("targets") or []
        if not targets:
            issues.append(f"{selector_id}: selector must declare target charts/widgets")
        for target in targets:
            target_id = target.get("target_id")
            if target_id not in widgets and target_id not in charts:
                issues.append(f"{selector_id}: target {target_id} is not a known widget or chart")
            target_param = str(target.get("param") or "").strip()
            if target_param not in parameters:
                issues.append(f"{selector_id}: target parameter {target_param or '<missing>'} is not declared by selector")
        targeted_parameters = {
            str(target.get("param") or "").strip()
            for target in targets
            if isinstance(target, dict)
        }
        missing_target_parameters = [parameter for parameter in parameters if parameter not in targeted_parameters]
        if missing_target_parameters:
            issues.append(
                f"{selector_id}: selector parameters without targets: {', '.join(missing_target_parameters)}"
            )
    filter_keys: list[tuple[str, str]] = []
    for dashboard_filter in relations.get("dashboard_filters") or []:
        filter_id = str(dashboard_filter.get("filter_id") or "dashboard_filter")
        selector_id = str(dashboard_filter.get("selector_id") or "").strip()
        parameter = str(dashboard_filter.get("param") or "").strip()
        filter_keys.append((selector_id, parameter))
        if selector_id not in selector_parameters:
            issues.append(f"{filter_id}: selector_id {selector_id or '<missing>'} is not declared")
            continue
        if parameter not in selector_parameters[selector_id]:
            issues.append(
                f"{filter_id}: parameter {parameter or '<missing>'} is not declared by {selector_id}"
            )
        for target_id in dashboard_filter.get("targets") or []:
            if target_id not in widgets and target_id not in charts:
                issues.append(f"{filter_id}: target {target_id} is not a known widget or chart")
    if len(filter_keys) != len(set(filter_keys)):
        issues.append("dashboard filters must be unique by selector_id and param")
    for selector_id, parameters in selector_parameters.items():
        missing_filter_parameters = [
            parameter
            for parameter in parameters
            if (selector_id, parameter) not in filter_keys
        ]
        if missing_filter_parameters:
            issues.append(
                f"{selector_id}: selector parameters without dashboard filters: "
                + ", ".join(missing_filter_parameters)
            )
    selector_result = validate_selector_controls(controls, target=SELECTOR_ROW_WIDTH_TARGET)
    issues.extend(selector_result.issues)
    chart_ids = {chart.get("chart_id") for chart in relations.get("charts") or []}
    for widget in relations.get("widgets") or []:
        tab_id = widget.get("tab_id")
        if tab_id and tab_id not in tabs:
            issues.append(f"{widget.get('widget_id')}: tab_id {tab_id} is not declared in tabs")
        chart_id = widget.get("chart_id")
        if chart_id and chart_id not in chart_ids:
            issues.append(f"{widget.get('widget_id')}: chart_id {chart_id} is not declared in charts")
        if widget.get("route") != "editor_js_control":
            metadata = widget.get("native_metadata") or {}
            if not metadata.get("title"):
                issues.append(f"{widget.get('widget_id')}: native_metadata.title is required")
            if metadata.get("hideTitle") is not False:
                issues.append(f"{widget.get('widget_id')}: native_metadata.hideTitle must be false")
            if metadata.get("enableHint") is True and not metadata.get("hint"):
                issues.append(f"{widget.get('widget_id')}: native_metadata.hint is required when enableHint is true")
    for relation in relations.get("chart_relations") or []:
        source = relation.get("source_chart_id")
        target = relation.get("target_chart_id")
        if source and source not in charts:
            issues.append(f"chart relation source {source} is not declared in charts")
        if target and target not in charts:
            issues.append(f"chart relation target {target} is not declared in charts")
    for relation in relations.get("navigation_relations") or []:
        source = relation.get("source_id")
        target = relation.get("target_id")
        if source and source not in widgets and source not in charts:
            issues.append(f"navigation source {source} is not a known widget or chart")
        if target and target not in widgets and target not in charts:
            issues.append(f"navigation target {target} is not a known widget or chart")
    return ValidationResult(ok=not issues, issues=issues)


def render_relation_summary_markdown(relations: dict[str, Any]) -> str:
    lines = ["## Object Relations", ""]
    lines.append("### Selector Relations")
    selectors = relations.get("selectors") or []
    if not selectors:
        lines.append("- No selectors declared.")
    for selector in selectors:
        targets = ", ".join(
            f"`{target.get('target_id')}` ({target.get('target_kind')})"
            for target in selector.get("targets") or []
        ) or "none"
        parameters = ", ".join(f"`{parameter}`" for parameter in _selector_relation_params(selector)) or "none"
        lines.append(
            f"- `{selector.get('selector_id')}` params {parameters} targets {targets}; "
            f"label `{selector.get('labelPlacement')}`, width `{selector.get('width')}`."
        )
    lines.extend(["", "### Dataset And Field Dependencies"])
    for chart in relations.get("charts") or []:
        datasets = ", ".join(f"`{item}`" for item in chart.get("dataset_dependencies") or []) or "none"
        fields = ", ".join(f"`{item}`" for item in chart.get("field_dependencies") or []) or "none"
        calculated = ", ".join(f"`{item}`" for item in chart.get("calculated_field_dependencies") or []) or "none"
        lines.append(
            f"- Chart `{chart.get('chart_id')}` uses datasets {datasets}, fields {fields}, calculated fields {calculated}."
        )
    lines.extend(["", "### Layout"])
    blueprint = relations.get("layout_blueprint") or {}
    if blueprint:
        flow = ", ".join(f"`{item}`" for item in blueprint.get("content_flow") or []) or "not declared"
        lines.append(
            f"- Dashboard type `{blueprint.get('dashboard_type')}` uses selector zone "
            f"`{blueprint.get('selector_zone')}` and content flow {flow}."
        )
    for widget in relations.get("widgets") or []:
        layout = widget.get("layout") or {}
        metadata = widget.get("native_metadata") or {}
        lines.append(
            f"- Widget `{widget.get('widget_id')}` on tab `{widget.get('tab_id')}` uses width `{layout.get('width')}`"
            f" and native title `{metadata.get('title', '')}`."
        )
    lines.extend(["", "### Chart And Navigation Relations"])
    for relation in relations.get("chart_relations") or []:
        lines.append(
            f"- Chart relation `{relation.get('relation_kind')}` from "
            f"`{relation.get('source_chart_id')}` to `{relation.get('target_chart_id') or 'none'}`."
        )
    for relation in relations.get("navigation_relations") or []:
        lines.append(
            f"- Navigation `{relation.get('relation_kind')}` from `{relation.get('source_id')}` to `{relation.get('target_id') or 'none'}`."
        )
    return "\n".join(lines) + "\n"


def _field_name(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("name") or item.get("field") or item.get("guid") or item.get("field_guid")
    else:
        value = item
    return str(value or "").strip()


def _technical_token(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_") or "param"


def _selector_id(parameters: list[str]) -> str:
    return "selector_" + "_".join(_technical_token(parameter) for parameter in parameters)


def _selector_relation(
    *,
    selector_id: str,
    widget_id: str,
    parameters: list[str],
    source_fields: list[str],
    contract: dict[str, Any],
) -> dict[str, Any]:
    label = str(contract.get("label") or parameters[0].replace("_", " ").title())
    relation: dict[str, Any] = {
        "selector_id": selector_id,
        "params": parameters,
        "label": label,
        "labelPlacement": "left",
        "width": "94%",
        "row": "row-1",
        "source_fields": source_fields,
        "field_dependency_status": (
            "validated"
            if len(source_fields) == len(parameters)
            else "schema_unavailable"
        ),
        "targets": [
            {"target_id": widget_id, "target_kind": "widget", "param": parameter}
            for parameter in parameters
        ],
    }
    if len(parameters) == 1:
        relation["param"] = parameters[0]
        relation["source_field"] = source_fields[0] if source_fields else ""
    elif contract.get("param_from") and contract.get("param_to"):
        relation["param_from"] = contract["param_from"]
        relation["param_to"] = contract["param_to"]
    if contract:
        relation["contract"] = {
            "schema_version": contract.get("schema_version"),
            "family": contract.get("family"),
            "option_source": contract.get("option_source"),
            "reset_behavior": contract.get("reset_behavior"),
        }
    return relation


def _selector_relation_params(selector: dict[str, Any]) -> list[str]:
    declared = selector.get("params")
    if isinstance(declared, list):
        return [str(value).strip() for value in declared if str(value).strip()]
    return _selector_binding_params(selector)


def _selector_binding_params(selector: dict[str, Any]) -> list[str]:
    param_from = str(selector.get("param_from") or "").strip()
    param_to = str(selector.get("param_to") or "").strip()
    if param_from or param_to:
        return [value for value in (param_from, param_to) if value]
    parameter = str(selector.get("param") or "").strip()
    return [parameter] if parameter else []
