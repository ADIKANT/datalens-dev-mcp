from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json


POLICY_RESOURCE = "config/route_selection_policy_v5.json"
POLICY_VERSION = "2026-07-13.route_selection_policy_v5"
WIZARD_NATIVE_ROUTE = "wizard_native"
WIZARD_MAP_ALIAS = "wizard_map_native"
QL_EXPLICIT_ROUTE = "ql_explicit"

SUPPORTED_WIZARD_VISUALIZATION_IDS = (
    "metric",
    "flatTable",
    "pivotTable",
    "line",
    "area",
    "area100p",
    "column",
    "column100p",
    "bar",
    "bar100p",
    "combined-chart",
    "pie",
    "donut",
    "scatter",
    "treemap",
    "geolayer",
)

_FALLBACK_FAMILY_TO_VISUALIZATION = {
    "kpi_value_only": "metric",
    "kpi_value_delta": "metric",
    "table_node": "flatTable",
    "flat_table": "flatTable",
    "pivot_table": "pivotTable",
    "pivot_table_node": "pivotTable",
    "line_chart": "line",
    "multiline_chart": "line",
    "area_completion": "area",
    "area_100p": "area100p",
    "vertical_bar_time_bucket": "column",
    "stacked_100": "column100p",
    "horizontal_stacked_100": "bar100p",
    "horizontal_bar": "bar",
    "grouped_bar": "bar",
    "combo_time_series_combo": "combined-chart",
    "pie": "pie",
    "donut": "donut",
    "scatter": "scatter",
    "bubble": "scatter",
    "treemap": "treemap",
    "native_map_geo_widget": "geolayer",
    "wizard_map_native": "geolayer",
}

_FALLBACK_JS_GAPS = {
    "box_plot": "wizard_has_no_box_plot_semantics",
    "bullet_assignees": "wizard_has_no_bullet_chart_semantics",
    "funnel_snapshot": "wizard_has_no_funnel_semantics",
    "heatmap": "wizard_has_no_heatmap_matrix_semantics",
    "histogram": "wizard_has_no_histogram_semantics",
    "kpi_value_delta_sparkline": "composite_kpi_with_sparkline",
    "kpi_value_sparkline": "composite_kpi_with_sparkline",
    "resource_schedule_exception": "custom_resource_schedule_interaction",
    "sankey_status_flow": "wizard_has_no_sankey_semantics",
    "table_pivot_js": "grouped_or_pinned_table_requires_custom_semantics",
    "waterfall": "wizard_has_no_waterfall_semantics",
}


@dataclass(frozen=True)
class RegisteredRouteDecision:
    route: str
    visualization_id: str
    selection_origin: str
    selection_reason: str
    capability_gap: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "route": self.route,
            "visualization_id": self.visualization_id,
            "selection_origin": self.selection_origin,
            "selection_reason": self.selection_reason,
            "capability_gap": self.capability_gap,
        }


@lru_cache(maxsize=1)
def load_route_policy_registry() -> dict[str, Any]:
    try:
        return resource_json(POLICY_RESOURCE)
    except RuntimeResourceError:
        return {
            "schema_version": POLICY_VERSION,
            "wizard_visualizations": {},
            "js_capability_gaps": dict(_FALLBACK_JS_GAPS),
        }


def normalize_creation_route(route: str) -> str:
    normalized = str(route or "").strip()
    aliases = {
        WIZARD_MAP_ALIAS: WIZARD_NATIVE_ROUTE,
        "wizard": WIZARD_NATIVE_ROUTE,
        "ql": QL_EXPLICIT_ROUTE,
        "ql_chart": QL_EXPLICIT_ROUTE,
        "advanced_editor_js": "editor_advanced",
    }
    return aliases.get(normalized, normalized)


def supported_wizard_visualization_ids() -> tuple[str, ...]:
    configured = tuple((load_route_policy_registry().get("wizard_visualizations") or {}).keys())
    return configured or SUPPORTED_WIZARD_VISUALIZATION_IDS


def is_supported_wizard_visualization(visualization_id: str) -> bool:
    return str(visualization_id or "").strip() in supported_wizard_visualization_ids()


