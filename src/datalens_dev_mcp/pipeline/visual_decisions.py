from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from datalens_dev_mcp.editor.visual_spec import RendererVisualSpec, build_renderer_visual_spec
from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec, route_for_chart_family
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.negative_requirements import (
    active_forbidden_chart_families,
    active_forbidden_concepts,
    active_negative_requirement_ids,
    detect_negative_requirements,
)


Route = Literal[
    "editor_advanced",
    "editor_table",
    "editor_markdown",
    "editor_js_control",
    "wizard_native",
    "ql_explicit",
]
Confidence = Literal["high", "medium", "low", "blocked"]


@dataclass(frozen=True)
class ChartDecisionRecord:
    schema_id: str
    chart_id: str
    business_question: str
    analytical_task: str
    selected_family: str
    selected_route: Route
    renderer_visual_spec: RendererVisualSpec
    confidence: Confidence
    audience: list[str] = field(default_factory=list)
    dashboard_type: str = "unknown"
    data_shape: dict[str, Any] = field(default_factory=dict)
    metric_semantics: dict[str, Any] = field(default_factory=dict)
    rejected_families: list[dict[str, str]] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    sort_spec: dict[str, Any] = field(default_factory=dict)
    series_spec: dict[str, Any] = field(default_factory=dict)
    color_spec: dict[str, Any] = field(default_factory=dict)
    axis_spec: dict[str, Any] = field(default_factory=dict)
    label_spec: dict[str, Any] = field(default_factory=dict)
    legend_spec: dict[str, Any] = field(default_factory=dict)
    tooltip_spec: dict[str, Any] = field(default_factory=dict)
    kpi_context_spec: dict[str, Any] = field(default_factory=dict)
    interaction_spec: dict[str, Any] = field(default_factory=dict)
    negative_requirements_applied: list[str] = field(default_factory=list)
    negative_requirement_concepts: list[str] = field(default_factory=list)
    questions_if_blocked: list[str] = field(default_factory=list)
    source_evidence_refs: list[str] = field(default_factory=list)
    effective_visual_contract_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["renderer_visual_spec"] = self.renderer_visual_spec.to_dict()
        return payload


