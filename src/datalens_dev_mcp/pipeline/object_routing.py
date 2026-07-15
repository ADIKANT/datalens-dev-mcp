from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT
from datalens_dev_mcp.pipeline.route_registry import QL_EXPLICIT_ROUTE, decide_registered_route


@dataclass(frozen=True)
class OperationRoute:
    operation_kind: str
    route: str
    object_kind: str
    allowed_use: str
    required_before: tuple[str, ...] = ()


OPERATION_ROUTES: dict[str, OperationRoute] = {
    "advanced_editor_chart": OperationRoute(
        operation_kind="advanced_editor_chart",
        route="editor_advanced",
        object_kind="editor_chart",
        allowed_use="Custom non-map JavaScript visual widgets.",
        required_before=("dataset_operation",),
    ),
    "wizard_native_chart": OperationRoute(
        operation_kind="wizard_native_chart",
        route="wizard_native",
        object_kind="wizard_chart",
        allowed_use="Standard native DataLens Wizard visualizations; geolayer requires validated geo evidence.",
        required_before=("dataset_operation",),
    ),
    "ql_explicit_chart": OperationRoute(
        operation_kind="ql_explicit_chart",
        route="ql_explicit",
        object_kind="ql_chart",
        allowed_use="QL read/create/update after a direct user request and explicit payload or fresh saved seed.",
        required_before=("explicit_user_request", "explicit_payload_or_fresh_saved_ql_seed"),
    ),
    "dataset_operation": OperationRoute(
        operation_kind="dataset_operation",
        route="dataset",
        object_kind="dataset",
        allowed_use="Dataset, field, calculated field, measure, dimension, and aggregation work.",
    ),
    "connector_operation": OperationRoute(
        operation_kind="connector_operation",
        route="connector",
        object_kind="connection",
        allowed_use="Connection and connector configuration work before datasets.",
    ),
    "dashboard_relation_operation": OperationRoute(
        operation_kind="dashboard_relation_operation",
        route="dashboard_relation",
        object_kind="dashboard",
        allowed_use="Dashboard layout, selector, chart, widget, and object relation work.",
    ),
}


ADVANCED_TERMS = ("advanced editor", "javascript", "js chart", "custom html", "custom svg", "custom visual", "custom interaction")
WIZARD_TERMS = ("wizard", "native chart", "native datalens", "native visualization")
MAP_TERMS = ("map", "geo", "latitude", "longitude", "geopoint", "geopolygon", "region", "polygon")
QL_TERMS = ("createqlchart", "updateqlchart", "deleteqlchart", "getqlchart", "graph_ql_node", "table_ql_node", "ql chart")
CONNECTOR_TERMS = ("connector", "connection", "connect to", "database connection", "oauth connection")
DATASET_TERMS = (
    "dataset",
    "calculated field",
    "calc field",
    "field config",
    "measure",
    "dimension",
    "aggregation",
)
DASHBOARD_RELATION_TERMS = (
    "dashboard layout",
    "dashboard relation",
    "object relation",
    "widget relation",
    "selector relation",
    "selector wiring",
    "tab layout",
)
REMOVED_CHART_TERMS = {
    "kpi status": "kpi_status_blocked",
    "kpi no data": "kpi_no_data",
    "kpi strip": "kpi_strip_composite",
    "slope": "slope_chart",
    "bump": "bump_chart",
    "streamgraph": "streamgraph_status_category",
    "standalone sparkline": "sparkline_created",
    "timeline": "timeline_created",
    "small multiple": "small_multiple_priority",
    "stacked bar": "stacked_bar_status_type",
    "lollipop": "lollipop_epics",
    "dumbbell": "dumbbell_type_created_completed",
    "density": "density_age",
    "jitter": "jitter_priority_age",
    "beeswarm": "beeswarm_priority_age",
}


