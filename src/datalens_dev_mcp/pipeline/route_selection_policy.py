from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from datalens_dev_mcp.pipeline.route_registry import (
    POLICY_VERSION,
    QL_EXPLICIT_ROUTE,
    WIZARD_NATIVE_ROUTE,
    capability_gap_for_family,
    decide_registered_route,
    normalize_creation_route,
)
from datalens_dev_mcp.pipeline.user_request import NormalizedUserRequest, normalize_user_request
from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json


RouteDecisionStatus = Literal["approved", "approved_with_requirements", "blocked_unsupported_route", "blocked_question"]


@dataclass(frozen=True)
class RouteSelectionDecision:
    status: RouteDecisionStatus
    requested_route: str
    selected_route: str
    selected_family: str
    reason: str
    visualization_id: str = ""
    selection_origin: str = ""
    selection_reason: str = ""
    capability_gap: str = ""
    docs_api_evidence: list[dict[str, Any]] = field(default_factory=list)
    nearest_supported_route: str = ""
    forbidden_fallback: bool = False
    required_evidence: list[str] = field(default_factory=list)
    policy: str = POLICY_VERSION

    @property
    def route(self) -> str:
        return self.selected_route

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["route"] = self.selected_route
        return payload


class RouteSelectionPolicyV5:
    """Deterministic Wizard-first routing with explicit-only QL selection."""

    def __init__(
        self,
        *,
        route_policy: dict[str, Any] | None = None,
        docs_feature_policy: dict[str, Any] | None = None,
        api_operation_policy: dict[str, Any] | None = None,
    ) -> None:
        self.route_policy = route_policy or _load_json("config/route_selection_policy_v5.json", {})
        self.docs_feature_policy = docs_feature_policy or _load_json("config/datalens_docs_feature_policy.json", {})
        self.api_operation_policy = api_operation_policy or _load_json("config/datalens_api_operation_policy.json", {})

    def select(
        self,
        request: str | NormalizedUserRequest,
        *,
        existing_route: str = "",
        existing_object_type: str = "",
        existing_visualization_id: str = "",
        semantic_output: str = "",
    ) -> RouteSelectionDecision:
        normalized = request if isinstance(request, NormalizedUserRequest) else normalize_user_request(str(request))
        preserve = self._preserve_existing_route(
            normalized,
            existing_route=existing_route,
            existing_object_type=existing_object_type,
            existing_visualization_id=existing_visualization_id,
        )
        if preserve:
            return preserve

        route_intent = normalized.route_intent
        semantic_text = f"{normalized.raw_text}\n{semantic_output}".lower()
        if route_intent == "ql_explicit":
            registered = decide_registered_route("ql_chart", explicit_route=QL_EXPLICIT_ROUTE)
            return self._decision(
                registered,
                requested_route=QL_EXPLICIT_ROUTE,
                family="ql_chart",
                evidence=("ql_charts", "createQLChart", "updateQLChart"),
                required_evidence=["explicit_user_request", "explicit_payload_or_fresh_saved_ql_seed"],
            )
        if route_intent in {"js", "advanced_editor"}:
            registered = decide_registered_route("custom_dom", explicit_route="editor_advanced")
            return self._decision(
                registered,
                requested_route=route_intent,
                family="advanced_editor_js",
                evidence=("editor_widgets_advanced", "createEditorChart", "updateEditorChart"),
            )
        if _semantic_selector(semantic_text):
            registered = decide_registered_route("control_node")
            return self._decision(
                registered,
                requested_route="semantic_selector",
                family="control_node",
                evidence=("editor_cross_filtration", "createEditorChart", "updateEditorChart"),
                required_evidence=["selector_layout_contract", "dashboard_relation_readback"],
            )
        if _semantic_markdown(semantic_text):
            registered = decide_registered_route("md_methodology_block")
            return self._decision(
                registered,
                requested_route="semantic_markdown_methodology",
                family="markdown_node",
                evidence=("editor_widgets_advanced", "createEditorChart", "updateEditorChart"),
            )
        if _semantic_dataset_backed(semantic_text) and not _has_visual_semantics(semantic_text):
            return RouteSelectionDecision(
                status="approved_with_requirements",
                requested_route="dataset_backed_source",
                selected_route="dataset_backed",
                selected_family="source_route_resolver",
                reason="Resolve the existing dataset before creating its visualization.",
                selection_origin="source_route_resolution",
                selection_reason="The request identifies an existing dataset but no visualization semantics.",
                docs_api_evidence=self._evidence("dataset_cache_invalidation", "getDataset", "createDataset", "updateDataset"),
                required_evidence=["workbook_entries_readback", "dataset_schema_readback"],
            )

        family = _semantic_family(semantic_text, route_intent=route_intent)
        explicit_route = ""
        explicit_wizard = route_intent == "wizard_native" or (
            route_intent == "wizard_map_native" and _explicit_wizard_request(normalized.raw_text.lower())
        )
        if explicit_wizard:
            capability_gap = capability_gap_for_family(family)
            if capability_gap:
                return RouteSelectionDecision(
                    status="blocked_unsupported_route",
                    requested_route=route_intent,
                    selected_route="",
                    selected_family=family,
                    reason="The explicitly requested Wizard route cannot provide the registered custom semantics.",
                    selection_origin="explicit_user_request",
                    selection_reason="Explicit Wizard does not silently convert to JavaScript.",
                    capability_gap=capability_gap,
                    forbidden_fallback=True,
                    nearest_supported_route="editor_advanced after an explicit route change",
                    docs_api_evidence=self._evidence("editor_widgets_advanced", "createWizardChart", "createEditorChart"),
                )
            explicit_route = WIZARD_NATIVE_ROUTE
        registered = decide_registered_route(
            family,
            semantic_text=semantic_text,
            explicit_route=explicit_route,
        )
        required: list[str] = []
        status: RouteDecisionStatus = "approved"
        feature_id = "visual_line"
        if registered.visualization_id == "geolayer":
            required.extend(["validated_geo_evidence", "object_schema_available"])
            status = "approved_with_requirements"
            feature_id = "visual_map"
        elif family == "bubble":
            required.append("size_role")
            status = "approved_with_requirements"
        elif family in {"kpi_value_only", "kpi_value_delta"}:
            required.extend(["kpi_formula", "unit", "grain", "comparator_policy"])
            status = "approved_with_requirements"
        methods = (
            ("createWizardChart", "updateWizardChart")
            if registered.route == WIZARD_NATIVE_ROUTE
            else ("createEditorChart", "updateEditorChart")
        )
        return self._decision(
            registered,
            requested_route=(
                route_intent
                if route_intent not in {"unspecified", "wizard_map_native"} or explicit_wizard
                else "wizard_first_default"
            ),
            family=family,
            evidence=(feature_id, *methods),
            required_evidence=required,
            status=status,
        )

    def _decision(
        self,
        registered: Any,
        *,
        requested_route: str,
        family: str,
        evidence: tuple[str, ...],
        required_evidence: list[str] | None = None,
        status: RouteDecisionStatus = "approved",
    ) -> RouteSelectionDecision:
        feature_id, *methods = evidence
        return RouteSelectionDecision(
            status=status,
            requested_route=requested_route,
            selected_route=registered.route,
            selected_family=family,
            reason=registered.selection_reason,
            visualization_id=registered.visualization_id,
            selection_origin=registered.selection_origin,
            selection_reason=registered.selection_reason,
            capability_gap=registered.capability_gap,
            docs_api_evidence=self._evidence(feature_id, *methods),
            required_evidence=required_evidence or [],
        )

    def _preserve_existing_route(
        self,
        request: NormalizedUserRequest,
        *,
        existing_route: str,
        existing_object_type: str,
        existing_visualization_id: str,
    ) -> RouteSelectionDecision | None:
        normalized = " ".join(item.strip().lower() for item in (existing_route, existing_object_type) if item.strip())
        if not normalized:
            return None
        if "ql" in normalized:
            if request.route_intent != "ql_explicit":
                return RouteSelectionDecision(
                    status="blocked_question",
                    requested_route="preserve_existing_ql",
                    selected_route="",
                    selected_family="ql_chart",
                    reason="QL updates require a direct user request for QL; the server never infers QL authoring.",
                    selection_origin="policy_guard",
                    selection_reason="explicit_user_request evidence is absent",
                    forbidden_fallback=True,
                    nearest_supported_route="Ask the user to explicitly request QL update, or perform read-only inspection.",
                    required_evidence=["explicit_user_request", "fresh_saved_ql_seed_or_explicit_payload"],
                    docs_api_evidence=self._evidence("ql_charts", "getQLChart", "updateQLChart"),
                )
            registered = decide_registered_route("ql_chart", explicit_route=QL_EXPLICIT_ROUTE)
            return self._decision(
                registered,
                requested_route="preserve_existing_object_route",
                family="ql_chart",
                evidence=("ql_charts", "getQLChart", "updateQLChart"),
                required_evidence=["fresh_saved_readback", "explicit_user_request"],
                status="approved_with_requirements",
            )
        if "wizard" in normalized or "ymap" in normalized:
            registered = decide_registered_route(
                "native_map_geo_widget" if any(token in normalized for token in ("ymap", "map", "geo")) else "",
                existing_route=WIZARD_NATIVE_ROUTE,
                existing_visualization_id=existing_visualization_id,
            )
            return self._decision(
                registered,
                requested_route="preserve_existing_object_route",
                family="existing_wizard_chart",
                evidence=("visual_line", "getWizardChart", "updateWizardChart"),
                required_evidence=["fresh_saved_readback", "matching_visualization_id", "fresh_revision"],
                status="approved_with_requirements",
            )
        if "table" in normalized:
            registered = decide_registered_route("table_pivot_js", existing_route="editor_table")
            return self._decision(
                registered,
                requested_route="preserve_existing_object_route",
                family="table_node",
                evidence=("visual_table", "getEditorChart", "updateEditorChart"),
            )
        if "editor" in normalized or "advanced" in normalized or "chart" in normalized:
            registered = decide_registered_route("custom_dom", existing_route="editor_advanced")
            return self._decision(
                registered,
                requested_route="preserve_existing_object_route",
                family="advanced_editor_js",
                evidence=("editor_widgets_advanced", "getEditorChart", "updateEditorChart"),
            )
        return None

    def _evidence(self, feature_id: str, *methods: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        feature = self._feature_cluster(feature_id)
        if feature:
            evidence.append(
                {
                    "kind": "docs_feature",
                    "id": feature.get("id"),
                    "classification": feature.get("classification"),
                    "mcp_surface": feature.get("mcp_surface"),
                    "server_decision": feature.get("server_decision"),
                }
            )
        by_method = self._operations_by_method()
        for method in methods:
            operation = by_method.get(method)
            if operation:
                evidence.append(
                    {
                        "kind": "api_operation",
                        "method_name": operation.get("method_name"),
                        "status": operation.get("status"),
                        "owning_mcp_tool": operation.get("owning_mcp_tool"),
                        "path": operation.get("path"),
                    }
                )
        return evidence

    def _feature_cluster(self, feature_id: str) -> dict[str, Any]:
        for item in self.docs_feature_policy.get("clusters") or []:
            if item.get("id") == feature_id:
                return item
        return {}

    def _operations_by_method(self) -> dict[str, dict[str, Any]]:
        return {str(item.get("method_name")): item for item in self.api_operation_policy.get("operations") or []}


def select_route_v5(
    request: str | NormalizedUserRequest,
    *,
    existing_route: str = "",
    existing_object_type: str = "",
    existing_visualization_id: str = "",
    semantic_output: str = "",
) -> RouteSelectionDecision:
    return RouteSelectionPolicyV5().select(
        request,
        existing_route=existing_route,
        existing_object_type=existing_object_type,
        existing_visualization_id=existing_visualization_id,
        semantic_output=semantic_output,
    )


def select_route_v4(*args: Any, **kwargs: Any) -> RouteSelectionDecision:
    return select_route_v5(*args, **kwargs)


def select_route_v3(*args: Any, **kwargs: Any) -> RouteSelectionDecision:
    return select_route_v5(*args, **kwargs)


RouteSelectionPolicyV4 = RouteSelectionPolicyV5
RouteSelectionPolicyV3 = RouteSelectionPolicyV5


def _load_json(resource_name: str, default: Any) -> Any:
    try:
        return resource_json(resource_name)
    except RuntimeResourceError:
        return default


def _semantic_table(value: str) -> bool:
    return any(term in value for term in ("table", "tabular", "rows", "registry", "таблица", "сводн", "pivot"))


def _semantic_selector(value: str) -> bool:
    return any(term in value for term in ("selector", "filter", "control", "dropdown", "фильтр", "селектор"))


def _semantic_kpi(value: str) -> bool:
    return any(term in value for term in ("kpi", "indicator", "индикатор", "metric card", "metric-card"))


def _explicit_wizard_request(value: str) -> bool:
    return any(term in value for term in ("wizard", "визард", "route=wizard_native", "route=wizard_map_native"))


def _semantic_markdown(value: str) -> bool:
    return any(term in value for term in ("methodology", "markdown", "text block", "методолог", "описание"))


def _semantic_dataset_backed(value: str) -> bool:
    return any(
        term in value
        for term in (
            "uploaded file",
            "uploaded dataset",
            "dataset id",
            "existing dataset",
            "connected file",
            "загруженный файл",
            "датасет",
        )
    )


def _has_visual_semantics(value: str) -> bool:
    return _semantic_table(value) or _semantic_kpi(value) or any(
        term in value
        for term in (
            "chart", "график", "line", "area", "column", "bar", "pie", "donut", "scatter", "bubble",
            "treemap", "map", "карта", "heatmap", "waterfall", "funnel", "sankey", "histogram", "box plot",
        )
    )


def _semantic_family(value: str, *, route_intent: str) -> str:
    mappings = (
        (("resource schedule", "расписан"), "resource_schedule_exception"),
        (("heatmap", "matrix", "теплов"), "heatmap"),
        (("waterfall", "водопад"), "waterfall"),
        (("funnel", "ворон"), "funnel_snapshot"),
        (("sankey", "санке"), "sankey_status_flow"),
        (("histogram", "гистограм"), "histogram"),
        (("box plot", "boxplot", "ящик"), "box_plot"),
        (("bubble", "пузыр"), "bubble"),
        (("scatter", "точечн"), "scatter"),
        (("treemap", "tree map"), "treemap"),
        (("donut", "кольцев"), "donut"),
        (("pie", "кругов"), "pie"),
        (("combined", "combo", "комбинирован"), "combo_time_series_combo"),
        (("100% area", "area100p"), "area_100p"),
        (("area", "област"), "area_completion"),
        (("100%", "stacked 100", "stacked_100"), "stacked_100"),
        (("horizontal bar", "горизонтальн"), "horizontal_bar"),
        (("grouped bar", "grouped column", "группирован"), "grouped_bar"),
        (("column", "столб"), "vertical_bar_time_bucket"),
        (("multiline", "multiple lines", "несколько линий"), "multiline_chart"),
        (("line", "trend", "динамик", "линейн"), "line_chart"),
        (("map", "geo", "карта", "гео"), "native_map_geo_widget"),
    )
    if route_intent == "native_pivot" or "pivot" in value or "сводн" in value:
        return "pivot_table"
    if route_intent == "native_table" or _semantic_table(value):
        return "table_node"
    if _semantic_kpi(value):
        if "spark" in value or "спарк" in value:
            return "kpi_value_delta_sparkline" if "delta" in value or "дельт" in value else "kpi_value_sparkline"
        return "kpi_value_delta" if "delta" in value or "дельт" in value else "kpi_value_only"
    for terms, family in mappings:
        if any(term in value for term in terms):
            return family
    if any(term in value for term in ("custom dom", "custom interaction", "custom html", "custom svg")):
        return "custom_dom"
    return "flat_table"