class VisualDecisionEngine:
    def decide(
        self,
        *,
        chart_id: str,
        business_question: str,
        audience: list[str] | None = None,
        dashboard_type: str = "unknown",
        data_shape: dict[str, Any] | None = None,
        metric_semantics: dict[str, Any] | None = None,
        user_decisions: list[str] | None = None,
        negative_requirements: list[dict[str, Any]] | None = None,
        requested_family: str = "",
        requested_route: str = "",
        effective_visual_contract: dict[str, Any] | None = None,
        source_evidence_refs: list[str] | None = None,
    ) -> ChartDecisionRecord:
        text = "\n".join([business_question, "\n".join(user_decisions or [])])
        detected_negative = [
            item.to_dict()
            for decision in (user_decisions or [])
            for item in detect_negative_requirements(decision, decision_id=chart_id)
        ]
        all_negative = list(negative_requirements or []) + detected_negative
        negative_concepts = active_forbidden_concepts(all_negative)
        forbidden_families = active_forbidden_chart_families(all_negative)
        data_shape = data_shape or infer_data_shape(text)
        metric_semantics = dict(metric_semantics or infer_metric_semantics(text))
        analytical_task = infer_analytical_task(text, data_shape=data_shape, metric_semantics=metric_semantics)
        selected_family = _select_family(
            analytical_task,
            text=text,
            data_shape=data_shape,
            metric_semantics=metric_semantics,
            requested_family=requested_family,
            negative_concepts=negative_concepts,
            forbidden_families=forbidden_families,
        )
        resolution = resolve_chart_family(selected_family)
        selected_family = resolution.approved_alternative
        if selected_family in forbidden_families:
            selected_family = _fallback_for_forbidden_family(
                selected_family,
                analytical_task=analytical_task,
                data_shape=data_shape,
            )
        if "implicit_period_comparison" in negative_concepts and selected_family in {"kpi_value_delta", "kpi_value_delta_sparkline"}:
            selected_family = "kpi_value_sparkline"
        effective = dict(effective_visual_contract or {})
        preserved_technology = str(effective.get("technology") or "")
        route = requested_route or preserved_technology or route_for_chart_family(selected_family)
        if route not in {
            "editor_advanced", "editor_table", "editor_markdown", "editor_js_control",
            "wizard_native", "ql_explicit",
        }:
            route = route_for_chart_family(selected_family)
        if route == "ql_explicit" and requested_route != "ql_explicit" and preserved_technology != "ql_explicit":
            route = route_for_chart_family(selected_family)
        param_spec = get_chart_param_spec(selected_family)
        visual_spec = build_renderer_visual_spec(
            family=selected_family,
            route=route,
            analytical_task=analytical_task,
            chart_purpose=business_question[:240],
            metric_semantics=metric_semantics,
            negative_requirements=negative_concepts,
        )
        questions = _blocking_questions(
            business_question,
            audience=audience or [],
            analytical_task=analytical_task,
            data_shape=data_shape,
            metric_semantics=metric_semantics,
        )
        if effective and business_question.strip():
            questions = []
        confidence: Confidence = "blocked" if not business_question.strip() else "low" if questions else "high"
        rejected = _rejected_families(analytical_task, selected_family, negative_concepts, forbidden_families)
        required_visual = _effective_sections(effective)
        series_spec = _deep_merge({}, required_visual.get("series") or {})
        legend_spec = _deep_merge(visual_spec.legend, required_visual.get("legend") or {})
        axis_spec = _deep_merge(visual_spec.axes, required_visual.get("axes") or {})
        tooltip_spec = _deep_merge(visual_spec.tooltip, required_visual.get("tooltip") or {})
        label_spec = _deep_merge(visual_spec.labels, required_visual.get("formatting") or {})
        color_spec = _deep_merge(visual_spec.colors, required_visual.get("colors") or {})
        interaction_spec = _deep_merge(
            {"cross_filter": "only_when_declared", "drilldown": "only_when_target_declared"},
            required_visual.get("selectors") or {},
        )
        _apply_forbidden_visuals(
            effective.get("forbidden") if isinstance(effective.get("forbidden"), dict) else {},
            legend=legend_spec,
            axes=axis_spec,
            tooltip=tooltip_spec,
            series=series_spec,
            interactions=interaction_spec,
        )
        return ChartDecisionRecord(
            schema_id="dataviz_chart_decision",
            chart_id=chart_id,
            business_question=business_question.strip() or "missing business question",
            audience=audience or [],
            dashboard_type=_normalize_dashboard_type(dashboard_type),
            analytical_task=analytical_task,
            data_shape=data_shape,
            metric_semantics=metric_semantics,
            selected_family=selected_family,
            selected_route=route,  # type: ignore[arg-type]
            rejected_families=rejected,
            required_fields=list(param_spec.required_parameters),
            optional_fields=list(param_spec.optional_parameters),
            sort_spec=visual_spec.sort,
            series_spec=series_spec,
            color_spec=color_spec,
            axis_spec=axis_spec,
            label_spec=label_spec,
            legend_spec=legend_spec,
            tooltip_spec=tooltip_spec,
            kpi_context_spec=visual_spec.kpi_context,
            interaction_spec=interaction_spec,
            negative_requirements_applied=active_negative_requirement_ids(all_negative),
            negative_requirement_concepts=negative_concepts,
            renderer_visual_spec=visual_spec,
            confidence=confidence,
            questions_if_blocked=questions,
            source_evidence_refs=source_evidence_refs or [],
            effective_visual_contract_hash=str(effective.get("contract_hash") or ""),
        )


def decide_chart(**kwargs: Any) -> ChartDecisionRecord:
    return VisualDecisionEngine().decide(**kwargs)