def visualization_for_family(family: str, *, semantic_text: str = "") -> str:
    normalized = str(family or "").strip()
    if normalized == "stacked_100" and any(
        token in str(semantic_text or "").lower()
        for token in ("horizontal", "горизонт", "bar100p")
    ):
        return "bar100p"
    configured = load_route_policy_registry().get("wizard_visualizations") or {}
    for visualization_id, spec in configured.items():
        if normalized in (spec.get("semantic_families") or []):
            return str(visualization_id)
    return _FALLBACK_FAMILY_TO_VISUALIZATION.get(normalized, "")


def capability_gap_for_family(family: str) -> str:
    configured = load_route_policy_registry().get("js_capability_gaps") or {}
    return str(configured.get(family) or _FALLBACK_JS_GAPS.get(family) or "")


def decide_registered_route(
    family: str,
    *,
    semantic_text: str = "",
    explicit_route: str = "",
    existing_route: str = "",
    existing_visualization_id: str = "",
) -> RegisteredRouteDecision:
    normalized_existing = normalize_creation_route(existing_route)
    if normalized_existing:
        if normalized_existing == WIZARD_NATIVE_ROUTE:
            return RegisteredRouteDecision(
                route=WIZARD_NATIVE_ROUTE,
                visualization_id=existing_visualization_id or visualization_for_family(family, semantic_text=semantic_text),
                selection_origin="fresh_saved_readback",
                selection_reason="Existing Wizard technology and visualization are preserved.",
            )
        return RegisteredRouteDecision(
            route=normalized_existing,
            visualization_id="",
            selection_origin="fresh_saved_readback",
            selection_reason="Existing object technology is preserved.",
        )

    normalized_explicit = normalize_creation_route(explicit_route)
    if normalized_explicit == QL_EXPLICIT_ROUTE:
        return RegisteredRouteDecision(
            route=QL_EXPLICIT_ROUTE,
            visualization_id="",
            selection_origin="explicit_user_request",
            selection_reason="QL was directly requested by the user; it is never selected automatically.",
        )
    if normalized_explicit in {"editor_advanced", "editor_table", "editor_markdown", "editor_js_control"}:
        return RegisteredRouteDecision(
            route=normalized_explicit,
            visualization_id="",
            selection_origin="explicit_user_request",
            selection_reason=f"The user explicitly requested {normalized_explicit}.",
            capability_gap="explicit_custom_route" if normalized_explicit == "editor_advanced" else "",
        )
    if normalized_explicit == WIZARD_NATIVE_ROUTE:
        visualization_id = existing_visualization_id or visualization_for_family(family, semantic_text=semantic_text)
        return RegisteredRouteDecision(
            route=WIZARD_NATIVE_ROUTE,
            visualization_id=visualization_id or "flatTable",
            selection_origin="explicit_user_request",
            selection_reason="The user explicitly requested native Wizard authoring.",
        )

    if family.startswith("md_"):
        return RegisteredRouteDecision(
            route="editor_markdown",
            visualization_id="",
            selection_origin="specialized_editor_route",
            selection_reason="Markdown remains a dedicated Editor route.",
        )
    if family in {
        "single_select_dropdown",
        "multi_select_dropdown",
        "search_selector",
        "date_range_selector",
        "selector_family_static",
        "selector_family_dynamic",
        "control_node",
    }:
        return RegisteredRouteDecision(
            route="editor_js_control",
            visualization_id="",
            selection_origin="specialized_editor_route",
            selection_reason="Controls remain a dedicated Editor JS control route.",
        )
    gap = capability_gap_for_family(family)
    if gap:
        route = "editor_table" if family == "table_pivot_js" else "editor_advanced"
        return RegisteredRouteDecision(
            route=route,
            visualization_id="",
            selection_origin="registered_capability_gap",
            selection_reason=f"Wizard is not selected because the registered capability gap is {gap}.",
            capability_gap=gap,
        )
    visualization_id = visualization_for_family(family, semantic_text=semantic_text) or "flatTable"
    return RegisteredRouteDecision(
        route=WIZARD_NATIVE_ROUTE,
        visualization_id=visualization_id,
        selection_origin="wizard_first_default",
        selection_reason="Standard visualization creation uses the deterministic Wizard-first policy.",
    )
