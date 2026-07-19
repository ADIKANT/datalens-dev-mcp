from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from datalens_dev_mcp.editor.render_tokens import load_visual_style_tokens


@dataclass(frozen=True)
class RendererVisualSpec:
    family: str
    route: str
    chart_purpose: str
    encoding: dict[str, Any]
    sort: dict[str, Any]
    colors: dict[str, Any]
    axes: dict[str, Any]
    labels: dict[str, Any]
    legend: dict[str, Any]
    gridlines: dict[str, Any]
    tooltip: dict[str, Any]
    kpi_context: dict[str, Any]
    table_formatting: dict[str, Any]
    value_semantics: dict[str, Any]
    formatting: dict[str, Any]
    comparison_context: dict[str, Any]
    responsive_layout: dict[str, Any]
    hint_contract: dict[str, Any]
    layout_contract: dict[str, Any]
    advanced_runtime_budget: dict[str, Any]
    style_tokens: dict[str, Any] = field(default_factory=dict)
    runtime_constraints: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2026-07-19.renderer_visual_spec.v2"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_renderer_visual_spec(
    *,
    family: str,
    route: str,
    analytical_task: str,
    chart_purpose: str = "",
    metric_semantics: dict[str, Any] | None = None,
    negative_requirements: list[str] | None = None,
) -> RendererVisualSpec:
    tokens = load_visual_style_tokens()
    metric_semantics = metric_semantics or {}
    negative_requirements = negative_requirements or []
    comparator = _explicit_comparator(metric_semantics, blocked=negative_requirements)
    colors = _color_spec(analytical_task, metric_semantics, tokens, blocked=negative_requirements)
    sort = _sort_spec(analytical_task)
    labels = _label_spec(analytical_task, family=family, blocked=negative_requirements)
    axes = _axis_spec(analytical_task)
    table_defaults = dict(tokens.get("table_defaults") or {})
    table_formatting = {
        "native_bars": family == "table_node",
        "bar_cell_contract": {
            "type": "bar",
            "min": 0,
            "max": "computed_from_visible_rows",
            "barColor": (tokens.get("colors") or {}).get("focus", "#2f80ed"),
            "barHeight": table_defaults.get("bar_height", "70%"),
            "showLabel": True,
        },
        **table_defaults,
    }
    kpi_context = {
        "comparator": comparator,
        "implicit_comparator_default": False,
        "period_required": analytical_task == "kpi_monitoring",
        "sparkline_allowed": family in {"kpi_value_sparkline", "kpi_value_delta_sparkline"},
    }
    style_colors = dict(tokens.get("colors") or {})
    if "red_green_palette" in negative_requirements:
        style_colors["positive"] = ""
        style_colors["negative"] = ""
    return RendererVisualSpec(
        family=family,
        route=route,
        chart_purpose=chart_purpose or analytical_task,
        encoding={
            "analytical_task": analytical_task,
            "semantic_color_only": True,
            "decorative_styles": False,
        },
        sort=sort,
        colors=colors,
        axes=axes,
        labels=labels,
        legend=_legend_spec(analytical_task, family, blocked=negative_requirements),
        gridlines={
            "show": False,
            "style": "none",
            "reason": "delta_v6_default_off; enable only when numeric lookup is explicitly required",
        },
        tooltip={
            "include_metric_definition": True,
            "include_source_context": True,
            "include_comparator": bool(comparator),
            "include_values": True,
            "comparison_interval_and_value": bool(comparator),
            "avoid_redundant_metric_name": True,
        },
        kpi_context=kpi_context,
        table_formatting=table_formatting,
        value_semantics={
            "missing_label": "N/A",
            "observed_zero_distinct_from_missing": True,
            "null_time_series": "preserve_gaps",
            "future_periods": "exclude_without_observed_rows",
            "source_absence_states": ["ABSENT", "PRESENT_EMPTY", "PRESENT_WITH_DATA"],
        },
        formatting={
            "daily_date": "DD.MM.YY",
            "monthly_date": "MM.YY",
            "number_grouping": "locale",
            "axis_tick_strategy": "nice_1_2_2_5_5_10",
            "axis_integer_ticks_unique": True,
            "label_thinning": "viewport_aware",
        },
        comparison_context={
            "explicit_only": True,
            "options": "contextual_to_selected_period",
            "invalid_option": "nearest_valid_fallback",
            "tab_summary": "single_shared_summary",
            "tooltip": "selected_interval_value_vs_comparison_interval_value",
        },
        responsive_layout={
            "sizing_source": "options.width_and_height",
            "fixed_min_width": False,
            "widget_width_probes_px": [236, 360, 530, 560, 700, 900],
            "dashboard_profiles": ["compact_desktop", "wide_desktop"],
            "horizontal_overflow": "forbidden",
            "content_clipping": "forbidden",
            "theme_profiles": ["light", "dark"],
        },
        hint_contract={
            "content": ["business_meaning", "calculation", "limitations"],
            "forbidden": ["rendering_mechanics", "hover_instructions", "line_style_instructions"],
            "section_header_hint": False,
            "table_column_hint_settings_required": True,
        },
        layout_contract={
            "preserve_existing_geometry": True,
            "semantic_noop_geometry_drift": False,
            "equal_kpi_heights_within_row": True,
            "one_kpi_per_object": True,
            "long_table_internal_scroll": True,
        },
        advanced_runtime_budget={
            "ordinary_wrap_fn_ms": 100,
            "advanced_wrap_fn_ms": 1500,
            "total_runtime_ms": int((tokens.get("limits") or {}).get("advanced_total_runtime_ms") or 3000),
            "pre_shape_before_render": True,
        },
        style_tokens={
            "font": tokens.get("font") or {},
            "colors": style_colors,
            "limits": tokens.get("limits") or {},
        },
        runtime_constraints={
            "no_inline_script": True,
            "no_duplicate_inline_title_hint": True,
            "no_decorative_css": True,
            "selector_values_string": route == "editor_js_control",
            "avoid_heavy_data_multiplication": True,
        },
    )


