from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class VisualQualityFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualQualityResult:
    ok: bool
    publish_allowed: bool
    visual_qa_status: str
    findings: list[VisualQualityFinding] = field(default_factory=list)
    schema_version: str = "2026-06-30.visual_quality_contract.v1"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


def validate_visual_quality_contract(
    spec: dict[str, Any],
    *,
    visual_qa_status: str = "not_run",
) -> VisualQualityResult:
    findings: list[VisualQualityFinding] = []
    family = str(spec.get("family") or spec.get("selected_family") or "").lower()
    analytical_task = str((spec.get("encoding") or {}).get("analytical_task") or spec.get("analytical_task") or "").lower()
    labels = spec.get("labels") if isinstance(spec.get("labels"), dict) else spec.get("label_spec") or {}
    axes = spec.get("axes") if isinstance(spec.get("axes"), dict) else spec.get("axis_spec") or {}
    gridlines = spec.get("gridlines") if isinstance(spec.get("gridlines"), dict) else {}
    colors = spec.get("colors") if isinstance(spec.get("colors"), dict) else spec.get("color_spec") or {}
    tooltip = spec.get("tooltip") if isinstance(spec.get("tooltip"), dict) else {}
    kpi_context = spec.get("kpi_context") if isinstance(spec.get("kpi_context"), dict) else spec.get("kpi_context_spec") or {}
    style_tokens = spec.get("style_tokens") if isinstance(spec.get("style_tokens"), dict) else {}
    runtime_constraints = spec.get("runtime_constraints") if isinstance(spec.get("runtime_constraints"), dict) else {}
    value_semantics = spec.get("value_semantics") if isinstance(spec.get("value_semantics"), dict) else {}
    formatting = spec.get("formatting") if isinstance(spec.get("formatting"), dict) else {}
    comparison_context = spec.get("comparison_context") if isinstance(spec.get("comparison_context"), dict) else {}
    responsive_layout = spec.get("responsive_layout") if isinstance(spec.get("responsive_layout"), dict) else {}
    hint_contract = spec.get("hint_contract") if isinstance(spec.get("hint_contract"), dict) else {}
    layout_contract = spec.get("layout_contract") if isinstance(spec.get("layout_contract"), dict) else {}
    semantic_roles_contract = (
        spec.get("semantic_roles_contract")
        if isinstance(spec.get("semantic_roles_contract"), dict)
        else {}
    )

    if _is_bar_like(family, analytical_task):
        direct_labels = bool(labels.get("direct_labels") or labels.get("show_values") or labels.get("showLabels"))
        if not direct_labels and not _explicit_label_axis_alternative(spec):
            findings.append(
                _finding(
                    "delta_v6_labels_required",
                    "$.labels",
                    "Delta v6 requires labels on bar/column charts unless an explicit exception is justified",
                )
            )
        readable_axis = bool(axes.get("show") or axes.get("unit_label_required") or gridlines.get("show"))
        if not direct_labels and not readable_axis and not _explicit_label_axis_alternative(spec):
            findings.append(_finding("bar_chart_label_contract", "$.labels", "bar charts need direct labels or readable axes/gridlines"))
        if axes.get("zero_baseline") is False:
            findings.append(_finding("bar_axis_zero_required", "$.axes.zero_baseline", "bar charts require zero baseline"))
    if _is_line_like(family, analytical_task):
        direct_labels = bool(labels.get("direct_labels") or labels.get("show_values") or labels.get("showLabels"))
        readable_axis = bool(
            axes.get("show")
            or axes.get("unit_label_required")
            or axes.get("date_axis_ascending")
            or axes.get("x_axis_label")
            or axes.get("y_axis_label")
        )
        tooltip_values = bool(tooltip.get("include_values") or tooltip.get("include_metric_definition"))
        line_label_alternative = (readable_axis and tooltip_values) or _explicit_label_axis_alternative(spec)
        if not direct_labels and not line_label_alternative:
            findings.append(
                _finding(
                    "delta_v6_labels_required",
                    "$.labels",
                    "Line charts require direct labels, readable axes with value tooltips, or an explicit alternative",
                )
            )
            findings.append(
                _finding(
                    "line_chart_axis_label_contract",
                    "$.axes",
                    "line charts without direct labels need readable axes plus value tooltips, or an explicit alternative",
                )
            )
    if _is_line_like(family, analytical_task) or _is_bar_like(family, analytical_task):
        if gridlines.get("show") is True and not _explicit_gridline_exception(spec):
            findings.append(
                _finding(
                    "delta_v6_gridlines_default_off",
                    "$.gridlines.show",
                    "Delta v6 keeps gridlines off unless numeric lookup is explicitly required",
                )
            )
        if axes.get("measure_axis_title") is True or axes.get("y_axis_title") is True:
            findings.append(
                _finding(
                    "delta_v6_measure_axis_title_default_off",
                    "$.axes",
                    "Delta v6 keeps measure-axis titles off when title/labels/legend already carry the meaning",
                )
            )
    comparator = str(kpi_context.get("comparator") or "").strip()
    if family.startswith("kpi") and comparator in {"previous_period", "implicit_previous_period"}:
        findings.append(
            _finding(
                "kpi_comparator_explicitness",
                "$.kpi_context.comparator",
                "KPI previous-period comparator must be explicit",
            )
        )
    if kpi_context.get("implicit_comparator_default"):
        findings.append(_finding("implicit_kpi_comparator", "$.kpi_context", "KPI comparator defaults must be disabled"))
    if colors.get("decorative") or (style_tokens.get("colors") or {}).get("decorative"):
        findings.append(_finding("decorative_color_forbidden", "$.colors", "color must encode grouping, focus, alert, or semantic status"))
    for key in ("decorative_css", "shadows", "gradients", "three_d"):
        if runtime_constraints.get(key):
            findings.append(_finding("chartjunk_forbidden", f"$.runtime_constraints.{key}", f"{key} is forbidden"))
    schema_version = str(spec.get("schema_version") or "")
    if schema_version in {
        "2026-07-19.renderer_visual_spec.v2",
        "2026-07-23.renderer_visual_spec.v3",
    }:
        findings.extend(
            _v2_renderer_contract_findings(
                value_semantics=value_semantics,
                formatting=formatting,
                comparison_context=comparison_context,
                responsive_layout=responsive_layout,
                hint_contract=hint_contract,
                layout_contract=layout_contract,
            )
        )
        if comparator and tooltip.get("comparison_interval_and_value") is not True:
            findings.append(
                _finding(
                    "comparison_tooltip_context_required",
                    "$.tooltip.comparison_interval_and_value",
                    "comparison tooltips must identify both intervals and both values",
                )
            )
        if schema_version == "2026-07-23.renderer_visual_spec.v3":
            findings.extend(
                _v3_renderer_contract_findings(
                    colors=colors,
                    labels=labels,
                    tooltip=tooltip,
                    kpi_context=kpi_context,
                    semantic_roles_contract=semantic_roles_contract,
                )
            )
    elif spec:
        findings.append(
            _finding(
                "renderer_visual_spec_current_contract_missing",
                "$.schema_version",
                "legacy visual spec has no current responsive, formatting, semantic-role, and missing-value contract",
                severity="warning",
            )
        )
    if visual_qa_status == "pass_unverified":
        findings.append(
            _finding(
                "visual_qa_unavailable_marked_as_pass",
                "$.visual_qa_status",
                "unavailable visual QA cannot be marked pass",
            )
        )
    errors = [finding for finding in findings if finding.severity == "error"]
    return VisualQualityResult(
        ok=not errors,
        publish_allowed=not errors,
        visual_qa_status=visual_qa_status,
        findings=findings,
    )


