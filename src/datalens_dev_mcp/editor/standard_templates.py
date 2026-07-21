from __future__ import annotations

import hashlib
import json
from typing import Any

from datalens_dev_mcp.editor.selector_contract import (
    DYNAMIC_SELECTOR_FAMILY,
    SELECTOR_FAMILIES,
    STATIC_SELECTOR_FAMILIES,
    normalize_selector_contract,
    selector_params,
)
from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.layout_contract import plan_selector_row_widths
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
    "selector_family_dynamic": ("value",),
}

MARKDOWN_FAMILIES = {
    "md_methodology_block",
    "md_section_header",
    "md_dashboard_owner",
    "md_contact_block",
    "md_requirements_link_block",
    "md_source_notes",
}


def _params_js(params_resource: str, *, variant: str, visual_spec: dict[str, Any] | None = None) -> str:
    params = resource_json(params_resource) if resource_exists(params_resource) else {}
    invalid = [
        name
        for name, values in params.items()
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values)
    ]
    if invalid:
        raise ValueError(
            "DataLens Editor Params values must be arrays of strings: "
            + ", ".join(sorted(invalid))
        )
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
    markdown: str | None = None,
    param: str | None = None,
    options: list[str] | None = None,
    selector_contract: dict[str, Any] | None = None,
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
    fixture_input = (
        resource_json(f"{template_dir}/example_input.json")
        if source_mode == GOLDEN_FIXTURE_SOURCE_MODE and resource_exists(f"{template_dir}/example_input.json")
        else {}
    )
    effective_markdown = markdown
    effective_param = str(param or "").strip()
    effective_options = [str(value) for value in (options or [])]
    effective_selector_contract = selector_contract
    caller_supplied_legacy_selector = bool(effective_param or effective_options)
    if source_mode == GOLDEN_FIXTURE_SOURCE_MODE:
        if effective_markdown in (None, ""):
            effective_markdown = str(fixture_input.get("markdown") or "")
        if (
            effective_selector_contract is None
            and not caller_supplied_legacy_selector
            and isinstance(fixture_input.get("selector_contract"), dict)
        ):
            effective_selector_contract = fixture_input["selector_contract"]
        if effective_selector_contract is None:
            if not effective_param:
                effective_param = str(fixture_input.get("param") or "")
            if not effective_options:
                effective_options = [str(value) for value in (fixture_input.get("options") or [])]
    normalized_selector_contract = (
        normalize_selector_contract(
            family=template_family,
            title=title,
            selector_contract=effective_selector_contract,
            param=effective_param or None,
            options=effective_options or None,
        )
        if template_family in SELECTOR_FAMILIES
        else {}
    )

    tabs: dict[str, str] = {}
    for file_name in spec["required_files"]:
        if file_name in {"schema.json", "example_input.json", "README.md", "params.json"}:
            continue
        text = resource_text(f"{template_dir}/{file_name}")
        if file_name == "prepare.js":
            if route == "editor_markdown":
                text = _markdown_prepare_js(
                    variant=template_family,
                    title=title,
                    markdown=effective_markdown,
                )
            else:
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
        elif file_name == "controls.js" and route == "editor_js_control":
            text = (
                _selector_controls_js(
                    variant=template_family,
                    contract=normalized_selector_contract,
                )
                if normalized_selector_contract.get("ok")
                else "module.exports = {controls: []};\n"
            )
        tabs[file_name] = text
    if source_mode == PRODUCTION_SOURCE_MODE and route in {"editor_advanced", "editor_table"}:
        source_tabs, source_contract = build_dataset_source_binding(
            dataset_alias=dataset_alias,
            columns=columns,
            required_columns=required_source_columns(template_family),
        )
        tabs.update(source_tabs)
    elif source_mode == PRODUCTION_SOURCE_MODE and template_family == DYNAMIC_SELECTOR_FAMILY:
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
    if normalized_selector_contract and not normalized_selector_contract["ok"]:
        source_contract = _merge_blocking_contract(
            source_contract,
            status="blocked_missing_input",
            issues=list(normalized_selector_contract["issues"]),
        )
    if (
        source_mode == PRODUCTION_SOURCE_MODE
        and template_family in MARKDOWN_FAMILIES
        and template_family != "md_section_header"
        and not str(effective_markdown or "").strip()
    ):
        source_contract = _blocked_input_contract(
            code="missing_markdown_content",
            message="Provide explicit Markdown content; production bundles never invent business metadata.",
        )
    params_resource = f"{template_dir}/params.json"
    if resource_exists(params_resource):
        tabs["params.js"] = _params_js(params_resource, variant=spec["variant"], visual_spec=visual_spec)
    if route == "editor_js_control":
        tabs["params.js"] = (
            _selector_params_js(normalized_selector_contract)
            if normalized_selector_contract.get("ok")
            else "module.exports = {};\n"
        )
    if route == "editor_advanced" and "controls.js" not in tabs:
        tabs["controls.js"] = "module.exports = {};\n"

    route_spec = ROUTE_CONTRACT.spec(route)
    template_provenance = _template_provenance(
        template_dir=template_dir,
        required_files=list(spec["required_files"]),
        tabs=tabs,
    )
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
        "selector_contract": normalized_selector_contract,
        "renderer_visual_spec": visual_spec or {},
        "source_template": spec["template_dir"],
        "source_gallery": spec["template_dir"],
        "template_provenance": template_provenance,
        "generation_status": (
            "ready" if source_contract["status"] in {"ready", "not_required"} else source_contract["status"]
        ),
        "source_contract": source_contract,
        "blocking_issues": [] if source_contract["status"] in {"ready", "fixture_only"} else source_contract["issues"],
        "tabs": tabs,
    }


