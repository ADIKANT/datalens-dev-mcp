from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteSpec:
    route: str
    entry_type: str
    create_method: str
    read_method: str
    update_method: str
    widget_kind: str
    required_tabs: tuple[str, ...]
    allowed_use: str


@dataclass(frozen=True)
class RouteContract:
    routes: dict[str, RouteSpec]
    forbidden_terms: tuple[str, ...]
    valid_geo_evidence_kinds: tuple[str, ...]

    def spec(self, route: str) -> RouteSpec:
        normalized = ROUTE_ALIASES.get(route, route)
        return self.routes[normalized]


ROUTE_ALIASES = {
    "editor_selector": "editor_js_control",
    "editor_control": "editor_js_control",
    "wizard_map_native": "wizard_native",
}

ROUTE_CONTRACT = RouteContract(
    routes={
        "editor_advanced": RouteSpec(
            route="editor_advanced",
            entry_type="advanced-chart_node",
            create_method="createEditorChart",
            read_method="getEditorChart",
            update_method="updateEditorChart",
            widget_kind="visual",
            required_tabs=("meta.json", "params.js", "sources.js", "controls.js", "prepare.js"),
            allowed_use="Non-map custom visual widgets.",
        ),
        "editor_table": RouteSpec(
            route="editor_table",
            entry_type="table_node",
            create_method="createEditorChart",
            read_method="getEditorChart",
            update_method="updateEditorChart",
            widget_kind="visual",
            required_tabs=("meta.json", "params.js", "sources.js", "prepare.js", "config.js"),
            allowed_use="Simple and pivot JavaScript tables with config.",
        ),
        "editor_markdown": RouteSpec(
            route="editor_markdown",
            entry_type="markdown_node",
            create_method="createEditorChart",
            read_method="getEditorChart",
            update_method="updateEditorChart",
            widget_kind="visual",
            required_tabs=("meta.json", "params.js", "sources.js", "prepare.js"),
            allowed_use="Text-only Markdown widgets.",
        ),
        "editor_js_control": RouteSpec(
            route="editor_js_control",
            entry_type="control_node",
            create_method="createEditorChart",
            read_method="getEditorChart",
            update_method="updateEditorChart",
            widget_kind="control",
            required_tabs=("meta.json", "params.js", "sources.js", "controls.js"),
            allowed_use="Selectors and parameter controls.",
        ),
        "wizard_native": RouteSpec(
            route="wizard_native",
            entry_type="wizard_chart",
            create_method="createWizardChart",
            read_method="getWizardChart",
            update_method="updateWizardChart",
            widget_kind="visual",
            required_tabs=(),
            allowed_use="Standard native Wizard visualizations; geolayer additionally requires validated geo evidence.",
        ),
        "ql_explicit": RouteSpec(
            route="ql_explicit",
            entry_type="ql_chart",
            create_method="createQLChart",
            read_method="getQLChart",
            update_method="updateQLChart",
            widget_kind="visual",
            required_tabs=(),
            allowed_use="QL read/create/update only after a direct user request and with an explicit payload or fresh saved seed.",
        ),
    },
    forbidden_terms=(
        "d3_node",
        "graph_ql_node",
        "table_ql_node",
        "deleteQLChart",
        "regular Editor Chart",
        "Gravity UI Charts",
        "@gravity-ui/charts",
        "native-first fallback",
    ),
    valid_geo_evidence_kinds=("geopoint", "geopolygon", "lat_lon", "validated_map_payload"),
)


def normalize_route(route: str) -> str:
    return ROUTE_ALIASES.get(route, route)


def route_contract_document() -> str:
    lines = ["# DataLens Route Contract", "", "Operational routes are closed:"]
    for route, spec in ROUTE_CONTRACT.routes.items():
        lines.append(f"- `{route}` -> `{spec.entry_type}` via `{spec.create_method}` / `{spec.update_method}`: {spec.allowed_use}")
    lines.extend(
        [
            "",
            "QL is explicit-only and never an automatic route. Forbidden by default: d3_node, regular Editor Chart,",
            "Gravity UI Charts, QL delete, guessed IDs, destructive operations, blind writes, and blind publish.",
        ]
    )
    return "\n".join(lines) + "\n"
