from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.layout_contract import plan_selector_row_widths
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT, normalize_route
from datalens_dev_mcp.editor.standard_templates import (
    GOLDEN_FIXTURE_SOURCE_MODE,
    PRODUCTION_SOURCE_MODE,
    build_dataset_source_binding,
    load_standard_template_bundle,
)
from datalens_dev_mcp.editor.visual_spec import build_renderer_visual_spec, normalize_renderer_visual_spec


REPO_ROOT = Path(__file__).resolve().parents[3]
GALLERY_ROOT = REPO_ROOT / "examples" / "gallery"
FAMILY_GALLERY = {
    "kpi_value_only": "kpi-status",
    "kpi_value_delta": "kpi-status",
    "kpi_value_sparkline": "kpi-status",
    "kpi_value_delta_sparkline": "kpi-status",
    "line_chart": "timeseries-combo",
    "multiline_chart": "timeseries-combo",
    "area_completion": "timeseries-combo",
    "vertical_bar_time_bucket": "timeseries-combo",
    "combo_time_series_combo": "timeseries-combo",
    "horizontal_bar": "ranking-comparison",
    "grouped_bar": "ranking-comparison",
    "stacked_100": "ranking-comparison",
    "bullet_assignees": "ranking-comparison",
    "heatmap": "diagnostics",
    "histogram": "diagnostics",
    "box_plot": "diagnostics",
    "scatter": "diagnostics",
    "bubble": "diagnostics",
    "waterfall": "contribution-distribution",
    "funnel_snapshot": "funnel",
    "sankey_status_flow": "funnel",
    "pie": "hierarchy",
    "donut": "hierarchy",
    "treemap": "hierarchy",
    "table_node": "editor-table-registry",
    "md_methodology_block": "editor-markdown-block",
    "md_section_header": "editor-markdown-block",
    "md_dashboard_owner": "editor-markdown-block",
    "md_contact_block": "editor-markdown-block",
    "md_requirements_link_block": "editor-markdown-block",
    "md_source_notes": "editor-markdown-block",
    "single_select_dropdown": "selector-wiring",
    "multi_select_dropdown": "selector-wiring",
    "search_selector": "selector-wiring",
    "date_range_selector": "selector-wiring",
    "selector_family_static": "selector-wiring",
    "selector_family_dynamic": "selector-wiring",
}


def _js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _default_meta(dataset_alias: str | None = None) -> str:
    links = {"dataset": dataset_alias} if dataset_alias else {}
    return json.dumps({"links": links}, ensure_ascii=False, indent=2)


def _default_params(param: str | None = None) -> str:
    if not param:
        return "module.exports = {};\n"
    return f"module.exports = {{\n  {param}: ['all'],\n}};\n"


def _default_sources(dataset_alias: str | None, columns: list[str] | None) -> str:
    if not dataset_alias or not columns:
        return "module.exports = {};\n"
    columns_js = json.dumps(columns, ensure_ascii=False)
    return (
        "const {buildSource} = require('libs/dataset/v2');\n\n"
        "module.exports = {\n"
        "  rows: buildSource({\n"
        "    datasetId: Editor.getId('dataset'),\n"
        f"    columns: {columns_js},\n"
        "  }),\n"
        "};\n"
    )


def _table_prepare(columns: list[str] | None) -> str:
    safe_columns = columns or ["name", "value"]
    columns_js = json.dumps(safe_columns, ensure_ascii=False)
    return (
        "const loaded = Editor.getLoadedData();\n"
        "const rawRows = loaded.rows?.result?.data?.Data || [];\n"
        "const fields = loaded.rows?.result?.fields || [];\n"
        "const names = fields.map((field, index) => field.title || field.guid || String(index));\n"
        "const objects = rawRows.map(row => Object.fromEntries(row.map((value, index) => [names[index], value])));\n"
        f"const columns = {columns_js};\n"
        "const numericNames = new Set(['value', 'amount', 'count', 'total']);\n"
        "const numericValues = objects.map(item => Number(item.value || item.amount || item.count || item.total || 0));\n"
        "const maxValue = Math.max(1, ...numericValues);\n"
        "const head = columns.map(name => numericNames.has(name) ? "
        "({id: name, name, type: 'bar', min: 0, max: maxValue, barColor: '#2f80ed', "
        "barHeight: '70%', showLabel: true}) : ({id: name, name, type: 'text'}));\n"
        "const rows = objects.map(item => ({cells: columns.map(name => numericNames.has(name) ? "
        "({value: Number(item[name] || 0), formattedValue: String(item[name] ?? '')}) : "
        "({value: item[name] ?? ''}))}));\n"
        "module.exports = {head, rows};\n"
    )