def route_datalens_operation(
    *,
    requirements_text: str,
    explicit_route: str | None = None,
    dataset_schema: dict[str, Any] | list[Any] | None = None,
    required_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic high-level route decision for DataLens work."""
    lowered = requirements_text.lower()
    explicit = (explicit_route or "").lower().strip()

    if _mentions_ql(lowered) or explicit in {"ql", "ql_chart", "ql_explicit"}:
        decision = _ql_explicit_decision()
    elif _contains_any(lowered, CONNECTOR_TERMS) or explicit in {"connector", "connection"}:
        decision = _decision("connector_operation", status="approved", reason="Connector work is a first-class prerequisite.")
    elif _contains_any(lowered, DATASET_TERMS) or explicit in {"dataset", "field", "calculated_field"}:
        decision = _decision(
            "dataset_operation",
            status="approved",
            reason="Dataset, field, and aggregation changes are not hidden in chart code.",
        )
    elif _contains_any(lowered, DASHBOARD_RELATION_TERMS) or explicit in {"dashboard_relation", "layout"}:
        decision = _decision(
            "dashboard_relation_operation",
            status="approved",
            reason="Dashboard object relations are handled separately from chart code.",
        )
    elif explicit in {"advanced", "advanced_editor", "editor_advanced", "javascript"} or _contains_any(lowered, ADVANCED_TERMS):
        decision = _standard_decision(lowered, force_editor=True)
    elif _mentions_map(lowered):
        decision = _wizard_decision(lowered=lowered, explicit=explicit)
    elif explicit in {"wizard", "wizard_native", "wizard_map_native"} or _contains_any(lowered, WIZARD_TERMS):
        decision = _standard_decision(lowered, force_wizard=True)
    else:
        decision = _standard_decision(lowered)

    if decision["operation_kind"] in {"advanced_editor_chart", "wizard_native_chart"}:
        field_validation = validate_field_availability(required_fields or [], dataset_schema)
        decision["field_validation"] = field_validation
        if field_validation["status"] == "blocked_missing_fields":
            decision["status"] = "blocked_missing_fields"
            decision["reason"] = "Required fields are absent from the supplied dataset schema."
    return decision


def validate_field_availability(
    required_fields: list[str],
    dataset_schema: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    available = set(_extract_field_names(dataset_schema))
    required = [field for field in required_fields if field]
    if not required:
        return {"status": "not_requested", "required_fields": [], "matched_fields": [], "missing_fields": []}
    if not available:
        return {
            "status": "schema_unavailable",
            "required_fields": required,
            "matched_fields": [],
            "missing_fields": [],
        }
    matched = [field for field in required if field in available]
    missing = [field for field in required if field not in available]
    return {
        "status": "blocked_missing_fields" if missing else "validated",
        "required_fields": required,
        "matched_fields": matched,
        "missing_fields": missing,
    }


def routing_model_document() -> dict[str, Any]:
    return {
        "schema_version": "2026-07-13.datalens_operation_routing.v3",
        "operation_routes": {name: asdict(route) for name, route in OPERATION_ROUTES.items()},
        "closed_editor_routes": sorted(ROUTE_CONTRACT.routes),
        "chart_creation_policy": {
            "wizard_native_chart": "Wizard-first standard visualizations; geolayer needs geo evidence",
            "advanced_editor_chart": "JavaScript only for explicit requests or registered capability gaps",
            "ql_explicit_chart": "QL read/create/update only after a direct user request",
        },
        "rules": [
            "Choose object operation kind before choosing a chart family.",
            "Create or validate connector and dataset objects before chart payloads.",
            "Represent calculated fields explicitly in dataset configs.",
            "Standard creates map to wizard_native before transport; no runtime fallback is attempted.",
            "QL is never selected automatically or as a fallback.",
            "Return a targeted question when the business goal or data shape is insufficient.",
        ],
    }


def _standard_decision(lowered: str, *, force_editor: bool = False, force_wizard: bool = False) -> dict[str, Any]:
    removed = _removed_chart_decision(lowered)
    if removed:
        return removed
    family = "kpi_value_only"
    if any(word in lowered for word in ("trend", "time", "daily", "weekly", "month")):
        family = "line_chart"
    elif any(word in lowered for word in ("table", "registry", "lookup", "detail")):
        return _chart_decision(
            "table_node",
            status="approved",
            reason="Exact lookup requests use the route-native table path.",
            force_route="editor_advanced" if force_editor else ("wizard_native" if force_wizard else ""),
        )
    elif any(word in lowered for word in ("selector", "filter", "control")):
        return _chart_decision(
            "single_select_dropdown",
            status="approved",
            reason="Selector requests use the route-native control path.",
            force_route="editor_advanced" if force_editor else "",
        )
    elif "heatmap" in lowered or "matrix" in lowered:
        family = "heatmap"
    elif "waterfall" in lowered:
        family = "waterfall"
    elif "funnel" in lowered:
        family = "funnel_snapshot"
    elif "sankey" in lowered:
        family = "sankey_status_flow"
    elif "histogram" in lowered:
        family = "histogram"
    elif "box plot" in lowered or "boxplot" in lowered:
        family = "box_plot"
    elif "bubble" in lowered:
        family = "bubble"
    elif "scatter" in lowered:
        family = "scatter"
    elif "treemap" in lowered:
        family = "treemap"
    elif "donut" in lowered:
        family = "donut"
    elif "pie" in lowered:
        family = "pie"
    elif "sparkline" in lowered:
        family = "kpi_value_delta_sparkline" if "delta" in lowered else "kpi_value_sparkline"
    elif any(word in lowered for word in ("delta", "target", "plan", "sla", "threshold")):
        family = "kpi_value_delta"
    elif any(word in lowered for word in ("kpi", "metric", "status")):
        family = "kpi_value_only"
    elif any(word in lowered for word in ("rank", "top", "compare", "bar")):
        family = "horizontal_bar"
    elif any(word in lowered for word in ("chart", "visual", "graph")) and not _contains_any(lowered, ADVANCED_TERMS):
        return _chart_decision(
            "table_node",
            status="blocked_question",
            reason="The chart request lacks an analytical goal or data shape.",
            question="Which business question, metric, dimension/date field, and intended action should this chart support?",
        )
    resolved = resolve_chart_family(family).approved_alternative
    return _chart_decision(
        resolved,
        status="approved",
        reason="Chart route is selected deterministically from the Wizard-first registry.",
        force_route="editor_advanced" if force_editor else ("wizard_native" if force_wizard else ""),
    )


def _wizard_decision(*, lowered: str, explicit: str) -> dict[str, Any]:
    del lowered, explicit
    registered = decide_registered_route("native_map_geo_widget")
    decision = _decision(
        "wizard_native_chart",
        status="approved_with_geo_evidence_required",
        reason="Geo/map requests use Wizard geolayer with validated geo evidence.",
        family="native_map_geo_widget",
    )
    decision.update(registered.to_dict())
    return decision


def _chart_decision(
    family: str,
    *,
    status: str,
    reason: str,
    question: str = "",
    force_route: str = "",
) -> dict[str, Any]:
    spec = get_chart_param_spec(family)
    registered = decide_registered_route(family, explicit_route=force_route)
    selected_route = registered.route
    object_kind = {
        "editor_table": "editor_table",
        "editor_markdown": "editor_markdown",
        "editor_js_control": "editor_control",
        "wizard_native": "wizard_chart",
    }.get(selected_route, "editor_chart")
    operation_kind = "wizard_native_chart" if selected_route == "wizard_native" else "advanced_editor_chart"
    decision = _decision(
        operation_kind,
        route_override=selected_route,
        object_kind_override=object_kind,
        status=status,
        reason=reason,
        family=spec.family,
        required_before=OPERATION_ROUTES[operation_kind].required_before,
    )
    decision.update(registered.to_dict())
    decision["parameter_spec"] = spec.brief()
    if question:
        decision["question"] = question
    return decision


def _removed_chart_decision(lowered: str) -> dict[str, Any] | None:
    for term, family in REMOVED_CHART_TERMS.items():
        if term not in lowered:
            continue
        resolution = resolve_chart_family(family)
        if resolution.status == "manual_review":
            return _chart_decision(
                resolution.approved_alternative,
                status="blocked_question",
                reason=(
                    f"Requested chart `{resolution.requested}` requires manual review; "
                    f"use `{resolution.approved_alternative}` only with evidence."
                ),
                question="What before-after or ranking-over-time evidence makes this specialized chart necessary?",
            )
        return _chart_decision(
            resolution.approved_alternative,
            status="approved_alternative",
            reason=f"Requested removed chart `{resolution.requested}` is unreachable; routing to `{resolution.approved_alternative}`.",
        )
    return None


def _ql_explicit_decision() -> dict[str, Any]:
    registered = decide_registered_route("ql_chart", explicit_route=QL_EXPLICIT_ROUTE)
    decision = _decision(
        "ql_explicit_chart",
        status="approved_with_requirements",
        reason="QL was directly requested; automatic QL selection remains forbidden.",
        family="ql_chart",
    )
    decision.update(registered.to_dict())
    return decision


def _decision(
    operation_kind: str,
    *,
    status: str,
    reason: str,
    family: str | None = None,
    route_override: str | None = None,
    object_kind_override: str | None = None,
    required_before: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    route = OPERATION_ROUTES[operation_kind]
    return {
        "schema_version": "2026-07-13.datalens_operation_decision.v3",
        "operation_kind": route.operation_kind,
        "route": route_override or route.route,
        "object_kind": object_kind_override or route.object_kind,
        "family": family,
        "status": status,
        "reason": reason,
        "required_before": list(route.required_before if required_before is None else required_before),
    }


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _mentions_ql(text: str) -> bool:
    return _contains_any(text, QL_TERMS) or re.search(r"\bql\b", text) is not None


def _mentions_map(text: str) -> bool:
    return bool(re.search(r"\b(map|geo)\b", text)) or any(
        term in text for term in MAP_TERMS if term not in {"map", "geo"}
    )


def _extract_field_names(dataset_schema: dict[str, Any] | list[Any] | None) -> list[str]:
    if not dataset_schema:
        return []
    fields = dataset_schema
    if isinstance(dataset_schema, dict):
        fields = dataset_schema.get("fields") or dataset_schema.get("columns") or []
    names: list[str] = []
    for field in fields if isinstance(fields, list) else []:
        if isinstance(field, str):
            names.append(field)
        elif isinstance(field, dict):
            name = field.get("name") or field.get("id") or field.get("guid")
            if name:
                names.append(str(name))
    return names
