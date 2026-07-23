#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.knowledge.corpus import resolve_corpus_root as resolve_shared_corpus_root  # noqa: E402

POLICY_PATH = ROOT / "config" / "datalens_docs_feature_policy.json"
PACKAGE_POLICY_PATH = ROOT / "src" / "datalens_dev_mcp" / "assets" / "config" / "datalens_docs_feature_policy.json"
DOC_PATH = ROOT / "docs" / "datalens" / "current_docs_reconciliation.md"
SCHEMA_VERSION = "2026-06-30.current_docs_feature_policy.v1"
DELTA_REPORT_NAME = "update_report_delta_2026-07-13.md"
EXPECTED_FINAL_COUNTS = {"pages": 651, "chunks": 4999, "assets": 886, "manifest": 1545}
EXPECTED_DELTA_COUNTS = {"changed": 12, "new": 3}
EXPECTED_OPENAPI_SHA256 = "fede0d82463b8e9808fedd6789eef80a854c01bdfa82b3020b7ac8a21d2a1ed8"

VALID_STATUSES = {
    "supported",
    "read_only",
    "import_only",
    "guarded_plan_only",
    "unsupported_explicit",
    "not_applicable",
}

REQUIRED_CLUSTER_IDS = [
    "api_versioning",
    "api_changelog_v2",
    "release_notes_2605",
    "dashboard_margins",
    "dashboard_widget_background",
    "dashboard_rounding",
    "dashboard_background",
    "dashboard_hide_tabs",
    "dashboard_tabs",
    "dashboard_title",
    "dashboard_contents",
    "dashboard_ai_widget",
    "dashboard_ai_reference_tab",
    "workbook_access_basic",
    "workbook_access_advanced",
    "embedded_objects",
    "roles",
    "editor_methods",
    "editor_tabs",
    "editor_sources",
    "editor_code_helper",
    "editor_widgets_advanced",
    "editor_widgets_gravity_ui",
    "editor_cross_filtration",
    "editor_notifications",
    "visual_table",
    "visual_indicator",
    "visual_bar",
    "visual_line",
    "visual_area",
    "visual_normalized_area",
    "visual_pie_ring",
    "visual_heatmap",
    "visual_map",
    "visual_combined",
    "visual_choropleth",
    "dataset_cache_invalidation",
    "dataset_data_model",
    "dataset_versioning_drafts",
    "dashboard_trends_preview",
    "audit_entry_scopes",
    "datalens_limits",
    "chart_inspector",
    "troubleshooting_errors",
]


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_count(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def resolve_corpus_root(raw: str = "") -> Path:
    return resolve_shared_corpus_root(raw or None, required_files=("pages.jsonl", "reports/update_report.md"))


def load_report(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"## Summary\s+```json\s+(\{.*?\})\s+```", text, flags=re.S)
    if not match:
        raise ValueError(f"{path.name} summary JSON block was not found")
    return json.loads(match.group(1)), text


def load_update_reports(corpus_root: Path) -> dict[str, Any]:
    snapshot_path = corpus_root / "reports" / "update_report.md"
    snapshot_summary, snapshot_text = load_report(snapshot_path)
    delta_path = corpus_root / "reports" / DELTA_REPORT_NAME
    if not delta_path.is_file():
        raise FileNotFoundError(f"required historical delta report is missing: reports/{DELTA_REPORT_NAME}")
    delta_summary, delta_text = load_report(delta_path)
    return {
        "snapshot_path": snapshot_path,
        "snapshot_summary": snapshot_summary,
        "snapshot_text": snapshot_text,
        "delta_path": delta_path,
        "delta_summary": delta_summary,
        "delta_text": delta_text,
    }


def extract_fenced_urls(text: str, heading: str) -> list[str]:
    pattern = rf"{re.escape(heading)}:\s+```text\s+(.*?)\s+```"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        return []
    return sorted(line.strip() for line in match.group(1).splitlines() if line.strip().startswith("http"))


def _cluster(
    cluster_id: str,
    title: str,
    classification: str,
    source_urls: list[str],
    mcp_surface: str,
    server_decision: str,
    runtime_contract: str,
) -> dict[str, Any]:
    return {
        "id": cluster_id,
        "title": title,
        "classification": classification,
        "source_urls": source_urls,
        "mcp_surface": mcp_surface,
        "server_decision": server_decision,
        "runtime_contract": runtime_contract,
    }


def build_clusters() -> list[dict[str, Any]]:
    base = "https://docs.yandex.cloud/ru/ru/datalens"
    return [
        _cluster(
            "api_versioning",
            "DataLens API version selection",
            "supported",
            [f"{base}/operations/api-versioning.md"],
            "DataLens API client version policy",
            "Keep auto pinned to the compiled OpenAPI version; permit explicit latest only for curated read-only calls.",
            "Guarded writes reject explicit latest before HTTP because future schemas are not compiled or reviewed.",
        ),
        _cluster(
            "api_changelog_v2",
            "DataLens API v2 changelog",
            "supported",
            [f"{base}/release-notes/api-changelog.md"],
            "request compiler and read-only RPC validation",
            "Validate getEntries with v2 arrays, pageToken, and ignoreSharedEntries semantics.",
            "Legacy string ids/createdBy and removed page are rejected locally; getEntries never auto-falls back to v1.",
        ),
        _cluster(
            "release_notes_2605",
            "May 2026 DataLens release notes",
            "read_only",
            [f"{base}/release-notes/2605.md"],
            "dl_reference and feature policy",
            "Index the release note as capability context without inferring new API routes.",
            "StarRocks, mailings, shared objects, roles, cache invalidation, and hidden tabs do not enable guessed mutations.",
        ),
        _cluster(
            "dashboard_margins",
            "Dashboard margins",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/add-margins.md"],
            "dashboard payload preflight and safe apply",
            "Preserve current dashboard margin fields and allow guarded save plans; do not strip unknown style fields.",
            "Unknown/current dashboard style fields are preserved through fresh-read/update payloads.",
        ),
        _cluster(
            "dashboard_widget_background",
            "Widget background",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/add-widget-background.md"],
            "dashboard payload preflight and relation/layout validation",
            "Preserve widget background settings; generate only when an explicit dashboard layout plan owns the widget.",
            "Validator checks duplicates and unsafe names without dropping current background fields.",
        ),
        _cluster(
            "dashboard_rounding",
            "Widget rounding",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/add-rounding.md"],
            "dashboard payload preflight",
            "Preserve rounding fields and keep decorative chart-body rounding out of Editor payloads.",
            "Dashboard item metadata owns rounding; chart body templates do not duplicate dashboard chrome.",
        ),
        _cluster(
            "dashboard_background",
            "Dashboard background",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/add-dashboard-background.md"],
            "dashboard payload preflight",
            "Preserve dashboard background settings through safe apply.",
            "Fresh dashboard reads are the source of truth for unknown layout/style fields.",
        ),
        _cluster(
            "dashboard_hide_tabs",
            "Hide dashboard tabs",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/dashboard-hide-tabs.md"],
            "dashboard tab update planner",
            "Preserve hide-tabs settings and do not infer tab visibility from local templates.",
            "Tab update plans must keep unrelated tabs and dashboard metadata unchanged.",
        ),
        _cluster(
            "dashboard_tabs",
            "Dashboard tabs",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/dashboard-tabs.md"],
            "dl_plan_dashboard_tab_update",
            "Append/replace tabs only through fresh-read guarded plans.",
            "Nested tab ids must stay non-empty and unique.",
        ),
        _cluster(
            "dashboard_title",
            "Dashboard title widgets and title metadata",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/add-title-dashboard.md", f"{base}/operations/dashboard/add-title.md"],
            "dashboard native title/hint policy",
            "Dashboard metadata renders titles and hints except narrative Markdown widgets.",
            "Generated chart bodies must not duplicate native dashboard titles or hints.",
        ),
        _cluster(
            "dashboard_contents",
            "Dashboard contents widget",
            "guarded_plan_only",
            [f"{base}/operations/dashboard/add-contents.md"],
            "dashboard layout validation",
            "Treat contents widgets as dashboard structure; preserve through readback and safe apply.",
            "Contents widgets are not synthesized from chart body templates.",
        ),
        _cluster(
            "dashboard_ai_widget",
            "Dashboard AI widget",
            "unsupported_explicit",
            [f"{base}/operations/dashboard/add-ai.md"],
            "reference and preservation only",
            "Do not create AI widgets from MCP; preserve unknown AI widget payloads on fresh-read update.",
            "Unsupported route returns explicit policy instead of a guessed payload.",
        ),
        _cluster(
            "dashboard_ai_reference_tab",
            "Dashboard AI/reference tab",
            "unsupported_explicit",
            [f"{base}/operations/dashboard/dashboard-ai-reference-tab.md"],
            "reference and preservation only",
            "Do not create AI/reference tabs from MCP; preserve existing fields when updating other tabs.",
            "Unsupported route remains explicit and tested.",
        ),
        _cluster(
            "workbook_access_basic",
            "Workbook access basic",
            "unsupported_explicit",
            [f"{base}/security/workbooks-access-basic.md", f"{base}/security/workbooks-access.md"],
            "reference only",
            "Use DataLens or Yandex Cloud access management for workbook permission changes.",
            "Permission mutation is outside the MCP route contract.",
        ),
        _cluster(
            "workbook_access_advanced",
            "Workbook access advanced",
            "unsupported_explicit",
            [f"{base}/security/workbooks-access-advanced.md"],
            "reference only",
            "Advanced access changes are outside this MCP server.",
            "Permission mutation is outside the MCP route contract.",
        ),
        _cluster(
            "embedded_objects",
            "Embedded objects",
            "read_only",
            [f"{base}/security/embedded-objects.md"],
            "dl_reference and object reads",
            "Embedding docs are retained as reference; create/update embed routes are unsupported unless separately implemented.",
            "No embedding secret or embed write route is exposed by default.",
        ),
        _cluster(
            "roles",
            "Roles and security",
            "read_only",
            [f"{base}/security/roles.md"],
            "dl_reference",
            "Roles are used for operator guidance and sanitized diagnostics.",
            "Role docs do not enable permission mutation.",
        ),
        _cluster(
            "editor_methods",
            "Editor methods",
            "supported",
            [f"{base}/charts/editor/methods.md"],
            "Advanced Editor validator and bundle generator",
            "Supported methods feed the Editor runtime allowlist.",
            "Generated payloads are validated before safe apply.",
        ),
        _cluster(
            "editor_tabs",
            "Editor tabs",
            "supported",
            [f"{base}/charts/editor/tabs.md"],
            "Advanced Editor bundle generator",
            "Generated payloads use current tab contracts for sources, params, prepare, and config.",
            "Tab names and required sections are validated.",
        ),
        _cluster(
            "editor_sources",
            "Editor sources",
            "supported",
            [f"{base}/charts/editor/sources.md"],
            "Editor source validators and SQL diagnostics",
            "Generated source SQL is statically linted and tied to source artifacts.",
            "Source errors are classified without fabricating runtime SQL execution.",
        ),
        _cluster(
            "editor_code_helper",
            "Editor code helper",
            "read_only",
            [f"{base}/charts/editor/code-helper.md"],
            "dl_reference",
            "AI helper docs are reference-only for authoring guidance.",
            "MCP does not depend on DataLens UI AI behavior.",
        ),
        _cluster(
            "editor_widgets_advanced",
            "Advanced Editor widgets",
            "supported",
            [f"{base}/charts/editor/widgets/advanced.md"],
            "editor_advanced route",
            "Advanced widgets use the supported custom chart route.",
            "Bundle output must pass runtime contract validation before save/publish.",
        ),
        _cluster(
            "editor_widgets_gravity_ui",
            "Gravity UI widgets",
            "unsupported_explicit",
            [f"{base}/charts/editor/widgets/gravity-ui.md"],
            "dl_reference",
            "Gravity UI Charts remain documented-reference only under local route policy.",
            "No Gravity UI chart creation route is added.",
        ),
        _cluster(
            "editor_cross_filtration",
            "Editor cross-filtration",
            "guarded_plan_only",
            [f"{base}/charts/editor/cross-filtration.md"],
            "selector and relation planning",
            "Cross-filtration informs selector wiring and relation validation.",
            "Relations are validated before payload and safe apply plans.",
        ),
        _cluster(
            "editor_notifications",
            "Editor notifications",
            "supported",
            [f"{base}/charts/editor/notifications.md"],
            "Advanced Editor validator",
            "Notification APIs are allowed only where current Editor runtime allows them.",
            "Unsupported notification patterns fail validation before safe apply.",
        ),
        _cluster(
            "visual_table",
            "Table visualization",
            "supported",
            [f"{base}/visualization-ref/table-chart.md", f"{base}/visualization-ref/pivot-table-chart.md"],
            "wizard_native flatTable/pivotTable and specialized table validators",
            "Ordinary flat and pivot tables use Wizard; grouped/pinned capability gaps use the specialized Editor table route.",
            "Custom HTML tables are not a fallback when native Wizard or registered table semantics are sufficient.",
        ),
        _cluster(
            "visual_indicator",
            "Indicator visualization",
            "supported",
            [f"{base}/visualization-ref/indicator-chart.md"],
            "VisualDecisionEngine and wizard_native metric",
            "Indicator/KPI requires explicit metric semantics and comparator policy.",
            "No implicit previous-period comparator is generated.",
        ),
        _cluster(
            "visual_bar",
            "Bar visualization",
            "supported",
            [f"{base}/visualization-ref/bar-chart.md"],
            "VisualDecisionEngine and wizard_native bar/column routes",
            "Bar charts are selected by task, data shape, cardinality, and metric semantics.",
            "Negative requirements can reject bars or specific colors.",
        ),
        _cluster(
            "visual_line",
            "Line visualization",
            "supported",
            [f"{base}/visualization-ref/line-chart.md"],
            "VisualDecisionEngine and wizard_native line route",
            "Line charts require time/ordered data evidence.",
            "Sort and axis contracts are recorded in RendererVisualSpec.",
        ),
        _cluster(
            "visual_area",
            "Area visualization",
            "supported",
            [f"{base}/visualization-ref/area-chart.md"],
            "VisualDecisionEngine and wizard_native area route",
            "Area charts require additive semantics and appropriate series count.",
            "Renderer specs record stacking/normalization decisions.",
        ),
        _cluster(
            "visual_normalized_area",
            "Normalized area visualization",
            "supported",
            [f"{base}/visualization-ref/normalized-area-chart.md"],
            "VisualDecisionEngine and wizard_native area100p route",
            "Normalized area is selected only for part-to-whole over time semantics.",
            "Additivity and denominator evidence are required.",
        ),
        _cluster(
            "visual_pie_ring",
            "Pie and ring visualization",
            "supported",
            [f"{base}/visualization-ref/pie-chart.md", f"{base}/visualization-ref/ring-chart.md"],
            "VisualDecisionEngine and wizard_native pie/donut routes",
            "Pie/ring remain available only for small-cardinality part-to-whole tasks.",
            "Negative requirements can force rejection and alternate families.",
        ),
        _cluster(
            "visual_heatmap",
            "Heat map visualization",
            "supported",
            [f"{base}/visualization-ref/heat-map-chart.md"],
            "VisualDecisionEngine and editor_advanced route",
            "Heat maps require two-dimensional categorical/date grid evidence.",
            "Color strategy must be explicit and accessible.",
        ),
        _cluster(
            "visual_map",
            "Map visualization",
            "guarded_plan_only",
            [f"{base}/visualization-ref/map-chart.md"],
            "wizard_native route with geolayer visualization",
            "Maps use the Wizard-first geolayer contract and require validated geo evidence.",
            "Route selection is deterministic before transport and never falls back to JavaScript after a failed write.",
        ),
        _cluster(
            "visual_combined",
            "Combined visualization",
            "supported",
            [f"{base}/visualization-ref/combined-chart.md"],
            "VisualDecisionEngine and wizard_native combined-chart route",
            "Combined charts require explicit axis/metric compatibility.",
            "Renderer spec records multi-axis and series decisions.",
        ),
        _cluster(
            "visual_choropleth",
            "Choropleth map visualization",
            "guarded_plan_only",
            [f"{base}/visualization-ref/choropleth-map-chart.md"],
            "wizard_native route with geolayer visualization",
            "Choropleth uses the validated Wizard geolayer planning contract.",
            "Geo evidence and map route validation are required before safe apply.",
        ),
        _cluster(
            "dataset_cache_invalidation",
            "Dataset cache invalidation",
            "read_only",
            [f"{base}/dataset/cache-invalidation.md"],
            "dl_reference and dataset diagnostics",
            "Cache invalidation docs are reference-only unless a validated API method is present.",
            "No cache mutation route is guessed.",
        ),
        _cluster(
            "dataset_data_model",
            "Dataset data model",
            "supported",
            [f"{base}/dataset/data-model.md"],
            "dataset planners and guarded update validators",
            "Dataset field/model changes are represented inside dataset payloads.",
            "Standalone dataset-field operations remain unsupported when absent from OpenAPI.",
        ),
        _cluster(
            "dataset_versioning_drafts",
            "Dataset drafts and current versions",
            "unsupported_explicit",
            [f"{base}/dataset/versioning.md"],
            "dl_reference and dataset request validation",
            "Explain draft/current-version behavior but do not invent draft or promotion request fields.",
            "Ordinary updateDataset is not treated as draft promotion; requests need exact API evidence before mutation.",
        ),
        _cluster(
            "dashboard_trends_preview",
            "Dashboard trends and smoothing preview",
            "read_only",
            [f"{base}/dashboard/trends-and-smoothing.md"],
            "dl_reference and browser QA guidance",
            "Treat preview trends as temporary dashboard UI state, not as a persisted chart/dashboard payload.",
            "Preview is dashboard-only, is not saved, and is unavailable in embedded dashboards.",
        ),
        _cluster(
            "audit_entry_scopes",
            "Audit and inventory entry scopes",
            "read_only",
            [f"{base}/at-ref.md", f"{base}/openapi-ref/getAuditEntriesUpdates.md"],
            "read-only inventory and audit response projection",
            "Preserve compute as inventory-only and artifact as an audit-only scope value.",
            "Neither scope enables a guessed direct reader or lifecycle route; artifact is not a generic MCP object type.",
        ),
        _cluster(
            "datalens_limits",
            "DataLens limits",
            "read_only",
            [f"{base}/concepts/limits.md"],
            "dl_reference and validators",
            "Limits inform budgets and warnings.",
            "Limit docs do not add new write routes.",
        ),
        _cluster(
            "chart_inspector",
            "Chart inspector",
            "import_only",
            [f"{base}/concepts/chart/inspector.md"],
            "dl_diagnose performance evidence",
            "Inspector/HAR evidence may be imported; timings are not fabricated.",
            "Missing inspector evidence is reported as timing_unavailable.",
        ),
        _cluster(
            "troubleshooting_errors",
            "Troubleshooting errors",
            "supported",
            [f"{base}/troubleshooting/errors/all.md"],
            "dl_classify_source_error and SQL diagnostics",
            "Known errors feed structured classifier and remediation output.",
            "Request-stage null-query failures are not misclassified as SQL errors.",
        ),
    ]


def build_policy(corpus_root: Path) -> dict[str, Any]:
    reports = load_update_reports(corpus_root)
    snapshot = reports["snapshot_summary"]
    delta = reports["delta_summary"]
    inventory = read_json(corpus_root / "api_inventory.json")
    docs = snapshot["docs"]
    assets = snapshot["assets"]
    validation = snapshot["validation"]
    delta_docs = delta["docs"]
    delta_assets = delta["assets"]
    new_urls = extract_fenced_urls(reports["delta_text"], "New pages")
    clusters = build_clusters()
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "corpus_root_hint": "<DATALENS_DOCS_CORPUS_ROOT>",
            "update_report": "reports/update_report.md",
            "update_report_generated_at": snapshot["generated_at"],
            "applied_delta_report": reports["delta_path"].relative_to(corpus_root).as_posix(),
            "applied_delta_generated_at": delta["generated_at"],
            "openapi_sha256": str(inventory.get("openapi_sha256") or ""),
            "mode": snapshot["mode"],
        },
        "expected_counts": {
            "docs_current_pages": read_jsonl_count(corpus_root / "pages.jsonl"),
            "docs_current_chunks": read_jsonl_count(corpus_root / "chunks.jsonl"),
            "docs_checked_pages": docs["checked_count"],
            "docs_changed_pages": delta_docs["changed_count"],
            "docs_new_pages": delta_docs["new_count"],
            "docs_removed_candidates": delta_docs["removed_candidate_count"],
            "docs_failed_pages": docs["failed_count"],
            "assets_current_records": read_jsonl_count(corpus_root / "assets.jsonl"),
            "assets_new_references": delta_assets["new_reference_count"],
            "assets_removed_references": delta_assets["removed_reference_count"],
            "manifest_current_records": read_jsonl_count(corpus_root / "manifest.jsonl"),
            "openapi_operations": inventory["stats"]["operations"],
            "openapi_paths": inventory["stats"]["paths"],
            "validation_required_checks_ok": validation["required_checks_ok"],
            "validation_failure_count": validation["failure_count"],
        },
        "status_enum": sorted(VALID_STATUSES),
        "covered_new_page_urls": new_urls,
        "clusters": clusters,
    }


