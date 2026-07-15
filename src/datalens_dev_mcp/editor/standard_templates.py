from __future__ import annotations

import json
from typing import Any

from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT
from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_exists, resource_json, resource_text


REGISTRY_RESOURCE = "templates/datalens/standard_chart_templates.json"
PRODUCTION_SOURCE_MODE = "production"
GOLDEN_FIXTURE_SOURCE_MODE = "golden_fixture"
SHARED_PLACEHOLDERS = {
    "/* __DATALENS_SHARED_STYLE_TOKENS__ */": "templates/datalens/advanced_editor/_shared/style_tokens.js",
    "/* __DATALENS_SHARED_RENDER_HELPERS__ */": "templates/datalens/advanced_editor/_shared/render_helpers.js",
}

# Standard prepare.js files consume these stable output aliases. Production
# generation must bind a caller-owned dataset that exposes the aliases instead
# of copying the example SQL stored with the template archetype.
STANDARD_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "kpi_value_only": ("current_value",),
    "kpi_value_delta": ("current_value", "comparator_value"),
    "kpi_value_sparkline": ("current_value", "sparkline"),
    "kpi_value_delta_sparkline": ("current_value", "comparator_value", "sparkline"),
    "line_chart": ("bucket", "value"),
    "multiline_chart": ("bucket", "metric", "value"),
    "area_completion": ("bucket", "value"),
    "vertical_bar_time_bucket": ("bucket", "value"),
    "combo_time_series_combo": ("bucket", "metric", "value"),
    "funnel_snapshot": ("bucket", "value"),
    "horizontal_bar": ("label", "value"),
    "grouped_bar": ("label", "group", "value"),
    "stacked_100": ("label", "value"),
    "bullet_assignees": ("label", "value", "target"),
    "heatmap": ("label", "value"),
    "waterfall": ("label", "value"),
    "histogram": ("label", "value"),
    "box_plot": ("label", "min", "q1", "median", "q3", "max"),
    "scatter": ("label", "x", "y"),
    "bubble": ("label", "x", "y", "size"),
    "pie": ("label", "value"),
    "donut": ("label", "value"),
    "treemap": ("label", "value"),
    "sankey_status_flow": ("source", "target", "value"),
    "resource_schedule_exception": ("resource_id", "resource_name", "item_id", "start_at", "end_at", "status"),
}


def _params_js(params_resource: str, *, variant: str, visual_spec: dict[str, Any] | None = None) -> str:
    params = resource_json(params_resource) if resource_exists(params_resource) else {}
    params["chart_variant"] = variant
    if visual_spec:
        params["renderer_visual_spec"] = visual_spec
    return "module.exports = " + json.dumps(params, ensure_ascii=False, indent=2) + ";\n"


def load_standard_template_bundle(
    *,
    widget_id: str,
    route: str,
    title: str,
    family: str | None,
    visual_spec: dict[str, Any] | None = None,
    dataset_alias: str | None = None,
    columns: list[str] | None = None,
    source_mode: str = PRODUCTION_SOURCE_MODE,
) -> dict[str, Any] | None:
    if not family:
        return None
    resolution = resolve_chart_family(family)
    template_family = resolution.approved_alternative
    try:
        registry = resource_json(REGISTRY_RESOURCE)
    except RuntimeResourceError:
        return None
    spec = (registry.get("families") or {}).get(template_family)
    if not spec or spec.get("route") != route:
        return None
    param_spec = get_chart_param_spec(template_family)
    template_dir = str(spec["template_dir"]).strip().rstrip("/")
    if source_mode not in {PRODUCTION_SOURCE_MODE, GOLDEN_FIXTURE_SOURCE_MODE}:
        raise ValueError(f"unsupported standard template source_mode: {source_mode}")

    tabs: dict[str, str] = {}
    for file_name in spec["required_files"]:
        if file_name in {"schema.json", "example_input.json", "README.md", "params.json"}:
            continue
        text = resource_text(f"{template_dir}/{file_name}")
        if file_name == "prepare.js":
            text = _inline_shared_helpers(text)
            text = text.replace("__TEMPLATE_VARIANT__", spec["variant"])
            text = text.replace(
                "__SHOW_DELTA__",
                "true" if template_family in {"kpi_value_delta", "kpi_value_delta_sparkline"} else "false",
            )
            text = text.replace(
                "__SHOW_SPARKLINE__",
                "true" if template_family in {"kpi_value_sparkline", "kpi_value_delta_sparkline"} else "false",
            )
        tabs[file_name] = text
    if source_mode == PRODUCTION_SOURCE_MODE and route in {"editor_advanced", "editor_table"}:
        source_tabs, source_contract = build_dataset_source_binding(
            dataset_alias=dataset_alias,
            columns=columns,
            required_columns=required_source_columns(template_family),
        )
        tabs.update(source_tabs)
    elif source_mode == PRODUCTION_SOURCE_MODE:
        # Markdown and JS controls do not need a dataset by default. Remove the
        # archetype connection placeholder while keeping their empty source tab.
        tabs["meta.json"] = json.dumps({"links": {}}, ensure_ascii=False, indent=2)
        tabs["sources.js"] = "module.exports = {};\n"
        source_contract = {
            "status": "not_required",
            "production_ready": True,
            "binding": "none",
            "required_output_columns": [],
            "issues": [],
        }
    else:
        source_contract = {
            "status": "fixture_only",
            "production_ready": False,
            "binding": "template_fixture",
            "required_output_columns": list(required_source_columns(template_family)),
            "issues": [
                {
                    "code": "fixture_source_not_production_ready",
                    "message": "Template example rows are allowed only in the static golden gallery.",
                }
            ],
        }
    params_resource = f"{template_dir}/params.json"
    if resource_exists(params_resource):
        tabs["params.js"] = _params_js(params_resource, variant=spec["variant"], visual_spec=visual_spec)
    if route == "editor_advanced" and "controls.js" not in tabs:
        tabs["controls.js"] = "module.exports = {};\n"

    route_spec = ROUTE_CONTRACT.spec(route)
    return {
        "schema_version": "2026-06-03.standard_template_bundle.v1",
        "widget_id": widget_id,
        "name": _canonical_name(route=route, title=title, technical_key=widget_id),
        "display_title": title,
        "route": route,
        "entry_type": route_spec.entry_type,
        "family": template_family,
        "requested_family": family,
        "template_status": spec.get("status", "IMPLEMENTED"),
        "implemented_behavior": spec.get("implemented_behavior", ""),
        "fallback_family": spec.get("fallback_family", ""),
        "parameter_spec": param_spec.brief(),
        "renderer_visual_spec": visual_spec or {},
        "source_template": spec["template_dir"],
        "source_gallery": spec["template_dir"],
        "generation_status": (
            "ready" if source_contract["status"] in {"ready", "not_required"} else source_contract["status"]
        ),
        "source_contract": source_contract,
        "blocking_issues": [] if source_contract["status"] in {"ready", "fixture_only"} else source_contract["issues"],
        "tabs": tabs,
    }


