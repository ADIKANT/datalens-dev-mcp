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