def _advanced_prepare(title: str) -> str:
    return (
        "const model = {\n"
        "  body: 'Ready for governed implementation.',\n"
        "};\n\n"
        "module.exports = {\n"
        "  render: Editor.wrapFn({\n"
        "    args: [model],\n"
        "    fn: function(options, data) {\n"
        "      function esc(value) {\n"
        "        return String(value == null ? '' : value)\n"
        "          .replace(/&/g, '&amp;')\n"
        "          .replace(/</g, '&lt;')\n"
        "          .replace(/>/g, '&gt;')\n"
        "          .replace(/\"/g, '&quot;');\n"
        "      }\n"
        "      return Editor.generateHtml(`<div style=\"font-family:Arial,sans-serif;padding:12px\">"
        "<div>${esc(data.body)}</div></div>`);\n"
        "    },\n"
        "  }),\n"
        "};\n"
    )


def _escape_template(value: str) -> str:
    return re.sub(r"[`$]", "", value)


def _markdown_prepare(markdown: str | None, title: str) -> str:
    body = markdown or f"## {title}\n\nSynthetic markdown block."
    return f"const markdown = {_js_string(body)};\nmodule.exports = {{markdown}};\n"


def _controls(param: str | None, options: list[str] | None, title: str) -> str:
    param_name = param or "segment"
    width = plan_selector_row_widths([param_name])[param_name]
    values = options or ["all"]
    content = [{"title": value, "value": str(value)} for value in values]
    return (
        "module.exports = {\n"
        "  controls: [\n"
        "    {\n"
        "      type: 'select',\n"
        f"      param: {_js_string(param_name)},\n"
        f"      label: {_js_string(title)},\n"
        "      labelPlacement: 'left',\n"
        f"      width: '{width}',\n"
        "      multiselect: true,\n"
        "      searchable: true,\n"
        "      updateOnChange: true,\n"
        f"      content: {json.dumps(content, ensure_ascii=False)},\n"
        "    },\n"
        "  ],\n"
        "};\n"
    )


def generate_editor_bundle(
    *,
    widget_id: str,
    route: str,
    title: str,
    dataset_alias: str | None = None,
    columns: list[str] | None = None,
    markdown: str | None = None,
    param: str | None = None,
    options: list[str] | None = None,
    family: str | None = None,
    visual_spec: dict[str, Any] | None = None,
    chart_decision_record: dict[str, Any] | None = None,
    source_mode: str = PRODUCTION_SOURCE_MODE,
) -> dict[str, Any]:
    if source_mode not in {PRODUCTION_SOURCE_MODE, GOLDEN_FIXTURE_SOURCE_MODE}:
        raise ValueError(f"unsupported Editor bundle source_mode: {source_mode}")
    normalized = normalize_route(route)
    if normalized in {"wizard_native", "ql_explicit"}:
        raise ValueError(f"{normalized} uses a native lifecycle payload, not an Editor tab bundle.")
    family_resolution = resolve_chart_family(family) if family else None
    if family_resolution and family_resolution.status == "reference_only":
        raise ValueError(
            f"{family_resolution.requested} is reference-only and cannot be generated; "
            f"use {family_resolution.approved_alternative}."
        )
    requested_visual_spec = normalize_renderer_visual_spec(visual_spec)
    if not requested_visual_spec and family:
        requested_visual_spec = build_renderer_visual_spec(
            family=family_resolution.approved_alternative if family_resolution else family,
            route=normalized,
            analytical_task="unknown",
            chart_purpose=title,
        ).to_dict()
    standard_bundle = load_standard_template_bundle(
        widget_id=widget_id,
        route=normalized,
        title=title,
        family=family,
        visual_spec=requested_visual_spec,
        dataset_alias=dataset_alias,
        columns=columns,
        source_mode=source_mode,
    )
    if standard_bundle:
        if chart_decision_record:
            standard_bundle["chart_decision_record"] = chart_decision_record
        return standard_bundle
    gallery_bundle = None
    if source_mode == GOLDEN_FIXTURE_SOURCE_MODE:
        gallery_bundle = _gallery_bundle(
            widget_id=widget_id,
            route=normalized,
            title=title,
            family=family,
        )
    if gallery_bundle:
        if requested_visual_spec:
            gallery_bundle["renderer_visual_spec"] = requested_visual_spec
        if chart_decision_record:
            gallery_bundle["chart_decision_record"] = chart_decision_record
        return gallery_bundle
    spec = ROUTE_CONTRACT.spec(normalized)
    tabs: dict[str, str] = {
        "meta.json": _default_meta(dataset_alias),
        "params.js": _default_params(param),
        "sources.js": _default_sources(dataset_alias, columns),
    }
    source_contract: dict[str, Any]
    if normalized in {"editor_advanced", "editor_table"}:
        source_tabs, source_contract = build_dataset_source_binding(
            dataset_alias=dataset_alias,
            columns=columns,
            required_columns=tuple(columns or ()),
        )
        tabs.update(source_tabs)
    else:
        source_contract = {
            "status": "not_required",
            "production_ready": True,
            "binding": "none",
            "required_output_columns": [],
            "issues": [],
        }
    if normalized == "editor_table":
        tabs["prepare.js"] = _table_prepare(columns)
        tabs["config.js"] = "module.exports = {size: 'm', paginator: {enabled: true, limit: 50}};\n"
    elif normalized == "editor_markdown":
        tabs["prepare.js"] = _markdown_prepare(markdown, title)
    elif normalized == "editor_js_control":
        tabs["controls.js"] = _controls(param, options, title)
    else:
        tabs["controls.js"] = "module.exports = {};\n"
        tabs["prepare.js"] = _advanced_prepare(title)
    blocking_issues = list(source_contract.get("issues") or [])
    if normalized == "editor_advanced":
        blocking_issues.append(
            {
                "code": "missing_standard_chart_family",
                "message": "Choose an approved Advanced Editor family before compiling a production payload.",
            }
        )
    generation_status = "ready" if not blocking_issues else "blocked_missing_source_or_family"
    return {
        "schema_version": "2026-05-25.editor_tab_bundle.v1",
        "widget_id": widget_id,
        "name": _canonical_name(route=normalized, title=title, widget_id=widget_id),
        "display_title": title,
        "route": normalized,
        "entry_type": spec.entry_type,
        "renderer_visual_spec": requested_visual_spec,
        "chart_decision_record": chart_decision_record or {},
        "generation_status": generation_status,
        "source_contract": source_contract,
        "blocking_issues": blocking_issues,
        "tabs": tabs,
    }