def attach_style_binding_to_decision(record: dict[str, Any], binding: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(record)
    if binding:
        result["style_binding"] = {
            "selection_origin": binding.get("selection_origin"),
            "profile_sha256": binding.get("profile_sha256"),
            "technology": binding.get("technology"),
            "binding_sha256": binding.get("binding_sha256"),
        }
    return result


def validate_chart_decision_record(record: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_id",
        "chart_id",
        "business_question",
        "analytical_task",
        "selected_family",
        "selected_route",
        "renderer_visual_spec",
        "confidence",
    ]
    issues = [f"{field} is required" for field in required if not record.get(field)]
    if record.get("selected_route") not in {
        "editor_advanced",
        "editor_table",
        "editor_markdown",
        "editor_js_control",
        "wizard_native",
        "ql_explicit",
    }:
        issues.append("selected_route must be an allowed DataLens creation route")
    negative_ids = list(record.get("negative_requirements_applied") or [])
    negative_concepts = list(record.get("negative_requirement_concepts") or [])
    negative_marker_text = " ".join(str(item) for item in negative_ids + negative_concepts).lower()
    if "implicit_period_comparison" in negative_marker_text or "previous_period_comparison" in negative_marker_text:
        if record.get("selected_family") in {"kpi_value_delta", "kpi_value_delta_sparkline"}:
            issues.append("previous-period negative requirement selected a comparator KPI family")
        text = str(record).lower()
        if any(token in text for token in ("previous_value", "delta_pct", "period_bucket")):
            issues.append("previous-period negative requirement leaked into chart decision")
    if "chart_family_pie_donut" in negative_marker_text and record.get("selected_family") in {"pie", "donut"}:
        issues.append("pie/donut negative requirement selected a forbidden family")
    if "table_only_output" in negative_marker_text:
        route = record.get("selected_route")
        family = str(record.get("selected_family") or "")
        allowed_route = route in {"wizard_native", "editor_table", "editor_markdown", "editor_js_control"}
        allowed_family = family == "table_node" or family.startswith("md_") or family.startswith("selector_")
        if not (allowed_route and allowed_family):
            issues.append("table-only negative requirement selected a chart family")
    if "legend" in negative_marker_text:
        legend_spec = record.get("legend_spec") or {}
        renderer_legend = (record.get("renderer_visual_spec") or {}).get("legend") or {}
        if legend_spec.get("show") or renderer_legend.get("show"):
            issues.append("legend negative requirement kept legend visible")
    if "red_green_palette" in negative_marker_text:
        color_spec = record.get("color_spec") or {}
        if color_spec.get("positive") or color_spec.get("negative"):
            issues.append("red/green negative requirement kept semantic red-green colors")
    spec = record.get("renderer_visual_spec") or {}
    for field_name in ("style_tokens", "encoding", "runtime_constraints"):
        if field_name not in spec:
            issues.append(f"renderer_visual_spec.{field_name} is required")
    return {"ok": not issues, "issues": issues}


def _effective_sections(contract: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for bucket in ("defaults", "preserve", "required"):
        value = contract.get(bucket)
        if isinstance(value, dict):
            result = _deep_merge(result, value)
    return result


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in left.items()}
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_forbidden_visuals(
    forbidden: dict[str, Any],
    *,
    legend: dict[str, Any],
    axes: dict[str, Any],
    tooltip: dict[str, Any],
    series: dict[str, Any],
    interactions: dict[str, Any],
) -> None:
    targets = {
        "legend": legend,
        "axes": axes,
        "tooltip": tooltip,
        "series": series,
        "selectors": interactions,
    }
    for category, target in targets.items():
        value = forbidden.get(category)
        if not isinstance(value, dict):
            continue
        for key, forbidden_value in value.items():
            if forbidden_value is True and key in {"show", "visible", "enabled"}:
                target["show" if category == "legend" else key] = False
            else:
                target.setdefault("forbidden", {})[key] = forbidden_value


def infer_data_shape(text: str) -> dict[str, Any]:
    lowered = text.lower()
    return {
        "has_date": any(term in lowered for term in ("date", "time", "daily", "weekly", "month", "недел", "день", "месяц", "динамик")),
        "has_geo": any(term in lowered for term in ("geo", "гео", "latitude", "longitude", "location", "карта", "map")),
        "has_many_fields": any(term in lowered for term in ("table", "таблиц", "registry", "lookup", "detail", "export", "выгруз")),
        "has_threshold": any(term in lowered for term in ("target", "plan", "sla", "threshold", "план", "цель", "порог")),
        "measure_count": 2 if any(term in lowered for term in ("correlation", "scatter", "relationship", "x/y")) else 1,
    }


def infer_metric_semantics(text: str) -> dict[str, Any]:
    lowered = text.lower()
    comparator = ""
    for value, terms in {
        "target": ("target", "цель"),
        "plan": ("plan", "план"),
        "sla": ("sla",),
        "threshold": ("threshold", "порог"),
        "same_period_last_year": ("same period last year", "год к году"),
        "previous_period": ("previous period", "предыдущ"),
    }.items():
        if any(term in lowered for term in terms):
            comparator = value
            break
    return {
        "unit": "declared_or_pending",
        "grain": "declared_or_pending",
        "aggregation": "declared_or_pending",
        "semantic_direction": "declared" if comparator in {"target", "plan", "sla", "threshold"} else "",
        "comparator": comparator,
    }


def infer_analytical_task(text: str, *, data_shape: dict[str, Any], metric_semantics: dict[str, Any]) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("methodology", "method", "note", "owner", "header", "методолог", "примечан")):
        return "methodology"
    if any(term in lowered for term in ("selector", "filter", "control", "селектор", "фильтр")):
        return "filtering"
    if data_shape.get("has_many_fields"):
        return "exact_lookup"
    if any(term in lowered for term in ("map", "карта")) and any(
        term in lowered for term in ("geo", "гео", "location", "latitude", "longitude", "географ")
    ):
        return "geo"
    if any(term in lowered for term in ("share", "доля", "part-to-whole", "100%", "pie", "donut")):
        return "part_to_whole"
    if any(term in lowered for term in ("correlation", "relationship", "scatter", "bubble", "связь", "корреляц")):
        return "relationship"
    if any(term in lowered for term in ("distribution", "histogram", "box", "распредел")):
        return "distribution"
    if metric_semantics.get("comparator") in {"target", "plan", "sla", "threshold"}:
        return "target_vs_actual"
    if any(term in lowered for term in ("trend", "динамик", "weekly", "daily", "month", "по недел", "по дням")):
        return "time_trend"
    if any(term in lowered for term in ("period comparison", "по период", "месяц к месяцу")):
        return "period_comparison"
    if any(term in lowered for term in ("top", "rank", "ranking", "compare", "bar", "категор", "рейтинг")):
        return "comparison_ranking"
    if any(term in lowered for term in ("kpi", "metric", "current", "status", "метрик", "показател")):
        return "kpi_monitoring"
    return "unknown"


