from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec, route_for_chart_family
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT
from datalens_dev_mcp.pipeline.visual_decisions import decide_chart


FAMILY_ROUTE = {
    "table_node": "editor_table",
    "md_methodology_block": "editor_markdown",
    "md_section_header": "editor_markdown",
    "md_dashboard_owner": "editor_markdown",
    "md_contact_block": "editor_markdown",
    "md_requirements_link_block": "editor_markdown",
    "md_source_notes": "editor_markdown",
    "single_select_dropdown": "editor_js_control",
    "multi_select_dropdown": "editor_js_control",
    "search_selector": "editor_js_control",
    "date_range_selector": "editor_js_control",
    "selector_family_static": "editor_js_control",
    "selector_family_dynamic": "editor_js_control",
}


REMOVED_REQUEST_TERMS = {
    "kpi status": "g02_kpi_status_blocked",
    "kpi no data": "g05_kpi_no_data",
    "kpi strip": "g06_kpi_strip_composite",
    "slope": "g13_slope_type_open",
    "bump": "g14_bump_priority_rank",
    "streamgraph": "g15_streamgraph_status_category",
    "standalone sparkline": "g16_sparkline_created",
    "timeline": "g18_timeline_created",
    "small multiple": "g19_small_multiple_priority",
    "stacked bar": "g23_stacked_bar_status_type",
    "lollipop": "g25_lollipop_epics",
    "dumbbell": "g27_dumbbell_type_created_completed",
    "density": "g41_density_age",
    "jitter": "g43_jitter_priority_age",
    "beeswarm": "g44_beeswarm_priority_age",
    "custom bars table": "g61_table_custom_bars",
    "table sparkline": "g65_table_sparkline",
}


def infer_family_and_route(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for term, removed_family in REMOVED_REQUEST_TERMS.items():
        if term in lowered:
            alternative = resolve_chart_family(removed_family).approved_alternative
            return alternative, route_for_chart_family(alternative)
    if any(word in lowered for word in ("map", "geo", "latitude", "longitude", "geopoint", "geopolygon")):
        return "native_map_geo_widget", "wizard_native"
    if any(word in lowered for word in ("table", "registry", "lookup", "detail")):
        return "table_node", route_for_chart_family("table_node")
    if any(word in lowered for word in ("selector", "filter", "control")):
        return "single_select_dropdown", route_for_chart_family("single_select_dropdown")
    if any(word in lowered for word in ("markdown", "note", "methodology", "owner", "header")):
        return "md_methodology_block", route_for_chart_family("md_methodology_block")
    if any(word in lowered for word in ("trend", "time", "daily", "weekly", "month")):
        return "line_chart", route_for_chart_family("line_chart")
    if any(word in lowered for word in ("rank", "top", "compare", "bar")):
        return "horizontal_bar", route_for_chart_family("horizontal_bar")
    return "kpi_value_only", route_for_chart_family("kpi_value_only")


def build_governance_brief(*, requirements_text: str, data_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    family, route = infer_family_and_route(requirements_text)
    decision_record = decide_chart(
        chart_id="CD-001",
        business_question=requirements_text,
        audience=["business owner", "analyst"],
        data_shape={"fields": sorted((data_profile or {}).get("fields", []))},
        requested_family=family,
        source_evidence_refs=["requirements_text"],
    )
    family = decision_record.selected_family
    route = decision_record.selected_route
    param_spec = get_chart_param_spec(family)
    fields = sorted((data_profile or {}).get("fields", []))
    metric_id = "MET-001"
    decision_id = "CD-001"
    return {
        "schema_version": "2026-05-25.dashboard_brief.v1",
        "dashboard_name": _first_title(requirements_text),
        "audience": ["business owner", "analyst"],
        "decision_action": "Monitor the requested process and decide follow-up action.",
        "requirements": [{"requirement_id": "REQ-001", "text": requirements_text[:1000]}],
        "data_contract": {
            "contract_id": "DATA-001",
            "fields": fields,
            "source_status": "synthetic_or_user_supplied",
        },
        "chart_decisions": [
            {
                "decision_id": decision_id,
                "metric_id": metric_id,
                "widget_id": "widget_001",
                "family": family,
                "route": route,
                "entry_type": ROUTE_CONTRACT.routes[route].entry_type,
                "status": "approved_with_geo_evidence_required" if family == "native_map_geo_widget" else "approved",
                "parameter_spec": param_spec.brief(),
                "governance_decision": {
                    "chart_family_decided_by": "datalens-dataviz-governance",
                    "approved": True,
                    "decision_id": decision_id,
                    "selected_family": family,
                    "approved_route": route,
                },
                "chart_decision_record": decision_record.to_dict(),
                "renderer_visual_spec": decision_record.renderer_visual_spec.to_dict(),
            }
        ],
    }


def _first_title(text: str) -> str:
    for line in text.splitlines():
        compact = line.strip("# -:\t ")
        if compact:
            return compact[:80]
    words = re.findall(r"\w+", text)[:6]
    return " ".join(words) or "Synthetic Dashboard"