def validate_visual_readback_quality(readback: dict[str, Any], *, expected_active_widgets: int = 0) -> VisualQualityResult:
    findings: list[VisualQualityFinding] = []
    active = _active_widget_count(readback)
    if expected_active_widgets and active == 0:
        findings.append(
            _finding(
                "published_readback_has_no_active_widgets",
                "$.active_widgets",
                "expected active widgets but target readback has zero active widgets",
            )
        )
    visual_status = str(readback.get("visual_qa_status") or "not_run")
    if visual_status in {"unavailable", "unavailable_external_blocker", "not_run"} and readback.get("visual_qa_pass") is True:
        findings.append(
            _finding(
                "visual_qa_unavailable_marked_as_pass",
                "$.visual_qa_status",
                "browser/rendering unavailable must not be reported as visual pass",
            )
        )
    table_checks = readback.get("table_checks") if isinstance(readback.get("table_checks"), list) else []
    for index, table in enumerate(table_checks):
        if table.get("source_rows", 0) > 0 and (not table.get("columns") or not table.get("has_data")):
            findings.append(
                _finding(
                    "empty_table_readback_blocks_completion",
                    f"$.table_checks[{index}]",
                    "non-empty source readback produced a skeleton/empty table",
                )
            )
    errors = [finding for finding in findings if finding.severity == "error"]
    return VisualQualityResult(
        ok=not errors,
        publish_allowed=not errors,
        visual_qa_status=visual_status,
        findings=findings,
    )