def _select_family(
    analytical_task: str,
    *,
    text: str,
    data_shape: dict[str, Any],
    metric_semantics: dict[str, Any],
    requested_family: str,
    negative_concepts: list[str],
    forbidden_families: list[str],
) -> str:
    if requested_family:
        resolution = resolve_chart_family(requested_family)
        family = resolution.approved_alternative
    else:
        family = {
            "exact_lookup": "table_node",
            "comparison_ranking": "horizontal_bar",
            "time_trend": "line_chart",
            "period_comparison": "vertical_bar_time_bucket",
            "target_vs_actual": "bullet_assignees",
            "part_to_whole": "stacked_100",
            "relationship": "bubble" if int(data_shape.get("measure_count") or 1) >= 3 else "scatter",
            "distribution": "histogram",
            "geo": "native_map_geo_widget",
            "filtering": "selector_family_dynamic",
            "methodology": "md_methodology_block",
            "kpi_monitoring": "kpi_value_sparkline" if data_shape.get("has_date") else "kpi_value_only",
        }.get(analytical_task, "table_node")
    if "table_only_output" in negative_concepts:
        return "table_node"
    if family in forbidden_families:
        return _fallback_for_forbidden_family(family, analytical_task=analytical_task, data_shape=data_shape)
    if "implicit_period_comparison" in negative_concepts and family in {"kpi_value_delta", "kpi_value_delta_sparkline"}:
        return "kpi_value_sparkline" if data_shape.get("has_date") else "kpi_value_only"
    if analytical_task == "part_to_whole" and not _small_true_composition(text):
        return "horizontal_bar"
    if analytical_task == "geo" and not data_shape.get("has_geo"):
        return "table_node"
    return family