def _template_provenance(
    *,
    template_dir: str,
    required_files: list[str],
    tabs: dict[str, str],
) -> dict[str, Any]:
    resource_paths = [f"{template_dir}/{name}" for name in required_files]
    if "prepare.js" in tabs:
        resource_paths.extend(SHARED_PLACEHOLDERS.values())
    resource_paths = list(dict.fromkeys(path for path in resource_paths if resource_exists(path)))
    asset_rows = [
        {
            "path": path,
            "sha256": hashlib.sha256(resource_text(path).encode("utf-8")).hexdigest(),
        }
        for path in resource_paths
    ]
    asset_canonical = json.dumps(asset_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    tabs_canonical = json.dumps(tabs, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "policy": "exact_registered_asset",
        "approximate_fallback_used": False,
        "source_template": template_dir,
        "asset_count": len(asset_rows),
        "template_asset_sha256": hashlib.sha256(asset_canonical.encode("utf-8")).hexdigest(),
        "compiled_tabs_sha256": hashlib.sha256(tabs_canonical.encode("utf-8")).hexdigest(),
    }


def _blocked_input_contract(*, code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked_missing_input",
        "production_ready": False,
        "binding": "none",
        "required_output_columns": [],
        "issues": [{"code": code, "message": message}],
    }


def _merge_blocking_contract(
    source_contract: dict[str, Any],
    *,
    status: str,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    merged = dict(source_contract)
    merged["status"] = status
    merged["production_ready"] = False
    merged["issues"] = [*(source_contract.get("issues") or []), *issues]
    return merged


def _selector_controls_js(
    *,
    variant: str,
    contract: dict[str, Any],
) -> str:
    if not contract.get("ok"):
        raise ValueError("selector controls require a complete normalized selector contract")
    parameters = selector_params(contract)
    if not parameters:
        raise ValueError("selector controls require at least one parameter")
    width = plan_selector_row_widths(["selector"])["selector"]
    common = (
        f"      label: {json.dumps(contract['label'], ensure_ascii=False)},\n"
        "      labelPlacement: 'left',\n"
        f"      width: '{width}',\n"
        "      updateOnChange: true,\n"
    )
    if variant == "date_range_selector":
        if contract.get("param"):
            parameter_binding = f"      param: {json.dumps(contract['param'], ensure_ascii=False)},\n"
        else:
            parameter_binding = (
                f"      paramFrom: {json.dumps(contract['param_from'], ensure_ascii=False)},\n"
                f"      paramTo: {json.dumps(contract['param_to'], ensure_ascii=False)},\n"
            )
        return (
            "module.exports = {\n"
            "  controls: [\n"
            "    {\n"
            "      type: 'range-datepicker',\n"
            f"{parameter_binding}"
            f"{common}"
            "    },\n"
            "  ],\n"
            "};\n"
        )

    dynamic = variant == DYNAMIC_SELECTOR_FAMILY
    if dynamic:
        content_source = (
            "const loaded = Editor.getLoadedData();\n"
            "function preparedRows(source) {\n"
            "  if (Array.isArray(source)) {\n"
            "    const names = source.find((item) => item && item.event === 'metadata')?.data?.names || [];\n"
            "    const eventRows = source.filter((item) => item && item.event === 'row' && Array.isArray(item.data));\n"
            "    if (names.length && eventRows.length) {\n"
            "      return eventRows.map((item) => Object.fromEntries(\n"
            "        item.data.map((value, index) => [names[index] || `column_${index + 1}`, value]),\n"
            "      ));\n"
            "    }\n"
            "    return source.filter((item) => item && typeof item === 'object' && !item.event);\n"
            "  }\n"
            "  const result = source?.result || {};\n"
            "  const rawRows = result.data?.Data || [];\n"
            "  const fields = result.fields || [];\n"
            "  const names = fields.map((field, index) => String(field.title || field.guid || index));\n"
            "  return rawRows.map((row) => Object.fromEntries(\n"
            "    row.map((value, index) => [names[index] || `column_${index + 1}`, value]),\n"
            "  ));\n"
            "}\n"
            "const rows = preparedRows(loaded.rows || []);\n"
            "const seen = new Set();\n"
            "const content = rows.flatMap((row) => {\n"
            "  const value = String(row?.value ?? '');\n"
            "  if (!value || seen.has(value)) return [];\n"
            "  seen.add(value);\n"
            "  const rawTitle = row?.title;\n"
            "  return [{title: String(rawTitle ?? value), value}];\n"
            "});\n\n"
        )
        content_expression = "content"
    else:
        content_source = ""
        content_expression = json.dumps(contract["options"], ensure_ascii=False)
    multiselect = variant == "multi_select_dropdown"
    searchable = variant in {"multi_select_dropdown", "search_selector", "selector_family_dynamic"}
    return (
        content_source
        + "module.exports = {\n"
        "  controls: [\n"
        "    {\n"
        "      type: 'select',\n"
        f"      param: {json.dumps(contract['param'], ensure_ascii=False)},\n"
        f"{common}"
        f"      multiselect: {str(multiselect).lower()},\n"
        f"      searchable: {str(searchable).lower()},\n"
        f"      content: {content_expression},\n"
        "    },\n"
        "  ],\n"
        "};\n"
    )


def _selector_params_js(
    contract: dict[str, Any],
) -> str:
    if not contract.get("ok"):
        raise ValueError("selector Params require a complete normalized selector contract")
    if contract.get("param_from") and contract.get("param_to"):
        payload = {
            contract["param_from"]: [contract["default_from"]] if contract.get("default_from") else [],
            contract["param_to"]: [contract["default_to"]] if contract.get("default_to") else [],
        }
    else:
        payload = {
            contract["param"]: list(contract.get("default_values") or []),
        }
    if not all(
        isinstance(values, list) and all(isinstance(value, str) for value in values)
        for values in payload.values()
    ):
        raise ValueError("DataLens Editor Params values must be arrays of strings")
    return "module.exports = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"


def _markdown_prepare_js(*, variant: str, title: str, markdown: str | None) -> str:
    if str(markdown or "").strip():
        body = str(markdown)
    elif variant == "md_section_header":
        body = f"## {title}"
    else:
        body = ""
    return f"const markdown = {json.dumps(body, ensure_ascii=False)};\nmodule.exports = {{markdown}};\n"


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