def normalize_renderer_visual_spec(value: RendererVisualSpec | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, RendererVisualSpec):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _explicit_comparator(metric_semantics: dict[str, Any], *, blocked: list[str]) -> str:
    if "implicit_period_comparison" in blocked:
        return ""
    raw = str(metric_semantics.get("comparator") or metric_semantics.get("baseline") or "").strip().lower()
    allowed = {
        "target",
        "plan",
        "sla",
        "threshold",
        "median",
        "benchmark",
        "same_period_last_year",
    }
    return raw if raw in allowed else ""


def _sort_spec(analytical_task: str) -> dict[str, Any]:
    mapping = {
        "comparison_ranking": ("measure_descending", "ranking task"),
        "time_trend": ("date_ascending", "continuous time axis"),
        "period_comparison": ("date_or_declared_period_order", "period comparison"),
        "exact_lookup": ("primary_sort_then_stable_secondary_key", "table lookup"),
        "part_to_whole": ("measure_descending_unless_business_order", "composition scan"),
    }
    by, reason = mapping.get(analytical_task, ("declared_business_order_or_stable_input", "default stable order"))
    return {"by": by, "reason": reason}


def _color_spec(
    analytical_task: str,
    metric_semantics: dict[str, Any],
    tokens: dict[str, Any],
    *,
    blocked: list[str],
) -> dict[str, Any]:
    colors = tokens.get("colors") or {}
    semantic_direction = str(metric_semantics.get("semantic_direction") or "").strip().lower()
    semantic_allowed = analytical_task in {"target_vs_actual", "alerts", "kpi_monitoring"} and bool(semantic_direction)
    if "red_green_palette" in blocked:
        return {
            "default": colors.get("neutral", "#c7ccd4"),
            "focus": colors.get("focus", "#2f80ed"),
            "semantic_allowed": False,
            "positive": "",
            "negative": "",
            "alternative_pair": [colors.get("focus", "#2f80ed"), colors.get("warning", "#f9a825")],
            "reason": "red/green semantic palette was forbidden; use neutral or blue-orange contrast",
        }
    return {
        "default": colors.get("neutral", "#c7ccd4"),
        "focus": colors.get("focus", "#2f80ed"),
        "semantic_allowed": semantic_allowed,
        "positive": colors.get("positive", "#2e7d32") if semantic_allowed else "",
        "negative": colors.get("negative", "#c62828") if semantic_allowed else "",
        "reason": "semantic direction declared" if semantic_allowed else "neutral first; no decorative color",
    }


def _axis_spec(analytical_task: str) -> dict[str, Any]:
    return {
        "zero_baseline": analytical_task in {"comparison_ranking", "period_comparison", "distribution"},
        "date_axis_ascending": analytical_task in {"time_trend", "period_comparison"},
        "unit_label_required": analytical_task not in {"filtering", "methodology"},
        "measure_axis_title": False,
    }


def _label_spec(analytical_task: str, *, family: str, blocked: list[str]) -> dict[str, Any]:
    family_text = family.lower()
    return {
        "direct_labels": analytical_task
        in {"comparison_ranking", "part_to_whole", "time_trend", "period_comparison", "distribution"}
        or any(term in family_text for term in ("bar", "column", "line", "timeseries", "time_series"))
        or "legend" in blocked,
        "density_limit": "low_only",
        "native_title_hint_only": True,
    }


def _legend_spec(analytical_task: str, family: str, *, blocked: list[str]) -> dict[str, Any]:
    if "legend" in blocked:
        return {
            "show": False,
            "reason": "legend was forbidden by a negative requirement; use direct labels or omit it",
        }
    return {
        "show": analytical_task in {"part_to_whole", "time_trend"} and family not in {"kpi_value_only"},
        "reason": "only when color encodes visible categories and direct labels are insufficient",
    }