def _canonical_name(*, route: str, title: str, widget_id: str = "") -> str:
    kind = {
        "editor_table": "table",
        "editor_markdown": "md",
        "editor_js_control": "selector",
    }.get(route, "chart")
    words = "".join(ch.lower() if ch.isalnum() else " " for ch in title).split()[:4]
    if any(not char.isascii() and char.isalnum() for char in title):
        key_words = "".join(ch.lower() if ch.isalnum() else " " for ch in widget_id).split()[:2]
        words.extend(key_words)
    if not words:
        words = re.findall(r"[a-z0-9]+", widget_id.lower())[:4]
    return "js - " + kind + " " + (" ".join(words) or "object")


def _gallery_bundle(*, widget_id: str, route: str, title: str, family: str | None) -> dict[str, Any] | None:
    candidates = []
    requested_family = family
    resolved_family = family
    if family:
        resolution = resolve_chart_family(family)
        resolved_family = resolution.approved_alternative
        if resolved_family in FAMILY_GALLERY:
            candidates.append(FAMILY_GALLERY[resolved_family])
        else:
            return None
    else:
        candidates.extend(
            {
                "editor_table": ["editor-table-registry"],
                "editor_markdown": ["editor-markdown-block"],
                "editor_js_control": ["selector-wiring", "editor-js-control-selector"],
                "editor_advanced": ["kpi-status"],
            }.get(route, [])
        )
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        folder = GALLERY_ROOT / name
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("route") != route:
            continue
        tabs = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(folder.iterdir())
            if path.is_file() and path.name in {"meta.json", "params.js", "sources.js", "prepare.js", "controls.js", "config.js"}
        }
        if not tabs:
            continue
        spec = ROUTE_CONTRACT.spec(route)
        return {
            "schema_version": "2026-06-04.editor_tab_bundle.local.v1",
            "widget_id": widget_id,
            "name": _canonical_name(route=route, title=title, widget_id=widget_id),
            "display_title": title,
            "route": route,
            "entry_type": spec.entry_type,
            "family": resolved_family or manifest.get("family") or name,
            "requested_family": requested_family,
            "source_gallery": name,
            "source_example": manifest.get("source_example", name),
            "generation_status": "fixture_only",
            "source_contract": {
                "status": "fixture_only",
                "production_ready": False,
                "binding": "gallery_fixture",
                "required_output_columns": [],
                "issues": [
                    {
                        "code": "fixture_source_not_production_ready",
                        "message": "Gallery example rows are allowed only in the static golden fixture path.",
                    }
                ],
            },
            "blocking_issues": [],
            "tabs": tabs,
        }
    return None