def _small_true_composition(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in ("100%", "whole", "composition", "состав", "доля")) and any(
        term in lowered for term in ("<=5", "5 categories", "few", "несколько")
    )


def _blocking_questions(
    business_question: str,
    *,
    audience: list[str],
    analytical_task: str,
    data_shape: dict[str, Any],
    metric_semantics: dict[str, Any],
) -> list[str]:
    questions: list[str] = []
    lowered = business_question.lower()
    if not business_question.strip():
        questions.append("Which business question should this chart answer?")
    if not audience and not any(term in lowered for term in ("audience", "users", "owner", "stakeholder")):
        questions.append("Who is the audience and owner?")
    if analytical_task in {"kpi_monitoring", "comparison_ranking", "time_trend"} and not any(
        term in lowered for term in ("metric", "kpi", "measure", "count", "amount", "колич", "метрик", "показател")
    ):
        questions.append("Which metric definition, unit, and aggregation are accepted?")
    if analytical_task in {"time_trend", "period_comparison"} and not data_shape.get("has_date"):
        questions.append("Which date field and grain should be used?")
    if analytical_task == "target_vs_actual" and not metric_semantics.get("comparator"):
        questions.append("Which target, plan, SLA, or threshold is the comparator?")
    if not any(term in lowered for term in ("source", "dataset", "table", "freshness", "источник", "таблиц", "данн")):
        questions.append("Which data source and freshness expectation are accepted?")
    return questions


def _rejected_families(
    analytical_task: str,
    selected_family: str,
    negative_concepts: list[str],
    forbidden_families: list[str],
) -> list[dict[str, str]]:
    rejected: list[dict[str, str]] = []
    if analytical_task == "comparison_ranking":
        rejected.extend(
            [
                {"family": "pie", "reason": "bar/table compares nominal categories more accurately"},
                {"family": "donut", "reason": "bar/table compares nominal categories more accurately"},
            ]
        )
    if analytical_task == "exact_lookup":
        rejected.append({"family": "advanced_html_table", "reason": "table_node is the native exact-value route"})
    if selected_family in {"heatmap", "waterfall", "funnel_snapshot", "sankey_status_flow", "histogram", "box_plot"}:
        rejected.append({"family": "wizard_native", "reason": "registered capability gap requires JavaScript semantics"})
    if "implicit_period_comparison" in negative_concepts:
        rejected.extend(
            [
                {"family": "kpi_value_delta", "reason": "previous-period comparator was forbidden"},
                {"family": "kpi_value_delta_sparkline", "reason": "previous-period comparator was forbidden"},
            ]
        )
    for family in forbidden_families:
        if family == selected_family:
            continue
        rejected.append({"family": family, "reason": "negative requirement forbids this family"})
    if "legend" in negative_concepts:
        rejected.append({"family": "legend", "reason": "legend was forbidden; direct labels or omission are required"})
    if "red_green_palette" in negative_concepts:
        rejected.append({"family": "red_green_palette", "reason": "red/green semantic palette was forbidden"})
    return _dedupe_rejections(rejected)


def _fallback_for_forbidden_family(family: str, *, analytical_task: str, data_shape: dict[str, Any]) -> str:
    if family in {"pie", "donut", "treemap", "stacked_100"}:
        return "horizontal_bar"
    if family in {"kpi_value_delta", "kpi_value_delta_sparkline"}:
        return "kpi_value_sparkline" if data_shape.get("has_date") else "kpi_value_only"
    if analytical_task == "methodology":
        return "md_methodology_block"
    if analytical_task == "filtering":
        return "selector_family_dynamic"
    return "table_node"


def _dedupe_rejections(rejected: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in rejected:
        key = (item.get("family", ""), item.get("reason", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _normalize_dashboard_type(value: str) -> str:
    aliases = {
        "object_management": "object_management_page",
        "alerts_mailing": "alerts",
        "analytical_tool": "analytical_instrument",
        "project_ad_hoc": "project_dashboard",
    }
    normalized = (value or "unknown").strip().lower()
    return aliases.get(normalized, normalized or "unknown")
