from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, read_text, write_text
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.requirements_workspace import initialize_requirements_workspace


CATALOG_DOC = "docs/datalens/implemented_charts.md"
CATALOG_REPORT = "artifacts/reports/implemented_charts_catalog.md"


def update_implemented_charts_catalog(
    project_root: str | Path,
    *,
    bundle: dict[str, Any] | None = None,
    relations: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    initialize_requirements_workspace(root)
    relations = relations or read_json(root / "artifacts" / "dashboard_object_relations.json", default={})
    brief = brief or read_json(root / "artifacts" / "dashboard_brief.json", default={})
    bundles = _collect_bundles(root, bundle)
    entries = _build_entries(root=root, bundles=bundles, relations=relations, brief=brief)
    dashboard_name = (
        (relations.get("dashboard") or {}).get("name")
        or brief.get("dashboard_name")
        or "DataLens Dashboard"
    )
    markdown = _render_catalog(entries=entries, dashboard_name=dashboard_name)

    write_text(root / CATALOG_DOC, markdown)
    _write_requirements_catalog(root, entries, relations)
    _write_report(root, entries)
    return {
        "ok": True,
        "path": CATALOG_DOC,
        "entries": len(entries),
        "chart_ids": [entry["chart_id"] for entry in entries],
    }


def _collect_bundles(root: Path, bundle: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    bundles: dict[str, dict[str, Any]] = {}
    for bundle_path in root.glob("dashboard/*/bundle.json"):
        current = read_json(bundle_path, default={})
        widget_id = str(current.get("widget_id") or bundle_path.parent.name)
        bundles[widget_id] = current
    if bundle:
        widget_id = str(bundle.get("widget_id") or "widget_001")
        bundles[widget_id] = bundle
    return bundles


def _build_entries(
    *,
    root: Path,
    bundles: dict[str, dict[str, Any]],
    relations: dict[str, Any],
    brief: dict[str, Any],
) -> list[dict[str, Any]]:
    charts = relations.get("charts") or []
    if not charts:
        charts = [
            {
                "chart_id": bundle.get("widget_id"),
                "widget_id": bundle.get("widget_id"),
                "family": bundle.get("family") or bundle.get("requested_family") or "kpi_value_sparkline",
                "route": bundle.get("route") or "editor_advanced",
                "dataset_dependencies": [],
                "field_dependencies": [],
                "calculated_field_dependencies": [],
            }
            for bundle in bundles.values()
        ]
    selectors = relations.get("selectors") or []
    datasets = {item.get("dataset_id"): item for item in relations.get("datasets") or []}
    widgets = {item.get("widget_id"): item for item in relations.get("widgets") or []}
    entries = []
    for chart in charts:
        widget_id = str(chart.get("widget_id") or chart.get("chart_id") or "")
        bundle = bundles.get(widget_id, {})
        family = _approved_family(str(chart.get("family") or bundle.get("family") or "kpi_value_sparkline"))
        fields = [str(item) for item in chart.get("field_dependencies") or []]
        dimensions, measures = _split_fields(fields, root=root)
        dataset_ids = [str(item) for item in chart.get("dataset_dependencies") or []]
        affected_selectors = _selectors_for_chart(selectors, chart_id=str(chart.get("chart_id") or widget_id), widget_id=widget_id)
        widget = widgets.get(widget_id) or {}
        tab = widget.get("tab_id") or "main"
        native_metadata = chart.get("native_metadata") or widget.get("native_metadata") or {}
        entries.append(
            {
                "chart_id": str(chart.get("chart_id") or widget_id or "chart_placeholder"),
                "widget_id": widget_id or "widget_placeholder",
                "dashboard": (relations.get("dashboard") or {}).get("name") or brief.get("dashboard_name") or "DataLens Dashboard",
                "page_tab": tab,
                "family": family,
                "implementation_path": _implementation_path(str(chart.get("route") or bundle.get("route") or "editor_advanced")),
                "route": str(chart.get("route") or bundle.get("route") or "editor_advanced"),
                "template_used": str(bundle.get("source_template") or bundle.get("source_gallery") or "generated_default_bundle"),
                "dataset_used": ", ".join(dataset_ids) or "pending",
                "source_connection_used": _source_connections(root),
                "dimensions": dimensions,
                "measures": measures,
                "calculated_fields": [str(item) for item in chart.get("calculated_field_dependencies") or []],
                "filters": [selector.get("param") for selector in affected_selectors if selector.get("param")],
                "selectors": [selector.get("selector_id") for selector in affected_selectors if selector.get("selector_id")],
                "object_relations": _relation_text(affected_selectors, dataset_ids, datasets),
                "native_title": native_metadata.get("title") or "",
                "native_hint": native_metadata.get("hint") or "",
                "native_hide_title": native_metadata.get("hideTitle"),
                "native_enable_hint": native_metadata.get("enableHint"),
                "style_theme_notes": _style_notes(root),
                "known_limitations": _limitations(bundle, fields),
                "last_updated": _timestamp(),
            }
        )
    return entries


def _approved_family(family: str) -> str:
    resolution = resolve_chart_family(family)
    return resolution.approved_alternative


def _implementation_path(route: str) -> str:
    if route in {"wizard_native", "wizard_map_native"}:
        return "Wizard native"
    if route.startswith("editor_"):
        return "Advanced Editor" if route == "editor_advanced" else f"Editor {route.removeprefix('editor_')}"
    return route


def _split_fields(fields: list[str], *, root: Path) -> tuple[list[str], list[str]]:
    metrics_text = read_text(root / "requirements" / "metrics.md", default="").lower()
    measures = []
    dimensions = []
    metric_markers = ("metric", "kpi", "measure", "value", "count", "sum", "rate", "amount", "total")
    for field in fields:
        lowered = field.lower()
        if lowered in metrics_text or any(marker in lowered for marker in metric_markers):
            measures.append(field)
        else:
            dimensions.append(field)
    if fields and not measures:
        measures = [fields[-1]]
        dimensions = fields[:-1]
    return dimensions, measures


def _selectors_for_chart(selectors: list[dict[str, Any]], *, chart_id: str, widget_id: str) -> list[dict[str, Any]]:
    matched = []
    for selector in selectors:
        for target in selector.get("targets") or []:
            if target.get("target_id") in {chart_id, widget_id}:
                matched.append(selector)
                break
    return matched


def _source_connections(root: Path) -> str:
    text = read_text(root / "requirements" / "connectors.md", default="")
    lines = [line.strip("- ") for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return ", ".join(lines[-3:]) if lines else "pending"


def _style_notes(root: Path) -> str:
    if (root / "config" / "datalens_style_guide.json").is_file():
        return "Uses config/datalens_style_guide.json light/dark tokens."
    return "Uses MCP default light/dark-safe template styling."


def _limitations(bundle: dict[str, Any], fields: list[str]) -> str:
    notes = []
    if not fields:
        notes.append("field dependencies pending")
    if not bundle.get("source_template") and not bundle.get("source_gallery"):
        notes.append("generated default bundle")
    return "; ".join(notes) or "none recorded"


def _relation_text(affected_selectors: list[dict[str, Any]], dataset_ids: list[str], datasets: dict[str, dict[str, Any]]) -> str:
    selector_text = ", ".join(str(selector.get("selector_id")) for selector in affected_selectors) or "no selector"
    dataset_text = ", ".join(dataset_ids) or "no dataset"
    field_count = sum(len((datasets.get(dataset_id) or {}).get("fields") or []) for dataset_id in dataset_ids)
    return f"{selector_text}; datasets: {dataset_text}; declared fields: {field_count}"


def _render_catalog(*, entries: list[dict[str, Any]], dashboard_name: str) -> str:
    lines = [
        "# Implemented Charts",
        "",
        f"Dashboard: `{dashboard_name}`",
        "",
    ]
    if not entries:
        lines.append("No implemented charts recorded yet.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| Chart | Page/Tab | Family | Path | Template | Dataset | Dimensions | Measures | Selectors | Updated |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for entry in entries:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{entry['chart_id']}`",
                    str(entry["page_tab"]),
                    f"`{entry['family']}`",
                    entry["implementation_path"],
                    f"`{entry['template_used']}`",
                    entry["dataset_used"],
                    _join(entry["dimensions"]),
                    _join(entry["measures"]),
                    _join(entry["selectors"]),
                    entry["last_updated"],
                ]
            )
            + " |"
        )
    lines.extend(["", "## Details", ""])
    for entry in entries:
        lines.extend(
            [
                f"### {entry['chart_id']}",
                "",
                f"- Dashboard/page/tab: `{entry['dashboard']}` / `{entry['page_tab']}`",
                f"- Chart family: `{entry['family']}`",
                f"- Implementation path: `{entry['implementation_path']}` (`{entry['route']}`)",
                f"- Template used: `{entry['template_used']}`",
                f"- Dataset used: `{entry['dataset_used']}`",
                f"- Source/connection used: {entry['source_connection_used']}",
                f"- Dimensions: {_join(entry['dimensions'])}",
                f"- Measures: {_join(entry['measures'])}",
                f"- Calculated fields: {_join(entry['calculated_fields'])}",
                f"- Filters: {_join(entry['filters'])}",
                f"- Selectors affecting it: {_join(entry['selectors'])}",
                f"- Object relations: {entry['object_relations']}",
                f"- Native title/hint: title `{entry['native_title'] or 'pending'}`, "
                f"hint `{entry['native_hint'] or 'pending'}`, hideTitle `{entry['native_hide_title']}`, "
                f"enableHint `{entry['native_enable_hint']}`",
                f"- Style/theme notes: {entry['style_theme_notes']}",
                f"- Known limitations: {entry['known_limitations']}",
                f"- Last updated: `{entry['last_updated']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Historical Conversion Notes",
            "",
            "Removed chart variants are not listed as current implementations. "
            "If a removed chart is found in a legacy dashboard, record it here "
            "as historical conversion evidence only.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_requirements_catalog(root: Path, entries: list[dict[str, Any]], relations: dict[str, Any]) -> None:
    chart_lines = ["\n## Implemented Chart Catalog\n"]
    metric_lines = ["\n## Implemented Metrics And Attributes\n"]
    relation_lines = ["\n## Implemented Object Relations\n"]
    for entry in entries:
        chart_lines.append(
            f"- `{entry['chart_id']}` on `{entry['page_tab']}`: `{entry['family']}` via `{entry['template_used']}`; "
            f"dimensions {_join(entry['dimensions'])}; measures {_join(entry['measures'])}; "
            f"selectors {_join(entry['selectors'])}; native title `{entry['native_title'] or 'pending'}`."
        )
        metric_lines.append(
            f"- `{entry['chart_id']}` measures {_join(entry['measures'])}; "
            f"dimensions/attributes {_join(entry['dimensions'])}; "
            f"calculated {_join(entry['calculated_fields'])}."
        )
        relation_lines.append(f"- `{entry['chart_id']}`: {entry['object_relations']}.")
    if relations:
        relation_lines.append("- Relation artifact: `artifacts/dashboard_object_relations.json`.")
    _replace_section(root / "requirements" / "charts.md", "## Implemented Chart Catalog", chart_lines)
    _replace_section(root / "requirements" / "metrics.md", "## Implemented Metrics And Attributes", metric_lines)
    _replace_section(root / "requirements" / "object_relations.md", "## Implemented Object Relations", relation_lines)


def _write_report(root: Path, entries: list[dict[str, Any]]) -> None:
    content = [
        "# Implemented Charts Catalog Report",
        "",
        "## Implemented",
        "",
        "- Added deterministic catalog generation from editor bundles and dashboard object relations.",
        "- Current catalog entries are resolved through the approved chart taxonomy.",
        "- Project requirements files receive chart, metric, attribute, selector, and relation summaries.",
        "",
        "## Files Changed",
        "",
        "- `src/datalens_dev_mcp/pipeline/implemented_charts_catalog.py`",
        "- `src/datalens_dev_mcp/mcp/tools/pipeline.py`",
        "- `docs/datalens/implemented_charts.md`",
        "- `requirements/charts.md` for project-specific runs",
        "- `requirements/metrics.md` for project-specific runs",
        "- `requirements/object_relations.md` for project-specific runs",
        "",
        "## Current Result",
        "",
        f"- Catalog entries generated: {len(entries)}",
        "",
        "## Tests",
        "",
        "- Pending final prompt-pack verification.",
        "",
        "## Remaining Risks",
        "",
        "- Source/connection details remain `pending` until connectors are declared in `requirements/connectors.md`.",
        "- Catalog generation is offline and does not prove live DataLens object existence without readback.",
        "",
    ]
    write_text(root / CATALOG_REPORT, "\n".join(content))


def _replace_section(path: Path, heading: str, lines: list[str]) -> None:
    existing = read_text(path, default="")
    base = existing.split(f"\n{heading}", 1)[0].rstrip()
    write_text(path, base + "\n" + "\n".join(lines).rstrip() + "\n")


def _join(values: list[Any]) -> str:
    return ", ".join(f"`{item}`" for item in values if item) or "pending"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
