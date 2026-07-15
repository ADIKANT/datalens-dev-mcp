from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChartResolution:
    requested: str
    status: str
    approved_alternative: str
    reason: str


APPROVED_CHARTS: dict[str, str] = {
    "kpi_value_only": "Single KPI value with title and hint.",
    "kpi_value_delta": "KPI with current value and an explicitly declared comparator delta.",
    "kpi_value_sparkline": "KPI value with compact trend context.",
    "kpi_value_delta_sparkline": "KPI value with trend and an explicitly declared comparator delta.",
    "line_chart": "Continuous time trend.",
    "multiline_chart": "Two or more comparable time series.",
    "area_completion": "Completion or accumulation over time.",
    "vertical_bar_time_bucket": "Discrete period bucket comparison.",
    "combo_time_series_combo": "Bar and line in one time frame.",
    "horizontal_bar": "Sorted category comparison or ranking.",
    "grouped_bar": "Side-by-side category comparison.",
    "stacked_100": "Part-to-whole comparison across categories.",
    "bullet_assignees": "Target versus actual comparison with strict context.",
    "heatmap": "Two-dimensional matrix intensity.",
    "waterfall": "Contribution or bridge analysis.",
    "funnel_snapshot": "Ordered funnel stage drop-off.",
    "sankey_status_flow": "Approved only when flow volumes and stages are explicit.",
    "histogram": "Numeric distribution bins.",
    "box_plot": "Distribution summary by category.",
    "scatter": "Relationship between two numeric measures.",
    "bubble": "Relationship with an explicit third magnitude.",
    "pie": "Small part-to-whole set when donut center is unnecessary.",
    "donut": "Small part-to-whole set with optional center value.",
    "treemap": "Hierarchical part-to-whole or size by category.",
    "table_node": "Default exact-value JavaScript Table route.",
    "resource_schedule_exception": "Explicit-only bounded resource-by-time schedule with declared conflict semantics.",
    "md_methodology_block": "Methodology or explanatory Markdown.",
    "md_section_header": "Markdown section divider.",
    "md_dashboard_owner": "Dashboard owner metadata block.",
    "md_contact_block": "Contact metadata block.",
    "md_requirements_link_block": "Requirements link block.",
    "md_source_notes": "Source notes block.",
    "single_select_dropdown": "Static single-select control.",
    "multi_select_dropdown": "Static multi-select control.",
    "search_selector": "Searchable selector control.",
    "date_range_selector": "Date range selector control.",
    "selector_family_static": "Static selector family.",
    "selector_family_dynamic": "Dynamic selector family backed by sources.",
}


REFERENCE_ONLY_CHARTS: dict[str, ChartResolution] = {
    "grouped_sticky_table_exception": ChartResolution(
        "grouped_sticky_table_exception",
        "reference_only",
        "table_node",
        "Advanced HTML tables fail the current runtime contract; use native table_node/head.sub instead.",
    ),
    "table_pivot_advanced_exception": ChartResolution(
        "table_pivot_advanced_exception",
        "reference_only",
        "table_node",
        "Advanced HTML pivot generation is blocked; use native table_pivot_js with nested head.sub.",
    ),
}