def _is_bar_like(family: str, analytical_task: str) -> bool:
    return any(term in family for term in ("bar", "bullet")) or analytical_task in {"comparison_ranking", "period_comparison"}


def _is_line_like(family: str, analytical_task: str) -> bool:
    return any(term in family for term in ("line", "timeseries", "time_series", "sparkline")) or analytical_task in {
        "time_trend",
        "period_trend",
    }


def _explicit_label_axis_alternative(spec: dict[str, Any]) -> bool:
    alternatives = spec.get("alternatives") if isinstance(spec.get("alternatives"), dict) else {}
    runtime = spec.get("runtime_constraints") if isinstance(spec.get("runtime_constraints"), dict) else {}
    return bool(
        spec.get("explicit_label_axis_alternative")
        or alternatives.get("labels_or_axes")
        or alternatives.get("label_axis_alternative")
        or runtime.get("explicit_label_axis_alternative")
    )


def _explicit_gridline_exception(spec: dict[str, Any]) -> bool:
    gridlines = spec.get("gridlines") if isinstance(spec.get("gridlines"), dict) else {}
    alternatives = spec.get("alternatives") if isinstance(spec.get("alternatives"), dict) else {}
    return bool(
        spec.get("explicit_gridline_exception")
        or gridlines.get("numeric_lookup_required")
        or gridlines.get("explicit_reason")
        or alternatives.get("gridlines_required")
    )