def required_source_columns(family: str | None) -> tuple[str, ...]:
    if not family:
        return ()
    resolution = resolve_chart_family(family)
    return STANDARD_SOURCE_COLUMNS.get(resolution.approved_alternative, ())


def build_dataset_source_binding(
    *,
    dataset_alias: str | None,
    columns: list[str] | None,
    required_columns: tuple[str, ...] = (),
) -> tuple[dict[str, str], dict[str, Any]]:
    alias = str(dataset_alias or "").strip()
    normalized_columns = list(dict.fromkeys(str(column).strip() for column in (columns or []) if str(column).strip()))
    missing_output_columns = [column for column in required_columns if column not in normalized_columns]
    issues: list[dict[str, str]] = []
    if not alias:
        issues.append(
            {
                "code": "missing_dataset_alias",
                "message": "Provide dataset_alias for the production Editor source binding.",
            }
        )
    if not normalized_columns:
        issues.append(
            {
                "code": "missing_source_columns",
                "message": "Provide the dataset columns consumed by the selected renderer.",
            }
        )
    if missing_output_columns:
        issues.append(
            {
                "code": "missing_renderer_output_columns",
                "message": "Dataset must expose these renderer aliases: " + ", ".join(missing_output_columns),
            }
        )

    if issues:
        tabs = {
            "meta.json": json.dumps({"links": {}}, ensure_ascii=False, indent=2),
            "sources.js": (
                "// BLOCKED: no validated production source binding was supplied.\n"
                "// Provide dataset_alias and the renderer output columns listed in source_contract.\n"
                "module.exports = {};\n"
            ),
        }
        return tabs, {
            "status": "blocked_missing_source",
            "production_ready": False,
            "binding": "empty",
            "dataset_alias": alias,
            "columns": normalized_columns,
            "required_output_columns": list(required_columns),
            "missing_output_columns": missing_output_columns,
            "issues": issues,
        }

    columns_js = json.dumps(normalized_columns, ensure_ascii=False)
    tabs = {
        "meta.json": json.dumps({"links": {"dataset": alias}}, ensure_ascii=False, indent=2),
        "sources.js": (
            "const {buildSource} = require('libs/dataset/v2');\n\n"
            "module.exports = {\n"
            "  rows: buildSource({\n"
            "    datasetId: Editor.getId('dataset'),\n"
            f"    columns: {columns_js},\n"
            "  }),\n"
            "};\n"
        ),
    }
    return tabs, {
        "status": "ready",
        "production_ready": True,
        "binding": "dataset",
        "dataset_alias": alias,
        "columns": normalized_columns,
        "required_output_columns": list(required_columns),
        "missing_output_columns": [],
        "issues": [],
    }


def _canonical_name(*, route: str, title: str, technical_key: str = "") -> str:
    kind = {
        "editor_table": "table",
        "editor_markdown": "md",
        "editor_js_control": "selector",
    }.get(route, "chart")
    words = "".join(ch.lower() if ch.isalnum() else " " for ch in title).split()[:4]
    if any(not char.isascii() and char.isalnum() for char in title):
        key_words = "".join(ch.lower() if ch.isalnum() else " " for ch in technical_key).split()[:2]
        words.extend(key_words)
    return "js - " + kind + " " + (" ".join(words) or "standard")


def _inline_shared_helpers(text: str) -> str:
    bundled = text
    legacy_require_map = {
        "const {HOUSE_STYLE} = require('../_shared/style_tokens');": "/* __DATALENS_SHARED_STYLE_TOKENS__ */",
        "const {normalizeRows, themeName} = require('../_shared/render_helpers');": "/* __DATALENS_SHARED_RENDER_HELPERS__ */",
    }
    for legacy, placeholder in legacy_require_map.items():
        bundled = bundled.replace(legacy, placeholder)
    for placeholder, resource_path in SHARED_PLACEHOLDERS.items():
        if placeholder not in bundled:
            continue
        helper = _shared_helper_source(resource_path)
        bundled = bundled.replace(placeholder, helper)
    return bundled


def _shared_helper_source(resource_path: str) -> str:
    text = resource_text(resource_path)
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("module.exports"):
            continue
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"