REMOVED_CHARTS: dict[str, ChartResolution] = {
    "g02_kpi_status_blocked": ChartResolution(
        "g02_kpi_status_blocked", "removed", "kpi_value_sparkline", "Standalone KPI status cards are not a standard family."
    ),
    "kpi_status_blocked": ChartResolution(
        "kpi_status_blocked", "removed", "kpi_value_sparkline", "Standalone KPI status cards are not a standard family."
    ),
    "g05_kpi_no_data": ChartResolution(
        "g05_kpi_no_data", "removed", "kpi_value_sparkline", "No-data is a state of KPI cards, not a separate chart."
    ),
    "kpi_no_data": ChartResolution(
        "kpi_no_data", "removed", "kpi_value_sparkline", "No-data is a state of KPI cards, not a separate chart."
    ),
    "g06_kpi_strip_composite": ChartResolution(
        "g06_kpi_strip_composite", "removed", "kpi_value_delta", "Composite KPI strips are not selected automatically."
    ),
    "kpi_strip_composite": ChartResolution(
        "kpi_strip_composite", "removed", "kpi_value_delta", "Composite KPI strips are not selected automatically."
    ),
    "g13_slope_type_open": ChartResolution(
        "g13_slope_type_open", "manual_review", "line_chart", "Slope charts require explicit before-after evidence."
    ),
    "slope_chart": ChartResolution(
        "slope_chart", "manual_review", "line_chart", "Slope charts require explicit before-after evidence."
    ),
    "g14_bump_priority_rank": ChartResolution(
        "g14_bump_priority_rank", "manual_review", "horizontal_bar", "Bump charts are not normal routing; prefer ranked bars."
    ),
    "bump_chart": ChartResolution(
        "bump_chart", "manual_review", "horizontal_bar", "Bump charts are not normal routing; prefer ranked bars."
    ),
    "g15_streamgraph_status_category": ChartResolution(
        "g15_streamgraph_status_category", "removed", "area_completion", "Streamgraph adds complexity without decision value here."
    ),
    "streamgraph_status_category": ChartResolution(
        "streamgraph_status_category", "removed", "area_completion", "Streamgraph adds complexity without decision value here."
    ),
    "g16_sparkline_created": ChartResolution(
        "g16_sparkline_created", "removed", "area_completion", "Standalone sparkline duplicates area or KPI trend use."
    ),
    "sparkline_created": ChartResolution(
        "sparkline_created", "removed", "area_completion", "Standalone sparkline duplicates area or KPI trend use."
    ),
    "g18_timeline_created": ChartResolution(
        "g18_timeline_created", "removed", "line_chart", "Timeline is not a standard operational chart."
    ),
    "timeline_created": ChartResolution(
        "timeline_created", "removed", "line_chart", "Timeline is not a standard operational chart."
    ),
    "g19_small_multiple_priority": ChartResolution(
        "g19_small_multiple_priority", "removed", "grouped_bar", "Small multiples are not a standard automatic choice."
    ),
    "small_multiple_priority": ChartResolution(
        "small_multiple_priority", "removed", "grouped_bar", "Small multiples are not a standard automatic choice."
    ),
    "g23_stacked_bar_status_type": ChartResolution(
        "g23_stacked_bar_status_type", "removed", "stacked_100", "Plain stacked bars are replaced by 100 percent stacks or grouped bars."
    ),
    "stacked_bar_status_type": ChartResolution(
        "stacked_bar_status_type", "removed", "stacked_100", "Plain stacked bars are replaced by 100 percent stacks or grouped bars."
    ),
    "g25_lollipop_epics": ChartResolution(
        "g25_lollipop_epics", "removed", "horizontal_bar", "Lollipop charts are removed from standard routing."
    ),
    "lollipop_epics": ChartResolution(
        "lollipop_epics", "removed", "horizontal_bar", "Lollipop charts are removed from standard routing."
    ),
    "g27_dumbbell_type_created_completed": ChartResolution(
        "g27_dumbbell_type_created_completed", "removed", "grouped_bar", "Dumbbell charts are removed from standard routing."
    ),
    "dumbbell_type_created_completed": ChartResolution(
        "dumbbell_type_created_completed", "removed", "grouped_bar", "Dumbbell charts are removed from standard routing."
    ),
    "g41_density_age": ChartResolution(
        "g41_density_age", "removed", "histogram", "Density plots are replaced by histogram or box plot."
    ),
    "density_age": ChartResolution(
        "density_age", "removed", "histogram", "Density plots are replaced by histogram or box plot."
    ),
    "g43_jitter_priority_age": ChartResolution(
        "g43_jitter_priority_age", "removed", "scatter", "Jitter plots are replaced by clearer relationship or distribution charts."
    ),
    "jitter_priority_age": ChartResolution(
        "jitter_priority_age", "removed", "scatter", "Jitter plots are replaced by clearer relationship or distribution charts."
    ),
    "g44_beeswarm_priority_age": ChartResolution(
        "g44_beeswarm_priority_age", "removed", "box_plot", "Beeswarm plots are replaced by box plot or histogram."
    ),
    "beeswarm_priority_age": ChartResolution(
        "beeswarm_priority_age", "removed", "box_plot", "Beeswarm plots are replaced by box plot or histogram."
    ),
    "g60_table_standard": ChartResolution(
        "g60_table_standard", "removed", "table_node", "Table aliases collapse into the default table_node route."
    ),
    "g61_table_custom_bars": ChartResolution(
        "g61_table_custom_bars", "removed", "table_node", "Bar-in-table variants are formatting, not chart families."
    ),
    "g62_registry_table": ChartResolution(
        "g62_registry_table", "removed", "table_node", "Registry tables collapse into table_node."
    ),
    "g63_summary_rows_table": ChartResolution(
        "g63_summary_rows_table", "removed", "table_node", "Summary rows are table configuration, not a chart family."
    ),
    "g64_status_heat_table": ChartResolution(
        "g64_status_heat_table", "removed", "table_node", "Status heat tables are table configuration, not a chart family."
    ),
    "g65_table_sparkline": ChartResolution(
        "g65_table_sparkline", "removed", "table_node", "Table sparklines are not a generated chart family."
    ),
}