def _v2_renderer_contract_findings(
    *,
    value_semantics: dict[str, Any],
    formatting: dict[str, Any],
    comparison_context: dict[str, Any],
    responsive_layout: dict[str, Any],
    hint_contract: dict[str, Any],
    layout_contract: dict[str, Any],
) -> list[VisualQualityFinding]:
    findings: list[VisualQualityFinding] = []
    required_objects = {
        "value_semantics": value_semantics,
        "formatting": formatting,
        "comparison_context": comparison_context,
        "responsive_layout": responsive_layout,
        "hint_contract": hint_contract,
        "layout_contract": layout_contract,
    }
    for name, value in required_objects.items():
        if not value:
            findings.append(_finding("renderer_v2_contract_missing", f"$.{name}", f"{name} is required"))
    if value_semantics:
        if value_semantics.get("missing_label") != "N/A":
            findings.append(
                _finding("missing_value_label", "$.value_semantics.missing_label", "missing values must render as N/A")
            )
        if value_semantics.get("observed_zero_distinct_from_missing") is not True:
            findings.append(
                _finding(
                    "zero_missing_semantics",
                    "$.value_semantics.observed_zero_distinct_from_missing",
                    "observed zero must stay distinct from a missing value",
                )
            )
        if value_semantics.get("null_time_series") != "preserve_gaps":
            findings.append(
                _finding(
                    "time_series_null_gap",
                    "$.value_semantics.null_time_series",
                    "time-series nulls must preserve gaps instead of becoming zero",
                )
            )
        if value_semantics.get("future_periods") != "exclude_without_observed_rows":
            findings.append(
                _finding(
                    "future_period_zero_fill",
                    "$.value_semantics.future_periods",
                    "future periods without observed rows must not be zero-filled",
                )
            )
    if formatting:
        expected_formats = {
            "daily_date": "DD.MM.YY",
            "monthly_date": "MM.YY",
            "axis_tick_strategy": "nice_1_2_2_5_5_10",
            "label_thinning": "viewport_aware",
        }
        for key, expected in expected_formats.items():
            if formatting.get(key) != expected:
                findings.append(
                    _finding(
                        "deterministic_formatting",
                        f"$.formatting.{key}",
                        f"{key} must use {expected}",
                    )
                )
        if formatting.get("axis_integer_ticks_unique") is not True:
            findings.append(
                _finding(
                    "duplicate_integer_ticks",
                    "$.formatting.axis_integer_ticks_unique",
                    "rounded integer axis ticks must remain unique",
                )
            )
    if comparison_context:
        if comparison_context.get("explicit_only") is not True:
            findings.append(
                _finding(
                    "comparison_explicitness",
                    "$.comparison_context.explicit_only",
                    "comparison is enabled only by an explicit accepted contract",
                )
            )
        if comparison_context.get("options") != "contextual_to_selected_period":
            findings.append(
                _finding(
                    "comparison_contextual_options",
                    "$.comparison_context.options",
                    "comparison options must be valid for the selected period",
                )
            )
        if comparison_context.get("tooltip") != "selected_interval_value_vs_comparison_interval_value":
            findings.append(
                _finding(
                    "comparison_tooltip_context_required",
                    "$.comparison_context.tooltip",
                    "comparison context must identify both intervals and values",
                )
            )
    if responsive_layout:
        if responsive_layout.get("sizing_source") != "options.width_and_height":
            findings.append(
                _finding(
                    "responsive_sizing_source",
                    "$.responsive_layout.sizing_source",
                    "Advanced renderers must derive size from options.width and options.height",
                )
            )
        if responsive_layout.get("fixed_min_width") is not False:
            findings.append(
                _finding(
                    "fixed_desktop_min_width",
                    "$.responsive_layout.fixed_min_width",
                    "fixed desktop minimum widths are forbidden",
                )
            )
        probes = [
            int(item)
            for item in responsive_layout.get("widget_width_probes_px") or []
            if isinstance(item, (int, float)) and not isinstance(item, bool)
        ]
        if not probes or min(probes) > 360 or max(probes) < 700:
            findings.append(
                _finding(
                    "responsive_widget_probe_coverage",
                    "$.responsive_layout.widget_width_probes_px",
                    "responsive QA needs both narrow and wide widget probes",
                )
            )
        profiles = {str(item) for item in responsive_layout.get("dashboard_profiles") or []}
        if not {"compact_desktop", "wide_desktop"} <= profiles:
            findings.append(
                _finding(
                    "responsive_dashboard_profiles",
                    "$.responsive_layout.dashboard_profiles",
                    "responsive QA needs compact and wide desktop profiles",
                )
            )
        for key in ("horizontal_overflow", "content_clipping"):
            if responsive_layout.get(key) != "forbidden":
                findings.append(
                    _finding(
                        "responsive_overflow_contract",
                        f"$.responsive_layout.{key}",
                        f"{key} must be forbidden",
                    )
                )
    if hint_contract:
        content = {str(item) for item in hint_contract.get("content") or []}
        if not {"business_meaning", "calculation", "limitations"} <= content:
            findings.append(
                _finding(
                    "business_hint_contract",
                    "$.hint_contract.content",
                    "hints must explain business meaning, calculation, and limitations",
                )
            )
        if hint_contract.get("section_header_hint") is not False:
            findings.append(
                _finding(
                    "section_header_hint",
                    "$.hint_contract.section_header_hint",
                    "plain section headers must not carry a redundant hint",
                )
            )
        if hint_contract.get("table_column_hint_settings_required") is not True:
            findings.append(
                _finding(
                    "table_column_hint_settings",
                    "$.hint_contract.table_column_hint_settings_required",
                    "table-column hints require enabled hintSettings in addition to description",
                )
            )
    if layout_contract:
        for key in (
            "preserve_existing_geometry",
            "equal_kpi_heights_within_row",
            "one_kpi_per_object",
            "long_table_internal_scroll",
        ):
            if layout_contract.get(key) is not True:
                findings.append(
                    _finding("layout_runtime_contract", f"$.layout_contract.{key}", f"{key} must be true")
                )
        if layout_contract.get("semantic_noop_geometry_drift") is not False:
            findings.append(
                _finding(
                    "semantic_noop_geometry_drift",
                    "$.layout_contract.semantic_noop_geometry_drift",
                    "a semantic no-op must not change dashboard geometry",
                )
            )
    return findings


