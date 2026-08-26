from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from datalens_dev_mcp.runtime_resources import resource_json

MATRIX_RESOURCE = "config/datalens_chart_param_matrix.json"


@dataclass(frozen=True)
class ChartParamSpec:
    family: str
    route: str
    intent: str
    template_dir: str | None
    required_parameters: tuple[str, ...]
    optional_parameters: tuple[str, ...]
    default_sorting: str
    fallback_family: str
    raw: dict[str, Any]

    @property
    def visualization_id(self) -> str:
        return str(self.raw.get("visualization_id") or "")

    @property
    def selection_origin(self) -> str:
        return str(self.raw.get("selection_origin") or "")

    @property
    def capability_gap(self) -> str:
        return str(self.raw.get("capability_gap") or "")

    def brief(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "intent": self.intent,
            "route": self.route,
            "visualization_id": self.visualization_id,
            "selection_origin": self.selection_origin,
            "capability_gap": self.capability_gap,
            "template_dir": self.template_dir,
            "required_parameters": list(self.required_parameters),
            "optional_parameters": list(self.optional_parameters),
            "default_sorting": self.default_sorting,
            "fallback_family": self.fallback_family,
            "ask_user_when": list(self.raw.get("ask_user_when") or []),
            "visual_constraints": list(self.raw.get("visual_constraints") or []),
            "color_strategy": self.raw.get("color_strategy", ""),
        }


@lru_cache(maxsize=1)
def load_chart_param_matrix() -> dict[str, Any]:
    return resource_json(MATRIX_RESOURCE)


def list_chart_param_specs() -> dict[str, ChartParamSpec]:
    return {family: _to_spec(family, data) for family, data in load_chart_param_matrix()["families"].items()}


def get_chart_param_spec(family: str) -> ChartParamSpec:
    specs = list_chart_param_specs()
    if family in specs:
        return specs[family]
    return specs["table_node"]


def route_for_chart_family(family: str) -> str:
    return get_chart_param_spec(family).route


def data_proof_requirements_for_chart(family: str) -> dict[str, Any]:
    """Return conservative typed assertions implied by a chart family without executing arbitrary code."""
    spec = get_chart_param_spec(family)
    assertions: list[str] = ["schema_matches", "pagination_complete"]
    if "kpi" in family:
        assertions.extend(["not_empty", "numeric_range"])
    elif any(token in family for token in ("line", "area", "column", "bar", "scatter", "bubble")):
        assertions.extend(["not_empty", "no_nulls", "sort_total_order"])
    elif "table" in family or "pivot" in family:
        assertions.extend(["sort_total_order"])
    if "selector" in family:
        assertions.extend(["selector_value_available", "selector_empty_means_no_filter"])
    return {
        "family": family,
        "route": spec.route,
        "assertion_kinds": list(dict.fromkeys(assertions)),
        "policy": "caller supplies field GUIDs and business bounds; this helper never invents thresholds",
    }


def _to_spec(family: str, data: dict[str, Any]) -> ChartParamSpec:
    return ChartParamSpec(
        family=family,
        route=data["route"],
        intent=data["intent"],
        template_dir=data.get("template_dir"),
        required_parameters=tuple(data.get("required_parameters") or ()),
        optional_parameters=tuple(data.get("optional_parameters") or ()),
        default_sorting=data["default_sorting"],
        fallback_family=data["fallback_family"],
        raw=data,
    )