def render_markdown(policy: dict[str, Any]) -> str:
    counts = policy["expected_counts"]
    lines = [
        "# Current DataLens Docs Reconciliation",
        "",
        (
            f"Source update report: `{policy['source']['update_report']}` generated at "
            f"`{policy['source']['update_report_generated_at']}`."
        ),
        (
            f"Applied delta report: `{policy['source']['applied_delta_report']}` generated at "
            f"`{policy['source']['applied_delta_generated_at']}`."
        ),
        "",
        "This file is a distilled policy matrix. It does not copy raw documentation pages into the repository.",
        "",
        "## Corpus Counts",
        "",
        f"- Current pages: `{counts['docs_current_pages']}`.",
        f"- Current chunks: `{counts['docs_current_chunks']}`.",
        f"- Changed pages: `{counts['docs_changed_pages']}`.",
        f"- New pages: `{counts['docs_new_pages']}`.",
        f"- Removed candidates: `{counts['docs_removed_candidates']}`.",
        f"- Failed page checks: `{counts['docs_failed_pages']}`.",
        f"- OpenAPI operations/paths: `{counts['openapi_operations']}` / `{counts['openapi_paths']}`.",
        f"- Required validation checks OK: `{counts['validation_required_checks_ok']}`.",
        "",
        "## New Pages Covered",
        "",
    ]
    lines.extend(f"- {url}" for url in policy["covered_new_page_urls"])
    lines.extend(
        [
            "",
            "## Feature Policy Matrix",
            "",
            "| Cluster ID | Classification | MCP surface | Server decision |",
            "| --- | --- | --- | --- |",
        ]
    )
    for cluster in policy["clusters"]:
        lines.append(
            f"| `{cluster['id']}` | `{cluster['classification']}` | {cluster['mcp_surface']} | {cluster['server_decision']} |"
        )
    lines.extend(
        [
            "",
            "## Unsupported Or Reference-Only Decisions",
            "",
        ]
    )
    for cluster in policy["clusters"]:
        if cluster["classification"] in {"unsupported_explicit", "read_only", "import_only"}:
            lines.append(f"- `{cluster['id']}`: {cluster['runtime_contract']}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(corpus_root: Path) -> None:
    policy = build_policy(corpus_root)
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    policy_text = json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    POLICY_PATH.write_text(policy_text, encoding="utf-8")
    PACKAGE_POLICY_PATH.write_text(policy_text, encoding="utf-8")
    DOC_PATH.write_text(render_markdown(policy), encoding="utf-8")


def validate(corpus_root: Path, *, strict: bool = False) -> dict[str, Any]:
    issues: list[str] = []
    if not POLICY_PATH.is_file():
        issues.append(f"missing {POLICY_PATH.relative_to(ROOT)}")
        policy: dict[str, Any] = {}
    else:
        policy = read_json(POLICY_PATH)
    if not PACKAGE_POLICY_PATH.is_file():
        issues.append(f"missing {PACKAGE_POLICY_PATH.relative_to(ROOT)}")
    elif policy and read_json(PACKAGE_POLICY_PATH) != policy:
        issues.append(f"changed {PACKAGE_POLICY_PATH.relative_to(ROOT)}")
    if not DOC_PATH.is_file():
        issues.append(f"missing {DOC_PATH.relative_to(ROOT)}")
        doc_text = ""
    else:
        doc_text = DOC_PATH.read_text(encoding="utf-8")

    reports = load_update_reports(corpus_root)
    snapshot = reports["snapshot_summary"]
    delta = reports["delta_summary"]
    docs = snapshot["docs"]
    assets = snapshot["assets"]
    delta_docs = delta["docs"]
    delta_assets = delta["assets"]
    validation_summary = snapshot["validation"]
    page_count = read_jsonl_count(corpus_root / "pages.jsonl")
    chunk_count = read_jsonl_count(corpus_root / "chunks.jsonl")
    asset_count = read_jsonl_count(corpus_root / "assets.jsonl")
    manifest_count = read_jsonl_count(corpus_root / "manifest.jsonl")
    inventory = read_json(corpus_root / "api_inventory.json")

    if policy.get("schema_version") != SCHEMA_VERSION:
        issues.append("policy schema_version mismatch")
    counts = policy.get("expected_counts") or {}
    expected_pairs = {
        "docs_current_pages": docs["current_count"],
        "docs_current_chunks": chunk_count,
        "docs_checked_pages": docs["checked_count"],
        "docs_changed_pages": delta_docs["changed_count"],
        "docs_new_pages": delta_docs["new_count"],
        "docs_removed_candidates": delta_docs["removed_candidate_count"],
        "docs_failed_pages": docs["failed_count"],
        "assets_current_records": assets["current_count"],
        "assets_new_references": delta_assets["new_reference_count"],
        "assets_removed_references": delta_assets["removed_reference_count"],
        "manifest_current_records": manifest_count,
        "openapi_operations": inventory["stats"]["operations"],
        "openapi_paths": inventory["stats"]["paths"],
        "validation_required_checks_ok": validation_summary["required_checks_ok"],
        "validation_failure_count": validation_summary["failure_count"],
    }
    for key, expected in expected_pairs.items():
        if counts.get(key) != expected:
            issues.append(f"count mismatch {key}: policy={counts.get(key)!r} expected={expected!r}")
    if page_count != docs["current_count"]:
        issues.append(f"pages.jsonl count mismatch: {page_count} != {docs['current_count']}")
    actual_final_counts = {
        "pages": page_count,
        "chunks": chunk_count,
        "assets": asset_count,
        "manifest": manifest_count,
    }
    for key, expected in EXPECTED_FINAL_COUNTS.items():
        if actual_final_counts[key] != expected:
            issues.append(f"final snapshot {key} mismatch: {actual_final_counts[key]} != {expected}")
    if asset_count != assets["current_count"]:
        issues.append(f"assets.jsonl count mismatch: {asset_count} != {assets['current_count']}")
    if snapshot["api"].get("new_operations") != 91 or inventory["stats"]["operations"] != 91:
        issues.append("OpenAPI operation count must be 91 for this update report")
    if inventory["stats"]["paths"] != 91:
        issues.append("OpenAPI path count must be 91 for this update report")
    if str(inventory.get("openapi_sha256") or "") != EXPECTED_OPENAPI_SHA256:
        issues.append("OpenAPI SHA-256 does not match the current locked snapshot")
    if not validation_summary.get("required_checks_ok"):
        issues.append("update report required checks are not OK")

    if policy.get("source", {}).get("applied_delta_report") != reports["delta_path"].relative_to(corpus_root).as_posix():
        issues.append("applied_delta_report mismatch")
    if policy.get("source", {}).get("openapi_sha256") != EXPECTED_OPENAPI_SHA256:
        issues.append("policy source OpenAPI SHA-256 mismatch")
    if delta_docs.get("changed_count") != EXPECTED_DELTA_COUNTS["changed"]:
        issues.append("historical delta changed_count must remain 12")
    if delta_docs.get("new_count") != EXPECTED_DELTA_COUNTS["new"]:
        issues.append("historical delta new_count must remain 3")

    expected_new_urls = extract_fenced_urls(reports["delta_text"], "New pages")
    covered_new_urls = sorted(policy.get("covered_new_page_urls") or [])
    if covered_new_urls != expected_new_urls:
        issues.append("covered_new_page_urls does not match update_report.md New pages block")

    clusters = policy.get("clusters") or []
    cluster_by_id = {item.get("id"): item for item in clusters if isinstance(item, dict)}
    missing_clusters = [cluster_id for cluster_id in REQUIRED_CLUSTER_IDS if cluster_id not in cluster_by_id]
    if missing_clusters:
        issues.append("missing required clusters: " + ", ".join(missing_clusters))
    extra_statuses = sorted(
        {str(item.get("classification")) for item in clusters if item.get("classification") not in VALID_STATUSES}
    )
    if extra_statuses:
        issues.append("invalid classifications: " + ", ".join(extra_statuses))
    for cluster_id, item in sorted(cluster_by_id.items()):
        if not item.get("source_urls"):
            issues.append(f"{cluster_id}: source_urls is empty")
        if f"`{cluster_id}`" not in doc_text:
            issues.append(f"{cluster_id}: missing from reconciliation doc")

    gravity = cluster_by_id.get("editor_widgets_gravity_ui") or {}
    if gravity.get("classification") != "unsupported_explicit":
        issues.append("Gravity UI widgets must remain unsupported_explicit under route policy")
    ai = cluster_by_id.get("dashboard_ai_reference_tab") or {}
    if ai.get("classification") != "unsupported_explicit":
        issues.append("AI/reference dashboard tab must be explicit unsupported/preserve-only")
    inspector = cluster_by_id.get("chart_inspector") or {}
    if inspector.get("classification") != "import_only":
        issues.append("Chart inspector must be import_only; timings cannot be fabricated")

    return {
        "ok": not issues,
        "strict": strict,
        "issues": issues,
        "checked": {
            "policy": str(POLICY_PATH.relative_to(ROOT)),
            "doc": str(DOC_PATH.relative_to(ROOT)),
            "cluster_count": len(clusters),
            "new_pages": len(expected_new_urls),
            "pages": page_count,
            "chunks": chunk_count,
            "assets": asset_count,
            "openapi_operations": inventory["stats"]["operations"],
            "openapi_paths": inventory["stats"]["paths"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate current DataLens docs reconciliation policy.")
    parser.add_argument("--corpus-root", default="", help="Path to compact datalens-docs-corpus output.")
    parser.add_argument("--write", action="store_true", help="Regenerate policy and markdown reconciliation artifacts.")
    parser.add_argument("--strict", action="store_true", help="Fail on any mismatch.")
    args = parser.parse_args(argv)
    try:
        corpus_root = resolve_corpus_root(args.corpus_root)
        if args.write:
            write_outputs(corpus_root)
        report = validate(corpus_root, strict=args.strict)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