ALIASES: dict[str, str] = {
    "g01_kpi_single_total": "kpi_value_only",
    "g03_kpi_delta_completed": "kpi_value_delta",
    "g04_kpi_sparkline_created": "kpi_value_sparkline",
    "g10_line_created": "line_chart",
    "g11_multiline_created_completed": "multiline_chart",
    "g12_area_completion": "area_completion",
    "g17_combo_bar_line": "combo_time_series_combo",
    "g20_vertical_bar_created": "vertical_bar_time_bucket",
    "g21_horizontal_bar_status": "horizontal_bar",
    "g22_grouped_bar_type_status": "grouped_bar",
    "g24_stacked_100_priority": "stacked_100",
    "g26_bullet_assignees": "bullet_assignees",
    "g28_heatmap_status_type": "heatmap",
    "g29_waterfall_flow": "waterfall",
    "g30_funnel_status_category": "funnel_snapshot",
    "g31_sankey_status_flow": "sankey_status_flow",
    "g40_histogram_age": "histogram",
    "g42_boxplot_age_type": "box_plot",
    "g45_scatter_issue_age_cycle": "scatter",
    "g46_bubble_assignee_load": "bubble",
    "g50_donut_priority": "donut",
    "g51_pie_issue_type": "pie",
    "g52_treemap_epics": "treemap",
    "g70_static_selector": "selector_family_static",
    "g71_dynamic_selector": "selector_family_dynamic",
    "g72_date_controls": "date_range_selector",
    "g73_markdown_section": "md_section_header",
}


def normalize_family(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def resolve_chart_family(value: str | None) -> ChartResolution:
    requested = normalize_family(value)
    if not requested:
        return ChartResolution("", "approved", "kpi_value_sparkline", "Default KPI without implicit comparator.")
    if requested in REMOVED_CHARTS:
        return REMOVED_CHARTS[requested]
    if requested in REFERENCE_ONLY_CHARTS:
        return REFERENCE_ONLY_CHARTS[requested]
    family = ALIASES.get(requested, requested)
    if family in APPROVED_CHARTS:
        return ChartResolution(requested, "approved", family, APPROVED_CHARTS[family])
    return ChartResolution(
        requested,
        "manual_review",
        "table_node",
        "Unknown chart family; use table_node until the analytical task is classified.",
    )