def _v3_renderer_contract_findings(
    *,
    colors: dict[str, Any],
    labels: dict[str, Any],
    tooltip: dict[str, Any],
    kpi_context: dict[str, Any],
    semantic_roles_contract: dict[str, Any],
) -> list[VisualQualityFinding]:
    findings: list[VisualQualityFinding] = []
    semantic_roles = colors.get("semantic_roles") if isinstance(colors.get("semantic_roles"), dict) else {}
    required_role_names = {
        "success",
        "failure",
        "warning",
        "neutral",
        "focus",
        "comparison",
        "track",
    }
    if not required_role_names <= set(semantic_roles):
        findings.append(
            _finding(
                "semantic_color_roles",
                "$.colors.semantic_roles",
                "visual spec v3 requires success, failure, warning, neutral, focus, comparison, and track roles",
            )
        )
    track_contract = colors.get("track_contract") if isinstance(colors.get("track_contract"), dict) else {}
    if (
        track_contract.get("lighter_than_primary") is not True
        or track_contract.get("distinct_from_focus_and_comparison") is not True
        or (
            semantic_roles.get("track")
            and semantic_roles.get("track")
            in {semantic_roles.get("focus"), semantic_roles.get("comparison")}
        )
    ):
        findings.append(
            _finding(
                "semantic_track_contrast",
                "$.colors.track_contract",
                "track must be lighter and distinct from focus and comparison colors",
            )
        )
    if labels.get("overflow_strategy") != "wrap_or_expand":
        findings.append(
            _finding(
                "label_overflow_strategy",
                "$.labels.overflow_strategy",
                "labels must wrap or expand before truncation",
            )
        )
    if labels.get("ellipsis") != "explicit_only":
        findings.append(
            _finding(
                "label_ellipsis_policy",
                "$.labels.ellipsis",
                "ellipsis is allowed only when explicitly requested",
            )
        )
    if tooltip.get("bucket_label") != "single_interval":
        findings.append(
            _finding(
                "tooltip_bucket_label",
                "$.tooltip.bucket_label",
                "tooltip bucket labels must identify one exact interval",
            )
        )
    surface = kpi_context.get("surface") if isinstance(kpi_context.get("surface"), dict) else {}
    if (
        kpi_context.get("comparator_explicit") is not True
        or surface.get("background") != "transparent_or_profile"
        or surface.get("border") != "none_or_profile"
        or surface.get("shadow") is not False
    ):
        findings.append(
            _finding(
                "kpi_surface_defaults",
                "$.kpi_context",
                "KPI comparator and surface defaults must remain explicit and profile-controlled",
            )
        )
    required = {str(item) for item in semantic_roles_contract.get("required") or []}
    forbidden = {str(item) for item in semantic_roles_contract.get("forbidden") or []}
    missing_required = sorted(role for role in required if not semantic_roles.get(role))
    present_forbidden = sorted(role for role in forbidden if semantic_roles.get(role))
    if missing_required:
        findings.append(
            _finding(
                "required_semantic_roles",
                "$.semantic_roles_contract.required",
                "required semantic roles are not available: " + ", ".join(missing_required),
            )
        )
    if present_forbidden:
        findings.append(
            _finding(
                "forbidden_semantic_roles",
                "$.semantic_roles_contract.forbidden",
                "forbidden semantic roles remain active: " + ", ".join(present_forbidden),
            )
        )
    return findings


def _active_widget_count(value: dict[str, Any]) -> int:
    for key in ("active_widget_count", "active_widgets", "widget_count"):
        raw = value.get(key)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, list):
            return len(raw)
    counts = value.get("counts_by_object_type")
    if isinstance(counts, dict):
        return int(counts.get("widget") or counts.get("widgets") or counts.get("chart") or counts.get("charts") or 0)
    return 0


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> VisualQualityFinding:
    return VisualQualityFinding(rule=rule, severity=severity, path=path, message=message)
