from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalens_dev_mcp.serialization import sanitize_response, serialized_metadata, stable_json_text
from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text


SCHEMA_VERSION = "2026-06-25.sql_performance.v1"
ARTIFACT_DIR = "artifacts/sql_performance"
AGGREGATE_FUNCTIONS = {
    "avg",
    "avgif",
    "count",
    "countif",
    "max",
    "min",
    "sum",
    "sumif",
    "uniq",
    "uniqexact",
    "uniqexactif",
    "countdistinct",
}
WINDOW_HINTS = {"over", "row_number", "rank", "dense_rank", "lag", "lead"}
NON_ADDITIVE_AGGS = {"avg", "countdistinct", "uniq", "uniqexact", "uniqexactif", "median", "quantile"}
SQL_KEYWORDS = {
    "and",
    "array",
    "as",
    "between",
    "by",
    "case",
    "cast",
    "desc",
    "else",
    "end",
    "from",
    "group",
    "having",
    "if",
    "in",
    "is",
    "join",
    "left",
    "limit",
    "not",
    "null",
    "on",
    "or",
    "order",
    "over",
    "right",
    "select",
    "then",
    "to",
    "union",
    "when",
    "where",
    "with",
}


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    kind: str

    @property
    def lower(self) -> str:
        return self.value.lower()


def analyze_sql(
    sql: str,
    *,
    source_name: str = "<inline>",
    schema_contract: dict[str, Any] | None = None,
    critical_ctes: list[str] | None = None,
) -> dict[str, Any]:
    """Parse enough ClickHouse/DataLens SQL structure to build stable diagnostics.

    This is intentionally not a regex-only lint pass: comments/strings are tokenized,
    balanced spans are tracked, SELECT/CTE/JOIN scopes are parsed, and findings carry
    offsets back to the original SQL.
    """
    tokens, lexical_issues = tokenize_sql(sql)
    if not tokens:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "source_name": source_name,
            "source_hash": _sha256(sql),
            "parser": "tokenized_clickhouse_subset",
            "parse_status": "parse_partial",
            "partial_spans": [],
            "diagnostics": [
                _finding(
                    "empty_sql",
                    "error",
                    "SQL text is empty or only comments.",
                    offset=0,
                    sql=sql,
                    source=source_name,
                    remediation="Provide the dataset or chart SQL text before validation.",
                )
            ],
        }

    parsed = _parse_query(tokens, sql, source_name=source_name)
    diagnostics = [*_lexical_findings(lexical_issues, sql, source_name), *parsed["diagnostics"]]
    diagnostics.extend(_stale_field_findings(parsed, schema_contract or {}, sql, source_name))
    diagnostics.extend(_broad_scan_findings(parsed, sql, source_name))
    diagnostics.extend(_select_star_findings(parsed, set(critical_ctes or []), sql, source_name))
    parse_status = "ok" if not lexical_issues and not parsed["partial_spans"] else "parse_partial"
    return {
        "ok": not any(item["severity"] == "error" for item in diagnostics),
        "schema_version": SCHEMA_VERSION,
        "source_name": source_name,
        "source_hash": _sha256(sql),
        "parser": "tokenized_clickhouse_subset",
        "parse_status": parse_status,
        "partial_spans": parsed["partial_spans"],
        "ctes": parsed["ctes"],
        "cte_dependency_dag": parsed["cte_dependency_dag"],
        "projections": parsed["projections"],
        "aliases": parsed["aliases"],
        "source_lineage": parsed["source_lineage"],
        "join_hints": parsed["join_hints"],
        "filter_pushdown": parsed["filter_pushdown"],
        "parameters": parsed["parameters"],
        "final_grain_candidates": parsed["final_grain_candidates"],
        "diagnostics": diagnostics,
        "metrics": {
            "cte_count": len(parsed["ctes"]),
            "join_count": len(parsed["join_hints"]),
            "projection_count": len(parsed["projections"]),
            "aggregate_count": sum(1 for item in parsed["function_calls"] if item["function"] in AGGREGATE_FUNCTIONS),
            "window_count": sum(1 for item in parsed["function_calls"] if item["function"] in WINDOW_HINTS),
        },
    }


def analyze_aggregation_grain(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = _normalize_dataset(payload.get("dataset") or payload)
    charts = _normalize_charts(payload.get("charts") or payload.get("affected_chart_payloads") or [])
    fields_by_guid = {field["guid"]: field for field in dataset["fields"] if field.get("guid")}
    fields_by_name = {field["name"].lower(): field for field in dataset["fields"] if field.get("name")}
    matrix: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    for chart in charts or [{"chart_id": "", "fields": []}]:
        chart_fields = chart.get("fields") or _chart_fields_from_payload(chart)
        if not chart_fields and not chart.get("chart_id"):
            continue
        for slot in chart_fields:
            field = _resolve_dataset_field(slot, fields_by_guid, fields_by_name)
            assessment = _assess_field_grain(dataset, chart, slot, field)
            matrix.append(assessment)
            blockers.extend(assessment["blockers"])

    dataset_level = [_assess_dataset_field(field, dataset) for field in dataset["fields"]]
    for item in dataset_level:
        blockers.extend(item["blockers"])
    blockers.extend(_fanout_join_blockers(dataset, charts))

    return {
        "ok": not blockers,
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset["dataset_id"],
        "physical_source_grain": dataset["physical_grain"],
        "dataset_output_grain": dataset["output_grain"],
        "dataset_field_assessments": dataset_level,
        "chart_field_matrix": matrix,
        "blockers": blockers,
        "remediation_options": _grain_remediation_options(blockers),
        "metric_parity_required": True,
        "automatic_mutation": False,
    }


def analyze_semantic_graph(payload: dict[str, Any]) -> dict[str, Any]:
    datasets = [_normalize_dataset(item) for item in payload.get("datasets") or [payload.get("dataset") or payload]]
    charts = _normalize_charts(payload.get("charts") or [])
    selectors = payload.get("selectors") if isinstance(payload.get("selectors"), list) else []
    active_ids = set(str(item) for item in payload.get("active_chart_ids") or [])
    new_contract = _contract_columns(payload.get("new_contract") or payload.get("schema_contract") or {})

    fields_by_guid: dict[str, dict[str, Any]] = {}
    fields_by_name: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        for field in dataset["fields"]:
            enriched = {**field, "dataset_id": dataset["dataset_id"]}
            if field.get("guid"):
                fields_by_guid[field["guid"]] = enriched
            if field.get("name"):
                fields_by_name[field["name"].lower()] = enriched

    edges: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    for chart in charts:
        chart_id = str(chart.get("chart_id") or chart.get("entryId") or chart.get("id") or "")
        active = not active_ids or chart_id in active_ids or bool(chart.get("active", True))
        for slot in chart.get("fields") or _chart_fields_from_payload(chart):
            guid = str(slot.get("field_guid") or slot.get("guid") or "")
            name = str(slot.get("field_name") or slot.get("name") or "")
            field = fields_by_guid.get(guid) if guid else fields_by_name.get(name.lower())
            edges.append({"from": f"chart:{chart_id}:{slot.get('slot') or 'field'}", "to": f"field:{guid or name}"})
            if active and not field:
                findings.append(
                    _graph_finding(
                        "unresolved_chart_field_guid",
                        "error",
                        f"Active chart field `{guid or name}` does not resolve to a dataset field.",
                        chart_id=chart_id,
                        field_guid=guid,
                    )
                )
            if field:
                edges.append({"from": f"field:{field.get('guid') or field.get('name')}", "to": f"dataset:{field.get('dataset_id')}"})

    source_edges, stale_findings = _source_field_edges(datasets, new_contract)
    edges.extend(source_edges)
    findings.extend(stale_findings)
    findings.extend(_selector_findings(selectors, datasets))

    return {
        "ok": not any(item["severity"] == "error" for item in findings),
        "schema_version": SCHEMA_VERSION,
        "datasets": [dataset["dataset_id"] for dataset in datasets],
        "active_chart_count": len(active_ids) or sum(1 for chart in charts if chart.get("active", True)),
        "edges": edges,
        "field_guid_count": len(fields_by_guid),
        "findings": findings,
        "validation_checklist": [
            "every active chart GUID resolves",
            "selector field aliases exist across target datasets",
            "source fields exist in the supplied physical contract",
            "dataset output grain is compatible with chart aggregation",
            "active and dormant objects are separated",
        ],
    }


def profile_performance(payload: dict[str, Any]) -> dict[str, Any]:
    charts = _normalize_charts(payload.get("charts") or [])
    rows: list[dict[str, Any]] = []
    stage_plans: list[dict[str, Any]] = []
    for chart in charts:
        sql = _chart_sql(chart)
        sql_report = analyze_sql(sql, source_name=str(chart.get("chart_id") or chart.get("id") or "<chart>")) if sql else {}
        timings = _normalize_timings(chart.get("timings") or payload.get("timings") or {})
        timing_status = "measured" if any(item.get("duration_ms") is not None for item in timings) else "timing_unavailable"
        row = {
            "chart_id": str(chart.get("chart_id") or chart.get("entryId") or chart.get("id") or ""),
            "dataset_id": str(chart.get("dataset_id") or chart.get("datasetId") or ""),
            "visible_tab": str(chart.get("visible_tab") or chart.get("tab") or ""),
            "source_query_hash": _sha256(sql) if sql else "",
            "cte_count": int((sql_report.get("metrics") or {}).get("cte_count") or 0),
            "joins": int((sql_report.get("metrics") or {}).get("join_count") or 0),
            "windows": int((sql_report.get("metrics") or {}).get("window_count") or 0),
            "aggregates": int((sql_report.get("metrics") or {}).get("aggregate_count") or 0),
            "field_slots": len(chart.get("fields") or _chart_fields_from_payload(chart)),
            "selector_defaults": chart.get("selector_defaults") or {},
            "response_rows": _int_or_none(chart.get("response_rows")),
            "response_bytes": _int_or_none(chart.get("response_bytes")),
            "request_id": str(chart.get("request_id") or ""),
            "query_id": str(chart.get("query_id") or ""),
            "trace_id": str(chart.get("trace_id") or ""),
            "timing_status": timing_status,
            "timings": timings,
            "evidence_source": _timing_sources(timings),
            "confidence": _performance_confidence(timings, sql_report),
        }
        rows.append(row)
        if _needs_stage_isolation(sql_report, row):
            stage_plans.append(_stage_isolation_plan(row, sql_report))
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "coverage": {
            "chart_count": len(rows),
            "measured_chart_count": sum(1 for row in rows if row["timing_status"] == "measured"),
            "timing_unavailable_count": sum(1 for row in rows if row["timing_status"] == "timing_unavailable"),
        },
        "timing_sources_are_separated": True,
        "browser_inspector_import": inspector_import_contract(),
        "chart_performance": rows,
        "stage_isolation_plans": stage_plans,
    }


def plan_optimizations(payload: dict[str, Any]) -> dict[str, Any]:
    performance = payload.get("performance") or profile_performance(payload)
    if payload.get("grain"):
        grain = payload["grain"]
    elif payload.get("dataset"):
        grain = analyze_aggregation_grain(payload)
    else:
        grain = {}
    rows = performance.get("chart_performance") or []
    blocked = _unsafe_optimization_blockers(grain)
    recommendations: list[dict[str, Any]] = []
    for row in rows:
        chart_id = row.get("chart_id") or ""
        if row.get("field_slots", 0) <= 2 and (row.get("joins", 0) or row.get("windows", 0) or row.get("cte_count", 0) >= 4):
            recommendations.append(
                _recommendation(
                    "split_lightweight_kpi_dataset",
                    [chart_id],
                    "simple KPI is backed by a heavy sequence/window query",
                    row,
                    proposed_grain="chart_metric_period_or_entity",
                    confidence="medium",
                )
            )
        if row.get("cte_count", 0) >= 4:
            recommendations.append(
                _recommendation(
                    "reduce_history_scan_after_key_set",
                    [chart_id],
                    "wide CTE chain should isolate the small entity/key set before broad history joins",
                    row,
                    proposed_grain="source_key_then_requested_period",
                    confidence="medium",
                )
            )
        if row.get("aggregates", 0) and row.get("windows", 0):
            recommendations.append(
                _recommendation(
                    "preserve_sequence_window_dataset_for_sequence_charts_only",
                    [chart_id],
                    "windowed sequence reconstruction is non-additive and should not feed simple KPI cards",
                    row,
                    proposed_grain="sequence_event_or_segment",
                    confidence="high",
                )
            )

    if not recommendations and rows:
        recommendations.append(
            _recommendation(
                "collect_runtime_timing_evidence",
                [str(row.get("chart_id") or "") for row in rows],
                "static complexity exists but measured timing evidence is missing or incomplete",
                rows[0],
                proposed_grain="unchanged",
                confidence="low",
            )
        )

    for blocker in blocked:
        recommendations.append(
            {
                "strategy": "blocked_unsafe_preaggregation",
                "affected_charts": blocker.get("affected_charts") or [],
                "status": "blocked",
                "current_bottleneck_evidence": blocker["message"],
                "proposed_grain": "none",
                "required_fields": [],
                "exact_vs_approximate": "exact_only",
                "selector_compatibility": "unchanged_required",
                "date_scale_compatibility": "unchanged_required",
                "expected_improvement_confidence": "none",
                "evidence_source": "aggregation_grain_contract",
                "parity_scenarios": ["no semantic rewrite allowed"],
                "rollback_plan": "no write planned",
                "stop_conditions": [blocker["message"]],
            }
        )

    return {
        "ok": not any(item.get("status") == "unsafe" for item in blocked),
        "schema_version": SCHEMA_VERSION,
        "automatic_mutation": False,
        "approximate_distinct_allowed": False,
        "hard_history_cap_allowed": False,
        "recommendations": recommendations,
        "blocked": blocked,
    }


def dl_diagnose_impl(
    *,
    mode: str,
    payload: dict[str, Any] | None = None,
    project_root: str = ".",
    max_items: int = 20,
) -> dict[str, Any]:
    payload = payload or {}
    normalized = str(mode or "").strip().lower()
    if normalized == "sql":
        result = analyze_sql(
            str(payload.get("sql") or ""),
            source_name=str(payload.get("source_name") or "<inline>"),
            schema_contract=payload.get("schema_contract") if isinstance(payload.get("schema_contract"), dict) else None,
            critical_ctes=[str(item) for item in payload.get("critical_ctes") or []],
        )
    elif normalized == "aggregation_grain":
        result = analyze_aggregation_grain(payload)
    elif normalized == "semantic_graph":
        result = analyze_semantic_graph(payload)
    elif normalized == "performance":
        result = profile_performance(payload)
    elif normalized == "optimization":
        result = plan_optimizations(payload)
    elif normalized == "synthetic_fleet_fixture":
        result = build_synthetic_fleet_fixture_assessment()
    elif normalized == "acceptance":
        result = build_acceptance_summary(payload)
    else:
        return {
            "ok": False,
            "mode": normalized,
            "error": {
                "category": "missing_input",
                "message": (
                    "mode must be sql, aggregation_grain, semantic_graph, performance, "
                    "optimization, synthetic_fleet_fixture, or acceptance"
                ),
            },
        }
    artifact = write_sql_performance_artifact(project_root, f"dl_diagnose_{normalized}.json", {"payload": payload, "result": result})
    return {
        "ok": bool(result.get("ok", False)),
        "mode": normalized,
        "summary": _bounded_result_summary(result, max_items=max_items),
        "artifact": artifact,
    }


def validate_payload_sql_performance(payload: dict[str, Any], *, source: str = "payload") -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.performance_budget import assess_performance_budget

    sql_values = _extract_sql_values(payload)
    sql_reports = [analyze_sql(sql, source_name=f"{source}.sql[{index}]") for index, sql in enumerate(sql_values)]
    lint_reports = [lint_editor_sql_text(sql, path=f"{source}.sql[{index}]") for index, sql in enumerate(sql_values)]
    grain_report = analyze_aggregation_grain(payload) if _payload_has_dataset_fields(payload) else {"ok": True, "blockers": []}
    budget_report = assess_performance_budget(payload)
    errors = []
    for report in sql_reports:
        for issue in report.get("diagnostics") or []:
            if issue.get("severity") == "error":
                errors.append(
                    f"{issue.get('rule')}: {issue.get('source_name')}:{issue.get('line')}:{issue.get('column')}"
                )
    for report in lint_reports:
        for issue in report.issues:
            if issue.severity == "error":
                errors.append(f"{issue.rule}: {issue.path}: {issue.message}")
    for blocker in grain_report.get("blockers") or []:
        errors.append(f"{blocker.get('rule')}: {blocker.get('message')}")
    for finding in budget_report.findings:
        if finding.severity == "error":
            errors.append(f"{finding.rule}: {finding.path}: {finding.message}")
    return {
        "ok": not errors,
        "sql_report_count": len(sql_reports),
        "sql_hashes": [report.get("source_hash") for report in sql_reports],
        "editor_sql_lint": {
            "ok": not any(issue.severity == "error" for report in lint_reports for issue in report.issues),
            "checked_sql_count": len(lint_reports),
            "error_rules": [
                issue.rule
                for report in lint_reports
                for issue in report.issues
                if issue.severity == "error"
            ],
        },
        "aggregation_grain": {
            "ok": grain_report.get("ok"),
            "blocker_count": len(grain_report.get("blockers") or []),
        },
        "performance_budget": budget_report.to_dict(),
        "issues": errors,
    }


def validate_project_sql_performance(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    candidates: list[Path] = []
    for pattern in (
        "dashboard/*/sources.js",
        "dashboard/*/bundle.json",
        "artifacts/**/*sources*.js",
        "artifacts/**/*sql*.json",
        "dataset/**/*.sql",
        "datasets/**/*.sql",
        "requirements/**/*.sql",
        "datalens_mapping/**/*dataset*.sql",
        "datalens_mapping/**/*source*.sql",
    ):
        candidates.extend(sorted(root.glob(pattern)))
    reports: list[dict[str, Any]] = []
    for candidate in _unique_files(candidates):
        if ARTIFACT_DIR in str(candidate):
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sql_values = _extract_sql_values(_json_or_text(text))
        if not sql_values and candidate.suffix.lower() == ".sql":
            sql_values = [text]
        for index, sql in enumerate(sql_values):
            reports.append(analyze_sql(sql, source_name=f"{candidate}:{index}"))
    issues = [
        f"{issue.get('rule')}: {issue.get('source_name')}:{issue.get('line')}:{issue.get('column')}"
        for report in reports
        for issue in report.get("diagnostics", [])
        if issue.get("severity") == "error"
    ]
    if not reports:
        issues.append("zero_semantic_sql_coverage: checked_sql_count is 0; an empty fixture cannot produce a pass")
    result = {
        "ok": not issues,
        "schema_version": SCHEMA_VERSION,
        "checked_sql_count": len(reports),
        "sql_hashes": [report.get("source_hash") for report in reports],
        "issues": issues,
        "reports": [
            {
                "source_name": report.get("source_name"),
                "source_hash": report.get("source_hash"),
                "parse_status": report.get("parse_status"),
                "diagnostic_count": len(report.get("diagnostics") or []),
                "error_rules": [
                    issue.get("rule") for issue in report.get("diagnostics", []) if issue.get("severity") == "error"
                ],
            }
            for report in reports
        ],
    }
    write_sql_performance_artifact(root, "project_semantic_validation.json", result)
    return result


def write_required_reports(project_root: str = ".", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(project_root)
    payload = payload or build_synthetic_fleet_fixture_payload()
    sql_reports = [
        analyze_sql(item["sql"], source_name=item["name"], schema_contract=item.get("schema_contract"))
        for item in payload["sql_cases"]
    ]
    aggregation = analyze_aggregation_grain(payload["grain_case"])
    graph = analyze_semantic_graph(payload["semantic_graph_case"])
    performance = profile_performance(payload["performance_case"])
    optimization = plan_optimizations({"performance": performance, **payload["grain_case"]})
    acceptance = build_acceptance_summary(
        {
            "sql_reports": sql_reports,
            "aggregation": aggregation,
            "graph": graph,
            "performance": performance,
            "optimization": optimization,
        }
    )

    paths = {
        "sql_parser_report.md": _write_report(root, "sql_parser_report.md", render_sql_parser_report(sql_reports)),
        "aggregation_grain_report.md": _write_report(root, "aggregation_grain_report.md", render_aggregation_report(aggregation)),
        "s2t_impact_report.md": _write_report(root, "s2t_impact_report.md", render_s2t_report(graph)),
        "chart_performance.csv": _write_csv(root, "chart_performance.csv", performance["chart_performance"]),
        "optimization_plan.md": _write_report(root, "optimization_plan.md", render_optimization_report(optimization)),
        "live_benchmark.md": _write_report(root, "live_benchmark.md", render_live_benchmark_report(performance)),
        "remaining_performance_gaps.md": _write_report(
            root,
            "remaining_performance_gaps.md",
            render_remaining_gaps_report(performance),
        ),
        "optimization_plan.json": write_sql_performance_artifact(root, "optimization_plan.json", optimization)["path"],
        "acceptance_summary.json": write_sql_performance_artifact(root, "acceptance_summary.json", acceptance)["path"],
        "raw/incident_queries.json": write_sql_performance_artifact(root, "raw/incident_queries.json", payload["sql_cases"])[
            "path"
        ],
    }
    return {"ok": acceptance["ok"], "paths": paths, "acceptance": acceptance}


def build_acceptance_summary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    sql_reports = payload.get("sql_reports") or []
    aggregation = payload.get("aggregation") or {}
    graph = payload.get("graph") or {}
    performance = payload.get("performance") or {}
    optimization = payload.get("optimization") or {}
    incident_rules = {
        issue.get("rule")
        for report in sql_reports
        for issue in report.get("diagnostics", [])
        if isinstance(issue, dict)
    }
    incident_rules.update(
        blocker.get("rule") for blocker in aggregation.get("blockers", []) if isinstance(blocker, dict)
    )
    return {
        "ok": {"unknown_identifier", "correlated_join_subquery", "nested_aggregation"}.issubset(incident_rules)
        and bool(aggregation.get("ok") is False)
        and bool(graph.get("ok") is False)
        and bool(performance.get("timing_sources_are_separated", True))
        and not bool(optimization.get("automatic_mutation", True)),
        "schema_version": SCHEMA_VERSION,
        "sql_analyzer_accuracy": {
            "golden_cases": len(sql_reports),
            "detected_rules": sorted(incident_rules),
            "parser_statuses": [report.get("parse_status") for report in sql_reports],
        },
        "aggregation_grain_results": {
            "blocker_count": len(aggregation.get("blockers") or []),
            "matrix_rows": len(aggregation.get("chart_field_matrix") or []),
        },
        "performance_coverage": performance.get("coverage") or {},
        "optimization_recommendations": len(optimization.get("recommendations") or []),
        "no_production_mutation": True,
        "timing_limitation": (
            "public DataLens read API does not expose browser Inspector render timings; "
            "use browser_inspector_export import evidence when available"
        ),
    }


def inspector_import_contract() -> dict[str, Any]:
    return {
        "schema_version": "2026-06-25.browser_inspector_import.v1",
        "signed_import_required": True,
        "fields": [
            "chart_id",
            "dashboard_id",
            "captured_at",
            "api_observed.duration_ms",
            "browser_inspector.data_fetch_ms",
            "browser_inspector.render_ms",
            "request_id",
            "query_id",
            "source_query_sha256",
        ],
        "timing_policy": (
            "report timing_unavailable unless supplied by API, browser Inspector export, "
            "query-engine evidence, or static estimate"
        ),
    }


def import_browser_inspector_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    signed = bool(evidence.get("signature") or evidence.get("sha256"))
    chart_id = str(evidence.get("chart_id") or "")
    timings = _normalize_timings({"browser_inspector": evidence.get("browser_inspector") or evidence})
    return {
        "ok": signed and bool(chart_id),
        "chart_id": chart_id,
        "signed": signed,
        "timings": timings,
        "source_query_hash": str(evidence.get("source_query_sha256") or ""),
    }


def build_synthetic_fleet_fixture_assessment() -> dict[str, Any]:
    """Build a deterministic assessment from repository-owned synthetic data."""
    payload = build_synthetic_fleet_fixture_payload()
    return {
        "ok": True,
        "sql": [
            analyze_sql(item["sql"], source_name=item["name"], schema_contract=item.get("schema_contract"))
            for item in payload["sql_cases"]
        ],
        "aggregation": analyze_aggregation_grain(payload["grain_case"]),
        "semantic_graph": analyze_semantic_graph(payload["semantic_graph_case"]),
        "performance": profile_performance(payload["performance_case"]),
        "optimization": plan_optimizations({"performance": profile_performance(payload["performance_case"]), **payload["grain_case"]}),
    }


def build_reviewed_sql_semantic_cases() -> dict[str, Any]:
    """Return deterministic reviewed cases for the supported DataLens SQL subset.

    The cases are generated from small reviewed templates so they stay compact in
    source while still exercising comments, strings, parameters, CTEs, joins,
    aggregates, windows, arrays/lambdas, selector lineage, GUID resolution, and
    grain compatibility in a stable way.
    """
    sql_cases: list[dict[str, Any]] = []
    for index in range(1, 31):
        sql_cases.append(
            {
                "name": f"simple_projection_filter_{index:03d}",
                "category": "projection_filter",
                "sql": (
                    f"-- reviewed case {index}\n"
                    f"SELECT entity_id AS entity_id, toDate(event_dttm) AS day_{index}, "
                    f"'status_{index}' AS status_label\n"
                    f"FROM mart.events_{index % 5} e\n"
                    f"WHERE e.event_dttm >= {{date_from}} AND e.status = 'active'\n"
                    f"GROUP BY entity_id, day_{index}, status_label"
                ),
                "expected_parse_status": "ok",
                "expected_rules": [],
            }
        )
    for index in range(1, 26):
        sql_cases.append(
            {
                "name": f"cte_join_key_reduction_{index:03d}",
                "category": "cte_join",
                "sql": (
                    "WITH scoped AS (\n"
                    f"  SELECT scope_id AS scope_id FROM synthetic.scope_keys WHERE scope_key = {{scope_{index}}}\n"
                    "), facts AS (\n"
                    f"  SELECT f.scope_id AS scope_id, f.entity_id AS entity_id, sum(f.value) AS value_sum_{index}\n"
                    "  FROM synthetic.entity_facts f\n"
                    "  INNER JOIN scoped s ON s.scope_id = f.scope_id\n"
                    "  GROUP BY f.scope_id, f.entity_id\n"
                    ")\n"
                    f"SELECT facts.entity_id AS entity_id, facts.value_sum_{index} AS value_sum\n"
                    "FROM facts"
                ),
                "expected_parse_status": "ok",
                "expected_rules": [],
            }
        )
    for index in range(1, 21):
        sql_cases.append(
            {
                "name": f"aggregate_window_array_{index:03d}",
                "category": "aggregate_window_array",
                "sql": (
                    "WITH raw AS (\n"
                    f"  SELECT vehicle_id AS vehicle_id, groupArray(speed) AS speeds, sum(distance) AS distance_sum_{index}\n"
                    f"  FROM synthetic.vehicle_events_{index % 4}\n"
                    "  GROUP BY vehicle_id\n"
                    "), ranked AS (\n"
                    f"  SELECT vehicle_id AS vehicle_id, arrayMap(x -> x + {index}, speeds) AS speeds_shifted, "
                    "row_number() OVER (PARTITION BY vehicle_id ORDER BY vehicle_id) AS rn\n"
                    "  FROM raw\n"
                    ")\n"
                    "SELECT vehicle_id AS vehicle_id, rn AS rn FROM ranked"
                ),
                "expected_parse_status": "ok",
                "expected_rules": [],
            }
        )
    for index in range(1, 16):
        sql_cases.append(
            {
                "name": f"schema_contract_unknown_{index:03d}",
                "category": "schema_contract",
                "sql": (
                    "WITH activity AS (\n"
                    "  SELECT car.vehicle_id, car.event_dttm, car.retired_status\n"
                    "  FROM synthetic.vehicle_events car\n"
                    ")\n"
                    "SELECT activity.vehicle_id, activity.retired_status FROM activity"
                ),
                "schema_contract": {"tables": {"synthetic.vehicle_events": ["vehicle_id", "event_dttm"]}},
                "expected_parse_status": "ok",
                "expected_rules": ["stale_s2t_field", "unknown_identifier"],
            }
        )
    for index in range(1, 16):
        sql_cases.append(
            {
                "name": f"history_stage_isolation_{index:03d}",
                "category": "stage_isolation",
                "sql": (
                    "WITH selected_scope AS (\n"
                    f"  SELECT scope_id FROM synthetic.scope_keys WHERE scope_key IN ({{scope_keys_{index}}})\n"
                    "), state_history AS (\n"
                    "  SELECT entity_id, period_id, state_name FROM synthetic.entity_state_history\n"
                    "), entity_links AS (\n"
                    "  SELECT source_entity_id, target_entity_id FROM synthetic.entity_links\n"
                    ")\n"
                    "SELECT sh.state_name AS state_name, count(el.target_entity_id) AS links\n"
                    "FROM state_history sh\n"
                    "LEFT JOIN entity_links el ON el.source_entity_id = sh.entity_id\n"
                    "GROUP BY sh.state_name"
                ),
                "expected_parse_status": "ok",
                "expected_rules": ["broad_history_scan_before_key_reduction"],
            }
        )

    semantic_cases: list[dict[str, Any]] = []
    for index in range(1, 16):
        semantic_cases.append(
            {
                "name": f"semantic_selector_guid_{index:03d}",
                "payload": {
                    "active_chart_ids": [f"chart_{index}"],
                    "new_contract": {"tables": {"mart.events": ["entity_id", "event_dttm", "value"]}},
                    "datasets": [
                        {
                            "dataset_id": f"dataset_{index}",
                            "source_table": "mart.events",
                            "fields": [
                                {"guid": f"guid_entity_{index}", "name": "entity_id", "source_expression": "entity_id"},
                                {"guid": f"guid_value_{index}", "name": "value", "source_expression": "value"},
                            ],
                        }
                    ],
                    "charts": [
                        {
                            "chart_id": f"chart_{index}",
                            "active": True,
                            "fields": [{"slot": "measure", "field_guid": f"guid_value_{index}", "aggregation": "sum"}],
                        }
                    ],
                    "selectors": [
                        {
                            "selector_id": f"selector_{index}",
                            "field_name": "entity_id",
                            "target_dataset_ids": [f"dataset_{index}"],
                        }
                    ],
                },
                "expected_ok": True,
            }
        )
    for index in range(1, 11):
        semantic_cases.append(
            {
                "name": f"semantic_missing_guid_{index:03d}",
                "payload": {
                    "active_chart_ids": [f"bad_chart_{index}"],
                    "datasets": [{"dataset_id": f"bad_dataset_{index}", "fields": [{"guid": "known", "name": "value"}]}],
                    "charts": [
                        {
                            "chart_id": f"bad_chart_{index}",
                            "active": True,
                            "fields": [{"slot": "measure", "field_guid": f"missing_{index}", "aggregation": "sum"}],
                        }
                    ],
                },
                "expected_rules": ["unresolved_chart_field_guid"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "review_status": "reviewed_template_corpus",
        "sql_cases": sql_cases,
        "semantic_cases": semantic_cases,
        "case_count": len(sql_cases) + len(semantic_cases),
    }


def run_reviewed_case_corpus(corpus: dict[str, Any] | None = None) -> dict[str, Any]:
    corpus = corpus or build_reviewed_sql_semantic_cases()
    sql_results = []
    for case in corpus["sql_cases"]:
        result = analyze_sql(
            case["sql"],
            source_name=case["name"],
            schema_contract=case.get("schema_contract") if isinstance(case.get("schema_contract"), dict) else None,
        )
        expected = set(case.get("expected_rules") or [])
        actual = {item.get("rule") for item in result.get("diagnostics") or []}
        sql_results.append(
            {
                "name": case["name"],
                "category": case["category"],
                "parse_status": result.get("parse_status"),
                "source_hash": result.get("source_hash"),
                "expected_rules": sorted(expected),
                "detected_rules": sorted(rule for rule in actual if rule),
                "missing_rules": sorted(expected - actual),
                "diagnostic_count": len(result.get("diagnostics") or []),
            }
        )
    semantic_results = []
    for case in corpus["semantic_cases"]:
        result = analyze_semantic_graph(case["payload"])
        expected = set(case.get("expected_rules") or [])
        actual = {item.get("rule") for item in result.get("findings") or []}
        semantic_results.append(
            {
                "name": case["name"],
                "ok": result.get("ok"),
                "expected_rules": sorted(expected),
                "detected_rules": sorted(rule for rule in actual if rule),
                "missing_rules": sorted(expected - actual),
                "field_guid_count": result.get("field_guid_count"),
                "active_chart_count": result.get("active_chart_count"),
            }
        )
    stability_hash = _sha256(stable_json_text({"sql": sql_results, "semantic": semantic_results}))
    return {
        "ok": not any(item["missing_rules"] for item in [*sql_results, *semantic_results]),
        "schema_version": SCHEMA_VERSION,
        "review_status": corpus["review_status"],
        "case_count": corpus["case_count"],
        "sql_case_count": len(sql_results),
        "semantic_case_count": len(semantic_results),
        "parse_status_counts": _counts(item["parse_status"] for item in sql_results),
        "category_counts": _counts(item["category"] for item in sql_results),
        "stability_hash": stability_hash,
        "sql_results": sql_results,
        "semantic_results": semantic_results,
    }


def build_synthetic_fleet_fixture_payload() -> dict[str, Any]:
    """Return a deterministic, non-production fixture for SQL diagnostics."""
    wide_sequence_sql = """
WITH raw_events AS (
    SELECT vehicle_id, event_dttm, latitude, longitude, speed, state_name
    FROM synthetic.vehicle_events
),
sequence_windows AS (
    SELECT vehicle_id, event_dttm, speed,
           row_number() OVER (PARTITION BY vehicle_id ORDER BY event_dttm) AS rn
    FROM raw_events
),
daily AS (
    SELECT toDate(event_dttm) AS day, vehicle_id, sum(speed) AS daily_value
    FROM sequence_windows
    GROUP BY day, vehicle_id
)
SELECT day, vehicle_id, sum(daily_value) AS speed_sum
FROM daily
GROUP BY day, vehicle_id
"""
    code47_sql = """
WITH activity AS (
    SELECT vehicle.vehicle_id, vehicle.event_dttm, vehicle.legacy_state
    FROM synthetic.vehicle_events vehicle
)
SELECT activity.vehicle_id, activity.legacy_state
FROM activity
"""
    code48_sql = """
WITH entities AS (
    SELECT entity_id, entity_key FROM synthetic.entities
)
SELECT entity.entity_key, link_counts.link_count
FROM entities entity
LEFT JOIN (
    SELECT entity_id, count(*) AS link_count
    FROM synthetic.entity_links link
    WHERE link.entity_id = entity.entity_id
    GROUP BY entity_id
) link_counts ON link_counts.entity_id = entity.entity_id
"""
    history_chain_sql = """
WITH selected_scope AS (
    SELECT scope_id FROM synthetic.scope_keys WHERE scope_key IN ({scope_keys})
),
entity_scope AS (
    SELECT entity_id, entity_key FROM synthetic.entities WHERE scope_id IN (SELECT scope_id FROM selected_scope)
),
state_history AS (
    SELECT entity_id, period_id, state_name FROM synthetic.entity_state_history
),
entity_links AS (
    SELECT source_entity_id, target_entity_id FROM synthetic.entity_links
)
SELECT entity.entity_key, history.state_name, count(link.target_entity_id) AS links
FROM entity_scope entity
LEFT JOIN state_history history ON history.entity_id = entity.entity_id
LEFT JOIN entity_links link ON link.source_entity_id = entity.entity_id
GROUP BY entity.entity_key, history.state_name
"""
    chart_ids = [f"chart_synthetic_fleet_{index:02d}" for index in range(1, 19)]
    return {
        "sql_cases": [
            {
                "name": "code47_alias_and_stale_s2t",
                "sql": code47_sql,
                "schema_contract": {"tables": {"synthetic.vehicle_events": ["vehicle_id", "event_dttm"]}},
            },
            {"name": "code48_correlated_join", "sql": code48_sql},
            {"name": "history_wide_cte_chain", "sql": history_chain_sql},
            {"name": "synthetic_fleet_sequence_window", "sql": wide_sequence_sql},
        ],
        "grain_case": {
            "dataset": {
                "dataset_id": "dataset_synthetic_fleet_events",
                "physical_grain": ["vehicle_id", "event_dt"],
                "output_grain": ["vehicle_id", "day"],
                "fields": [
                    {"guid": "guid_vehicle_id", "name": "vehicle_id", "source_expression": "vehicle_id", "aggregation": "none"},
                    {
                        "guid": "guid_daily_value",
                        "name": "daily_value",
                        "source_expression": "sum(speed)",
                        "formula": "SUM([daily_value])",
                        "aggregation": "sum",
                        "grain": ["vehicle_id", "day"],
                    },
                    {
                        "guid": "guid_vehicle_distinct",
                        "name": "vehicle_distinct",
                        "formula": "COUNTD([vehicle_id])",
                        "aggregation": "countdistinct",
                        "grain": ["day"],
                    },
                ],
            },
            "charts": [
                {
                    "chart_id": "chart_synthetic_fleet_01",
                    "fields": [{"slot": "measure", "field_guid": "guid_daily_value", "aggregation": "sum"}],
                },
                {
                    "chart_id": "chart_synthetic_fleet_02",
                    "fields": [{"slot": "measure", "field_guid": "guid_vehicle_distinct", "aggregation": "sum"}],
                },
            ],
        },
        "semantic_graph_case": {
            "active_chart_ids": chart_ids,
            "new_contract": {"tables": {"synthetic.vehicle_events": ["vehicle_id", "event_dttm", "speed"]}},
            "datasets": [
                {
                    "dataset_id": "dataset_synthetic_fleet_events",
                    "fields": [
                        {"guid": "guid_vehicle_id", "name": "vehicle_id", "source_expression": "vehicle_id"},
                        {"guid": "guid_daily_value", "name": "daily_value", "source_expression": "daily_value"},
                    ],
                }
            ],
            "charts": [
                *[
                    {
                        "chart_id": chart_id,
                        "active": True,
                        "fields": [{"slot": "measure", "field_guid": "guid_daily_value", "aggregation": "sum"}],
                    }
                    for chart_id in chart_ids[:17]
                ],
                {
                    "chart_id": chart_ids[-1],
                    "active": True,
                    "fields": [{"slot": "measure", "field_guid": "guid_missing", "aggregation": "sum"}],
                },
            ],
            "selectors": [
                {
                    "selector_id": "selector_vehicle",
                    "field_name": "vehicle_id",
                    "target_dataset_ids": ["dataset_synthetic_fleet_events"],
                    "aliases": {"dataset_synthetic_fleet_events": "vehicle_id"},
                }
            ],
        },
        "performance_case": {
            "charts": [
                {
                    "chart_id": chart_ids[0],
                    "dataset_id": "dataset_synthetic_fleet_events",
                    "visible_tab": "Overview",
                    "source_sql": wide_sequence_sql,
                    "fields": [{"slot": "measure", "field_guid": "guid_vehicle_distinct"}],
                    "timings": {"static_estimate": {"duration_ms": None, "source": "static"}},
                },
                *[
                    {
                        "chart_id": chart_id,
                        "dataset_id": "dataset_synthetic_fleet_events",
                        "visible_tab": "Synthetic Fleet",
                        "source_sql": (
                            wide_sequence_sql
                            if index % 3 == 0
                            else "SELECT day, vehicle_id, value FROM synthetic.daily_vehicle_events"
                        ),
                        "fields": [{"slot": "measure", "field_guid": "guid_daily_value"}],
                        "timings": {},
                    }
                    for index, chart_id in enumerate(chart_ids[1:], start=2)
                ],
            ]
        },
    }


def tokenize_sql(sql: str) -> tuple[list[Token], list[dict[str, Any]]]:
    tokens: list[Token] = []
    issues: list[dict[str, Any]] = []
    i = 0
    while i < len(sql):
        char = sql[i]
        if char.isspace():
            i += 1
            continue
        if sql.startswith("--", i):
            end = sql.find("\n", i + 2)
            i = len(sql) if end == -1 else end + 1
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end == -1:
                issues.append({"offset": i, "message": "unterminated block comment"})
                break
            i = end + 2
            continue
        if char in ("'", '"', "`"):
            end = _quoted_end(sql, i, char)
            kind = "string" if char in ("'", '"') else "identifier"
            if end == -1:
                issues.append({"offset": i, "message": f"unterminated {kind}"})
                end = len(sql)
            tokens.append(Token(sql[i:end], i, end, kind))
            i = end
            continue
        if char == "{" and i + 1 < len(sql) and sql[i + 1] == "{":
            end = sql.find("}}", i + 2)
            if end == -1:
                issues.append({"offset": i, "message": "unterminated template parameter"})
                end = len(sql) - 2
            tokens.append(Token(sql[i : end + 2], i, end + 2, "parameter"))
            i = end + 2
            continue
        if char.isalpha() or char == "_":
            end = i + 1
            while end < len(sql) and (sql[end].isalnum() or sql[end] in ("_", "$")):
                end += 1
            tokens.append(Token(sql[i:end], i, end, "word"))
            i = end
            continue
        if char.isdigit():
            end = i + 1
            while end < len(sql) and (sql[end].isalnum() or sql[end] in ("_", ".")):
                end += 1
            tokens.append(Token(sql[i:end], i, end, "number"))
            i = end
            continue
        if i + 1 < len(sql) and sql[i : i + 2] in {">=", "<=", "!=", "<>", "->", "::"}:
            tokens.append(Token(sql[i : i + 2], i, i + 2, "symbol"))
            i += 2
            continue
        tokens.append(Token(char, i, i + 1, "symbol"))
        i += 1
    return tokens, issues


def _parse_query(tokens: list[Token], sql: str, *, source_name: str) -> dict[str, Any]:
    cte_defs, main_tokens, partial_spans = _parse_ctes(tokens)
    cte_names = set(cte_defs)
    cte_reports: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    for name, body in cte_defs.items():
        report = _parse_select_scope(body["tokens"], sql, scope=name, cte_names=cte_names, parent_aliases=set())
        cte_reports[name] = report
        diagnostics.extend(report["diagnostics"])
    main_report = _parse_select_scope(main_tokens, sql, scope="__final__", cte_names=cte_names, parent_aliases=set())
    diagnostics.extend(main_report["diagnostics"])
    cte_dependency_dag = {
        name: sorted(_referenced_ctes(cte_report["tokens"], cte_names - {name})) for name, cte_report in cte_reports.items()
    }
    ctes = [
        {
            "name": name,
            "offset": body["start"],
            "hash": _sha256(sql[body["start"] : body["end"]]),
            "projection_count": len(cte_reports[name]["projections"]),
        }
        for name, body in cte_defs.items()
    ]
    reports = [*cte_reports.values(), main_report]
    return {
        "partial_spans": partial_spans,
        "diagnostics": diagnostics,
        "ctes": ctes,
        "cte_dependency_dag": cte_dependency_dag,
        "projections": [projection for report in reports for projection in report["projections"]],
        "aliases": [alias for report in reports for alias in report["aliases"]],
        "source_lineage": [source for report in reports for source in report["source_lineage"]],
        "join_hints": [join for report in reports for join in report["join_hints"]],
        "filter_pushdown": [item for report in reports for item in report["filter_pushdown"]],
        "parameters": sorted({token.value for token in tokens if token.kind == "parameter"}),
        "final_grain_candidates": main_report["grain_candidates"],
        "function_calls": [item for report in reports for item in report["function_calls"]],
    }


def _parse_ctes(tokens: list[Token]) -> tuple[dict[str, dict[str, Any]], list[Token], list[dict[str, Any]]]:
    if not tokens or tokens[0].lower != "with":
        return {}, tokens, []
    ctes: dict[str, dict[str, Any]] = {}
    partial_spans: list[dict[str, Any]] = []
    index = 1
    while index < len(tokens):
        if index + 2 >= len(tokens) or tokens[index].kind not in {"word", "identifier"}:
            break
        name = _clean_identifier(tokens[index].value)
        if tokens[index + 1].lower != "as" or tokens[index + 2].value != "(":
            break
        close = _matching_paren(tokens, index + 2)
        if close is None:
            partial_spans.append({"start": tokens[index + 2].start, "end": tokens[-1].end, "reason": "unbalanced_cte"})
            return ctes, tokens[index:], partial_spans
        ctes[name] = {
            "tokens": tokens[index + 3 : close],
            "start": tokens[index].start,
            "end": tokens[close].end,
        }
        index = close + 1
        if index < len(tokens) and tokens[index].value == ",":
            index += 1
            continue
        break
    return ctes, tokens[index:], partial_spans


def _parse_select_scope(
    tokens: list[Token],
    sql: str,
    *,
    scope: str,
    cte_names: set[str],
    parent_aliases: set[str],
) -> dict[str, Any]:
    select_i = _top_level_keyword(tokens, "select", 0)
    from_i = _top_level_keyword(tokens, "from", select_i + 1 if select_i is not None else 0)
    group_i = _top_level_keyword(tokens, "group", from_i + 1 if from_i is not None else 0)
    where_i = _top_level_keyword(tokens, "where", from_i + 1 if from_i is not None else 0)
    order_i = _top_level_keyword(tokens, "order", from_i + 1 if from_i is not None else 0)
    end_i = min([idx for idx in (group_i, order_i) if idx is not None] or [len(tokens)])
    projections: list[dict[str, Any]] = []
    aliases: list[dict[str, str]] = []
    source_lineage: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    if select_i is None:
        return _empty_scope(tokens, scope)
    projection_spans = _split_top_level(tokens[select_i + 1 : from_i if from_i is not None else len(tokens)], ",")
    for span in projection_spans:
        projection = _projection_info(span, sql, scope)
        projections.append(projection)
        if not projection["alias"] and projection["requires_alias"]:
            diagnostics.append(
                _finding(
                    "implicit_projected_name",
                    "error" if scope != "__final__" else "warning",
                    "Projected expression requires an explicit stable alias before downstream use.",
                    offset=projection["offset"],
                    sql=sql,
                    source=projection["source_name"],
                    cte=scope,
                    identifier=projection["expression_excerpt"],
                    remediation="Add `AS stable_snake_case_alias` in the CTE projection.",
                )
            )
    if from_i is not None:
        from_end = min([idx for idx in (where_i, group_i, order_i) if idx is not None and idx > from_i] or [len(tokens)])
        alias_data = _parse_from_and_joins(tokens[from_i + 1 : from_end], sql, scope, cte_names, parent_aliases)
        aliases = alias_data["aliases"]
        source_lineage = alias_data["source_lineage"]
        joins = alias_data["joins"]
        diagnostics.extend(alias_data["diagnostics"])

    alias_names = {item["alias"].lower() for item in aliases if item.get("alias")}
    allowed_prefixes = alias_names | {item.lower() for item in cte_names}
    for ref in _qualified_references(tokens):
        prefix = ref["parts"][0].lower()
        if prefix in allowed_prefixes or _looks_like_catalog_reference(ref, aliases):
            continue
        diagnostics.append(
            _finding(
                "unknown_identifier",
                "error",
                f"Qualified reference `{'.'.join(ref['parts'][:2])}` has no visible alias/CTE in scope.",
                offset=ref["offset"],
                sql=sql,
                source=scope,
                cte=scope,
                identifier=".".join(ref["parts"]),
                remediation="Declare the alias explicitly or project the field from the owning CTE with a stable alias.",
            )
        )

    function_calls = _function_calls(tokens)
    filter_pushdown = _filter_pushdown(tokens[where_i + 1 : end_i] if where_i is not None else [], scope)
    grain_candidates = _grain_candidates(tokens[group_i + 2 : order_i or len(tokens)] if group_i is not None else [], function_calls)
    return {
        "tokens": tokens,
        "projections": projections,
        "aliases": aliases,
        "source_lineage": source_lineage,
        "join_hints": joins,
        "diagnostics": diagnostics,
        "filter_pushdown": filter_pushdown,
        "grain_candidates": grain_candidates,
        "function_calls": function_calls,
    }


def _empty_scope(tokens: list[Token], scope: str) -> dict[str, Any]:
    return {
        "tokens": tokens,
        "projections": [],
        "aliases": [],
        "source_lineage": [],
        "join_hints": [],
        "diagnostics": [],
        "filter_pushdown": [],
        "grain_candidates": [],
        "function_calls": [],
        "scope": scope,
    }


def _parse_from_and_joins(
    tokens: list[Token],
    sql: str,
    scope: str,
    cte_names: set[str],
    parent_aliases: set[str],
) -> dict[str, Any]:
    aliases: list[dict[str, str]] = []
    source_lineage: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    index = 0
    pending_join = "from"
    while index < len(tokens):
        token = tokens[index]
        if token.lower in {"left", "right", "inner", "full", "cross"}:
            pending_join = token.lower
            index += 1
            continue
        if token.lower == "join":
            pending_join = "join" if pending_join == "from" else pending_join + "_join"
            index += 1
            continue
        if token.lower in {"on", "using"}:
            on_start = index + 1
            on_end = _next_join_index(tokens, on_start)
            joins.append(_join_hint(tokens[on_start:on_end], pending_join, scope))
            index = on_end
            pending_join = "join"
            continue
        if token.value == "(":
            close = _matching_paren(tokens, index)
            if close is None:
                break
            alias = _alias_after(tokens, close + 1)
            if alias:
                aliases.append({"alias": alias, "source": "subquery", "scope": scope})
            sub_report = _parse_select_scope(
                tokens[index + 1 : close],
                sql,
                scope=f"{scope}.{alias or 'subquery'}",
                cte_names=cte_names,
                parent_aliases={item["alias"].lower() for item in aliases if item.get("alias")} | parent_aliases,
            )
            outer_refs = [
                ref
                for ref in _qualified_references(tokens[index + 1 : close])
                if ref["parts"][0].lower() in parent_aliases
                or ref["parts"][0].lower() in {item["alias"].lower() for item in aliases if item.get("alias")}
            ]
            for ref in outer_refs:
                diagnostics.append(
                    _finding(
                        "correlated_join_subquery",
                        "error",
                        "JOIN subquery references an outer alias and can fail in ClickHouse with Code 48.",
                        offset=ref["offset"],
                        sql=sql,
                        source=scope,
                        cte=scope,
                        identifier=".".join(ref["parts"]),
                        remediation="Precompute the relation as a separate CTE and join on explicit keys after key reduction.",
                    )
                )
            diagnostics.extend(sub_report["diagnostics"])
            index = close + 1
            if alias and index < len(tokens) and tokens[index].lower == "as":
                index += 2
            elif alias:
                index += 1
            continue
        if token.kind in {"word", "identifier"} and token.lower not in SQL_KEYWORDS:
            table_parts = [token.value]
            cursor = index + 1
            while cursor + 1 < len(tokens) and tokens[cursor].value == "." and tokens[cursor + 1].kind in {"word", "identifier"}:
                table_parts.append(tokens[cursor + 1].value)
                cursor += 2
            alias = _alias_after(tokens, cursor)
            source = ".".join(_clean_identifier(part) for part in table_parts)
            if alias:
                aliases.append({"alias": alias, "source": source, "scope": scope})
            elif source.split(".")[-1].lower() not in cte_names:
                aliases.append({"alias": source.split(".")[-1], "source": source, "scope": scope})
            source_lineage.append({"scope": scope, "source": source, "alias": alias or source.split(".")[-1], "offset": token.start})
            index = cursor + (2 if cursor < len(tokens) and tokens[cursor].lower == "as" and alias else 1 if alias else 0)
            continue
        index += 1
    return {"aliases": aliases, "source_lineage": source_lineage, "joins": joins, "diagnostics": diagnostics}


def _projection_info(tokens: list[Token], sql: str, scope: str) -> dict[str, Any]:
    if not tokens:
        return {"scope": scope, "alias": "", "offset": 0, "requires_alias": False, "expression_excerpt": ""}
    alias = ""
    expression_tokens = tokens
    for index, token in enumerate(tokens):
        if token.lower == "as" and index + 1 < len(tokens):
            alias = _clean_identifier(tokens[index + 1].value)
            expression_tokens = tokens[:index]
            break
    if not alias and len(tokens) >= 2 and tokens[-1].kind in {"word", "identifier"} and tokens[-2].value not in {".", ")"}:
        if tokens[-1].lower not in SQL_KEYWORDS:
            alias = _clean_identifier(tokens[-1].value)
            expression_tokens = tokens[:-1]
    expr_text = _tokens_text(expression_tokens, sql)
    if expr_text == "*":
        simple_identifier = True
        requires_alias = False
    else:
        simple_identifier = len(expression_tokens) == 1 and all(
            token.kind in {"word", "identifier"} or token.value == "." for token in expression_tokens
        )
        requires_alias = not alias and not simple_identifier
    return {
        "source_name": scope,
        "scope": scope,
        "alias": alias,
        "offset": tokens[0].start,
        "expression_hash": _sha256(expr_text),
        "expression_excerpt": _bounded(expr_text, 120),
        "requires_alias": requires_alias,
        "lineage_identifiers": [".".join(ref["parts"]) for ref in _qualified_references(expression_tokens)],
        "aggregate": any(call["function"] in AGGREGATE_FUNCTIONS for call in _function_calls(expression_tokens)),
        "window": any(call["function"] in WINDOW_HINTS for call in _function_calls(expression_tokens)),
    }


def _assess_dataset_field(field: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    formula = str(field.get("formula") or field.get("source_expression") or "")
    default_agg = _normalize_aggregation(field.get("aggregation"))
    blockers = []
    if _has_aggregate(formula) and default_agg in AGGREGATE_FUNCTIONS:
        blockers.append(
            _blocker(
                "nested_aggregation",
                f"Dataset field `{field.get('name')}` is aggregated in formula and has default aggregation `{default_agg}`.",
                field_guid=field.get("guid", ""),
                dataset_id=dataset["dataset_id"],
            )
        )
    if "/" in formula and _has_aggregate(formula) and default_agg in AGGREGATE_FUNCTIONS:
        blockers.append(
            _blocker(
                "ratio_reaggregation",
                f"Dataset field `{field.get('name')}` is a ratio of aggregates and must not be re-aggregated blindly.",
                field_guid=field.get("guid", ""),
                dataset_id=dataset["dataset_id"],
            )
        )
    return {
        "field_guid": field.get("guid", ""),
        "field_name": field.get("name", ""),
        "source_expression_hash": _sha256(formula),
        "default_aggregation": default_agg,
        "grain": field.get("grain") or dataset["output_grain"],
        "aggregate_status": "aggregate" if _has_aggregate(formula) else "row",
        "blockers": blockers,
    }


def _assess_field_grain(
    dataset: dict[str, Any],
    chart: dict[str, Any],
    slot: dict[str, Any],
    field: dict[str, Any] | None,
) -> dict[str, Any]:
    chart_agg = _normalize_aggregation(slot.get("aggregation") or chart.get("aggregation"))
    blockers: list[dict[str, Any]] = []
    if not field:
        blockers.append(
            _blocker(
                "unresolved_chart_field_guid",
                f"Chart `{chart.get('chart_id')}` references a field that is not present in dataset `{dataset['dataset_id']}`.",
                chart_id=chart.get("chart_id", ""),
                field_guid=str(slot.get("field_guid") or slot.get("guid") or ""),
            )
        )
    else:
        field_formula = str(field.get("formula") or field.get("source_expression") or "")
        field_agg = _normalize_aggregation(field.get("aggregation"))
        if _has_aggregate(field_formula) and chart_agg in AGGREGATE_FUNCTIONS:
            blockers.append(
                _blocker(
                    "nested_aggregation",
                    f"Chart `{chart.get('chart_id')}` applies `{chart_agg}` to pre-aggregated field `{field.get('name')}`.",
                    chart_id=chart.get("chart_id", ""),
                    field_guid=field.get("guid", ""),
                )
            )
        if field_agg in NON_ADDITIVE_AGGS and chart_agg in AGGREGATE_FUNCTIONS - {"count"}:
            blockers.append(
                _blocker(
                    "non_additive_reaggregation",
                    f"Chart `{chart.get('chart_id')}` re-aggregates non-additive field `{field.get('name')}`.",
                    chart_id=chart.get("chart_id", ""),
                    field_guid=field.get("guid", ""),
                )
            )
        if (field_agg in {"countdistinct", "uniq", "uniqexact"} or "countd" in field_formula.lower()) and chart_agg in AGGREGATE_FUNCTIONS:
            blockers.append(
                _blocker(
                    "distinct_over_preaggregated_grain",
                    f"Chart `{chart.get('chart_id')}` risks distinct-count drift at dataset grain `{dataset['output_grain']}`.",
                    chart_id=chart.get("chart_id", ""),
                    field_guid=field.get("guid", ""),
                )
            )
    return {
        "chart_id": chart.get("chart_id", ""),
        "slot": slot.get("slot", "field"),
        "field_guid": str(slot.get("field_guid") or slot.get("guid") or (field or {}).get("guid") or ""),
        "field_name": str(slot.get("field_name") or slot.get("name") or (field or {}).get("name") or ""),
        "dataset_id": dataset["dataset_id"],
        "dataset_output_grain": dataset["output_grain"],
        "chart_aggregation": chart_agg,
        "compatible": not blockers,
        "blockers": blockers,
    }


def _source_field_edges(
    datasets: list[dict[str, Any]],
    new_contract: dict[str, set[str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    edges: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    for dataset in datasets:
        default_table = str(dataset.get("source_table") or "")
        for field in dataset["fields"]:
            expression = str(field.get("source_expression") or field.get("formula") or field.get("name") or "")
            for identifier in _formula_identifiers(expression):
                table = default_table or _matching_contract_table(identifier, new_contract)
                edges.append({"from": f"field:{field.get('guid') or field.get('name')}", "to": f"source:{table}:{identifier}"})
                if new_contract and not _contract_has_column(new_contract, table, identifier):
                    findings.append(
                        _graph_finding(
                            "stale_source_field",
                            "error",
                            f"Source field `{identifier}` is absent from the new physical contract.",
                            dataset_id=dataset["dataset_id"],
                            field_guid=field.get("guid", ""),
                        )
                    )
    return edges, findings


def _selector_findings(selectors: list[dict[str, Any]], datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields_by_dataset = {
        dataset["dataset_id"]: {field["name"].lower() for field in dataset["fields"] if field.get("name")}
        for dataset in datasets
    }
    findings: list[dict[str, Any]] = []
    for selector in selectors:
        field_name = str(selector.get("field_name") or selector.get("field") or "").lower()
        aliases = selector.get("aliases") if isinstance(selector.get("aliases"), dict) else {}
        target_dataset_ids = [str(item) for item in selector.get("target_dataset_ids") or [] if str(item)]
        if not target_dataset_ids:
            findings.append(
                _graph_finding(
                    "selector_target_coverage_missing",
                    "error",
                    f"Selector `{selector.get('selector_id')}` has no target_dataset_ids, so alias coverage cannot be verified.",
                )
            )
            continue
        for dataset_id in target_dataset_ids:
            resolved = str(aliases.get(dataset_id) or field_name).lower()
            if resolved and resolved in fields_by_dataset.get(dataset_id, set()):
                continue
            findings.append(
                _graph_finding(
                    "selector_field_missing",
                    "error",
                    f"Selector `{selector.get('selector_id')}` field `{resolved or field_name}` is missing in dataset `{dataset_id}`.",
                    dataset_id=dataset_id,
                )
            )
    return findings


def _normalize_dataset(value: dict[str, Any]) -> dict[str, Any]:
    dataset = value.get("dataset") if isinstance(value.get("dataset"), dict) else value
    if isinstance(dataset.get("datasets"), list):
        first_dataset = next((item for item in dataset["datasets"] if isinstance(item, dict)), None)
        if first_dataset is not None:
            dataset = first_dataset
    data = dataset.get("data") if isinstance(dataset.get("data"), dict) else {}
    nested = data.get("dataset") if isinstance(data.get("dataset"), dict) else dataset
    fields = nested.get("fields") or dataset.get("fields") or []
    normalized_fields = []
    for item in fields if isinstance(fields, list) else []:
        if not isinstance(item, dict):
            continue
        normalized_fields.append(
            {
                "guid": str(item.get("guid") or item.get("id") or item.get("field_guid") or ""),
                "name": str(item.get("name") or item.get("title") or item.get("field_name") or ""),
                "source_expression": str(item.get("source_expression") or item.get("sourceExpression") or item.get("expression") or ""),
                "formula": str(item.get("formula") or item.get("calc_spec") or item.get("calculation") or ""),
                "aggregation": str(item.get("aggregation") or item.get("aggregationType") or item.get("default_aggregation") or ""),
                "grain": item.get("grain") or item.get("grouping_keys") or [],
            }
        )
    return {
        "dataset_id": str(
            dataset.get("dataset_id")
            or dataset.get("datasetId")
            or nested.get("dataset_id")
            or nested.get("datasetId")
            or dataset.get("id")
            or ""
        ),
        "source_table": str(dataset.get("source_table") or nested.get("source_table") or ""),
        "physical_grain": dataset.get("physical_grain") or nested.get("physical_grain") or [],
        "output_grain": dataset.get("output_grain") or nested.get("output_grain") or dataset.get("grain") or [],
        "fields": normalized_fields,
        "joins": dataset.get("joins") or nested.get("joins") or [],
    }


def _fanout_join_blockers(dataset: dict[str, Any], charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    joins = dataset.get("joins") if isinstance(dataset.get("joins"), list) else []
    fanout_joins = []
    for join in joins:
        if not isinstance(join, dict):
            continue
        cardinality = str(
            join.get("cardinality")
            or join.get("relationship")
            or join.get("join_cardinality")
            or join.get("type")
            or ""
        ).lower()
        if cardinality in {"one_to_many", "many_to_many", "1:n", "n:m", "one-to-many", "many-to-many"}:
            fanout_joins.append(join)
    if not fanout_joins:
        return []
    additive_fields = {
        field.get("name")
        for field in dataset["fields"]
        if _normalize_aggregation(field.get("aggregation")) in AGGREGATE_FUNCTIONS
    }
    chart_has_additive = any(
        _normalize_aggregation(slot.get("aggregation") or chart.get("aggregation")) in AGGREGATE_FUNCTIONS
        for chart in charts
        for slot in (chart.get("fields") or _chart_fields_from_payload(chart))
    )
    if not additive_fields and not chart_has_additive:
        return []
    return [
        _blocker(
            "fanout_join_reaggregation",
            "Dataset contains one-to-many or many-to-many joins with additive aggregation; "
            "require explicit dedupe or pre-aggregation before release.",
            dataset_id=dataset["dataset_id"],
            join_count=len(fanout_joins),
        )
    ]


def _normalize_charts(value: Any) -> list[dict[str, Any]]:
    charts = value if isinstance(value, list) else []
    normalized = []
    for item in charts:
        if not isinstance(item, dict):
            continue
        entry = item.get("entry") if isinstance(item.get("entry"), dict) else item
        normalized.append(
            {
                **item,
                "chart_id": str(
                    item.get("chart_id")
                    or item.get("chartId")
                    or item.get("entryId")
                    or entry.get("entryId")
                    or entry.get("chartId")
                    or item.get("id")
                    or ""
                ),
            }
        )
    return normalized


def _chart_fields_from_payload(chart: dict[str, Any]) -> list[dict[str, Any]]:
    fields = chart.get("fields") if isinstance(chart.get("fields"), list) else []
    data = chart.get("data") if isinstance(chart.get("data"), dict) else {}
    fields.extend(data.get("fields") if isinstance(data.get("fields"), list) else [])
    result = []
    for index, item in enumerate(fields):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "slot": str(item.get("slot") or item.get("role") or f"field_{index}"),
                "field_guid": str(item.get("field_guid") or item.get("guid") or item.get("datasetFieldId") or ""),
                "field_name": str(item.get("field_name") or item.get("name") or item.get("title") or ""),
                "aggregation": str(item.get("aggregation") or item.get("aggregationType") or ""),
            }
        )
    return result


def _extract_sql_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("sql", "query", "statement")) and isinstance(nested, str):
                found.append(nested)
            else:
                found.extend(_extract_sql_values(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(_extract_sql_values(item))
    return found


def _json_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _unique_files(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        result.append(path)
    return result


def _payload_has_dataset_fields(payload: dict[str, Any]) -> bool:
    dataset = _normalize_dataset(payload)
    return bool(dataset["fields"])


def _resolve_dataset_field(
    slot: dict[str, Any],
    fields_by_guid: dict[str, dict[str, Any]],
    fields_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    guid = str(slot.get("field_guid") or slot.get("guid") or "")
    name = str(slot.get("field_name") or slot.get("name") or "").lower()
    return fields_by_guid.get(guid) if guid else fields_by_name.get(name)


def _normalize_aggregation(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "")
    aliases = {"countd": "countdistinct", "none": "none", "": "none"}
    return aliases.get(text, text)


def _has_aggregate(expression: str) -> bool:
    tokens, _ = tokenize_sql(expression.replace("[", "").replace("]", ""))
    return any(item["function"] in AGGREGATE_FUNCTIONS for item in _function_calls(tokens))


def _unsafe_optimization_blockers(grain: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = []
    for blocker in grain.get("blockers") or []:
        rule = str(blocker.get("rule") or "")
        if rule in {"nested_aggregation", "distinct_over_preaggregated_grain", "ratio_reaggregation", "non_additive_reaggregation"}:
            affected = [blocker.get("chart_id")] if blocker.get("chart_id") else []
            blockers.append({**blocker, "status": "unsafe", "affected_charts": affected})
    return blockers


def _recommendation(
    strategy: str,
    affected_charts: list[str],
    evidence: str,
    row: dict[str, Any],
    *,
    proposed_grain: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "affected_charts": [chart for chart in affected_charts if chart],
        "status": "recommendation",
        "current_bottleneck_evidence": evidence,
        "proposed_grain": proposed_grain,
        "required_fields": [],
        "exact_vs_approximate": "exact",
        "selector_compatibility": "preserve aliases and field GUIDs",
        "date_scale_compatibility": "preserve date grain unless explicitly approved",
        "expected_improvement_confidence": confidence,
        "evidence_source": ",".join(row.get("evidence_source") or []) or "static_sql_graph",
        "parity_scenarios": ["same selector filters", "current and previous periods", "empty period", "known total rows"],
        "rollback_plan": "chart clone/repoint mapping; keep old dataset and dashboard revision until readback passes",
        "stop_conditions": [
            "metric parity mismatch",
            "field GUID loss",
            "selector alias break",
            "non-additive metric at unsafe grain",
        ],
    }


def _normalize_timings(value: dict[str, Any]) -> list[dict[str, Any]]:
    timings: list[dict[str, Any]] = []
    for source in ("api_observed", "browser_inspector", "query_engine", "static_estimate"):
        item = value.get(source)
        if not isinstance(item, dict):
            continue
        timings.append(
            {
                "source": source,
                "duration_ms": _int_or_none(item.get("duration_ms") or item.get("data_fetch_ms") or item.get("elapsed_ms")),
                "render_ms": _int_or_none(item.get("render_ms")),
                "evidence_hash": _sha256(stable_json_text(item)),
                "confidence": item.get("confidence") or ("high" if source != "static_estimate" else "low"),
            }
        )
    return timings


def _timing_sources(timings: list[dict[str, Any]]) -> list[str]:
    return [item["source"] for item in timings if item.get("duration_ms") is not None or item.get("render_ms") is not None]


def _performance_confidence(timings: list[dict[str, Any]], sql_report: dict[str, Any]) -> str:
    if any(item.get("source") == "browser_inspector" and item.get("render_ms") is not None for item in timings):
        return "high"
    if any(item.get("duration_ms") is not None for item in timings):
        return "medium"
    if sql_report:
        return "static_only"
    return "unknown"


def _needs_stage_isolation(sql_report: dict[str, Any], row: dict[str, Any]) -> bool:
    return row.get("cte_count", 0) >= 4 or row.get("joins", 0) >= 3 or any(
        issue.get("rule") == "broad_history_scan_before_key_reduction" for issue in sql_report.get("diagnostics", [])
    )


def _stage_isolation_plan(row: dict[str, Any], sql_report: dict[str, Any]) -> dict[str, Any]:
    ctes = [cte.get("name") for cte in sql_report.get("ctes") or []]
    return {
        "chart_id": row.get("chart_id"),
        "source_query_hash": row.get("source_query_hash"),
        "timeout_sec": 30,
        "read_only": True,
        "stages": [
            {
                "cte": cte,
                "probe": "bounded_count",
                "sql_policy": "wrap CTE chain through this stage and count rows with explicit timeout",
            }
            for cte in ctes
        ],
    }


def _chart_sql(chart: dict[str, Any]) -> str:
    return str(chart.get("source_sql") or chart.get("sql") or chart.get("query") or "")


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _grain_remediation_options(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not blockers:
        return []
    return [
        {
            "option": "row_level_field",
            "when": "formula must remain aggregatable at chart level",
            "automatic": False,
        },
        {
            "option": "additive_preaggregate",
            "when": "measure is additive and parity scenarios pass exactly",
            "automatic": False,
        },
        {
            "option": "separate_dataset",
            "when": "KPI/detail/sequence charts need incompatible grains",
            "automatic": False,
        },
        {
            "option": "materialized_layer_suggestion",
            "when": "measured broad CTE costs remain high after key reduction",
            "automatic": False,
        },
    ]


def write_sql_performance_artifact(project_root: str | Path, relative_name: str, payload: Any) -> dict[str, Any]:
    root = Path(project_root)
    target = root / ARTIFACT_DIR / relative_name
    target.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_response(payload)
    target.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(target), **serialized_metadata(sanitized)}


def _write_report(root: Path, name: str, text: str) -> str:
    target = root / ARTIFACT_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)


def _write_csv(root: Path, name: str, rows: list[dict[str, Any]]) -> str:
    target = root / ARTIFACT_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "chart_id",
        "dataset_id",
        "visible_tab",
        "source_query_hash",
        "cte_count",
        "joins",
        "windows",
        "aggregates",
        "field_slots",
        "timing_status",
        "confidence",
    ]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return str(target)


def render_sql_parser_report(reports: list[dict[str, Any]]) -> str:
    lines = ["# SQL Parser Report", "", "| Case | Status | Hash | Error Findings |", "| --- | --- | --- | --- |"]
    for report in reports:
        errors = [item["rule"] for item in report.get("diagnostics") or [] if item.get("severity") == "error"]
        lines.append(
            f"| {report.get('source_name')} | {report.get('parse_status')} | `{str(report.get('source_hash'))[:12]}` | "
            f"{', '.join(errors) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def render_aggregation_report(report: dict[str, Any]) -> str:
    lines = ["# Aggregation Grain Report", "", f"- Dataset: `{report.get('dataset_id')}`", f"- OK: `{report.get('ok')}`", ""]
    for blocker in report.get("blockers") or []:
        lines.append(f"- `{blocker.get('rule')}`: {blocker.get('message')}")
    return "\n".join(lines) + "\n"


def render_s2t_report(report: dict[str, Any]) -> str:
    lines = ["# S2T Impact Report", "", f"- OK: `{report.get('ok')}`", f"- Edges: `{len(report.get('edges') or [])}`", ""]
    for finding in report.get("findings") or []:
        lines.append(f"- `{finding.get('rule')}`: {finding.get('message')}")
    return "\n".join(lines) + "\n"


def render_optimization_report(report: dict[str, Any]) -> str:
    lines = ["# Optimization Plan", "", f"- Automatic mutation: `{report.get('automatic_mutation')}`", ""]
    for item in report.get("recommendations") or []:
        charts = ", ".join(item.get("affected_charts") or [])
        lines.append(
            f"- `{item.get('strategy')}` for `{charts or 'n/a'}`: confidence `{item.get('expected_improvement_confidence')}`, "
            f"evidence `{item.get('evidence_source')}`"
        )
    return "\n".join(lines) + "\n"


def render_live_benchmark_report(report: dict[str, Any]) -> str:
    coverage = report.get("coverage") or {}
    return (
        "# Live Benchmark\n\n"
        f"- Chart count: `{coverage.get('chart_count', 0)}`\n"
        f"- Measured charts: `{coverage.get('measured_chart_count', 0)}`\n"
        f"- Timing unavailable: `{coverage.get('timing_unavailable_count', 0)}`\n"
        "- Timing sources are separated into API-observed, browser Inspector, query-engine, and static estimates.\n"
        "- Browser Inspector timing requires an imported evidence export; no timing is fabricated.\n"
    )


def render_remaining_gaps_report(report: dict[str, Any]) -> str:
    unavailable = [
        row.get("chart_id") for row in report.get("chart_performance") or [] if row.get("timing_status") == "timing_unavailable"
    ]
    lines = ["# Remaining Performance Gaps", ""]
    if unavailable:
        lines.append(
            "- Browser Inspector or query-engine timing evidence is missing for: "
            + ", ".join(str(item) for item in unavailable)
        )
    else:
        lines.append("- No missing timing evidence in supplied payload.")
    return "\n".join(lines) + "\n"


def _bounded_result_summary(result: dict[str, Any], *, max_items: int) -> dict[str, Any]:
    if "diagnostics" in result:
        return {
            "ok": result.get("ok"),
            "parse_status": result.get("parse_status"),
            "source_hash": result.get("source_hash"),
            "diagnostics": [
                {key: item.get(key) for key in ("rule", "severity", "line", "column", "cte", "identifier", "message")}
                for item in (result.get("diagnostics") or [])[:max_items]
            ],
        }
    if "chart_performance" in result:
        return {
            "ok": result.get("ok"),
            "coverage": result.get("coverage"),
            "rows": result.get("chart_performance", [])[:max_items],
        }
    if "recommendations" in result:
        return {
            "ok": result.get("ok"),
            "recommendations": result.get("recommendations", [])[:max_items],
            "blocked": result.get("blocked", []),
        }
    if "blockers" in result:
        return {"ok": result.get("ok"), "blockers": result.get("blockers", [])[:max_items]}
    if "findings" in result:
        return {"ok": result.get("ok"), "findings": result.get("findings", [])[:max_items]}
    return {"ok": result.get("ok"), "keys": sorted(result)[:max_items]}


def _lexical_findings(issues: list[dict[str, Any]], sql: str, source: str) -> list[dict[str, Any]]:
    return [
        _finding(
            "parse_partial",
            "error",
            issue["message"],
            offset=issue["offset"],
            sql=sql,
            source=source,
            remediation="Fix the unterminated token or provide an Inspector/export artifact for unsupported syntax.",
        )
        for issue in issues
    ]


def _stale_field_findings(parsed: dict[str, Any], contract: dict[str, Any], sql: str, source: str) -> list[dict[str, Any]]:
    columns = _contract_columns(contract)
    if not columns:
        return []
    findings = []
    for lineage in parsed.get("source_lineage") or []:
        table = str(lineage.get("source") or "")
        allowed = columns.get(table.lower())
        if not allowed:
            continue
        for ref in parsed.get("projections") or []:
            for identifier in ref.get("lineage_identifiers") or []:
                parts = identifier.split(".")
                column = parts[-1].lower()
                if column not in allowed and (len(parts) == 1 or parts[0].lower() in {lineage.get("alias", "").lower(), table.lower()}):
                    offset = int(ref.get("offset") or 0)
                    findings.append(
                        _finding(
                            "stale_s2t_field",
                            "error",
                            f"Source field `{column}` is absent from the supplied S2T/schema contract for `{table}`.",
                            offset=offset,
                            sql=sql,
                            source=source,
                            cte=ref.get("scope", ""),
                            identifier=identifier,
                            remediation="Refresh the S2T contract or preserve the chart-facing alias while replacing the physical field.",
                        )
                    )
                    findings.append(
                        _finding(
                            "unknown_identifier",
                            "error",
                            (
                                f"ClickHouse Code 47 risk: `{identifier}` is not available in `{table}` "
                                "according to the supplied schema contract."
                            ),
                            offset=offset,
                            sql=sql,
                            source=source,
                            cte=ref.get("scope", ""),
                            identifier=identifier,
                            remediation=(
                                "Resolve the physical column from the current source schema, then keep a "
                                "stable dataset/chart alias for downstream compatibility."
                            ),
                        )
                    )
    return findings


def _broad_scan_findings(parsed: dict[str, Any], sql: str, source: str) -> list[dict[str, Any]]:
    findings = []
    for lineage in parsed.get("source_lineage") or []:
        name = str(lineage.get("source") or "").lower()
        scope = str(lineage.get("scope") or "")
        if not any(term in name for term in ("history", "status", "state", "event_log", "entity_link", "audit_log")):
            continue
        filters = [item for item in parsed.get("filter_pushdown") or [] if item.get("scope") == scope]
        if not filters:
            findings.append(
                _finding(
                    "broad_history_scan_before_key_reduction",
                    "warning",
                    f"CTE `{scope}` reads broad history/link source `{lineage.get('source')}` without an early key filter.",
                    offset=int(lineage.get("offset") or 0),
                    sql=sql,
                    source=source,
                    cte=scope,
                    remediation="Isolate scope/entity keys first, then join the history/link table with an explicit timeout stage probe.",
                )
            )
    return findings


def _select_star_findings(parsed: dict[str, Any], critical_ctes: set[str], sql: str, source: str) -> list[dict[str, Any]]:
    findings = []
    for projection in parsed.get("projections") or []:
        if projection.get("expression_excerpt") != "*":
            continue
        scope = str(projection.get("scope") or "")
        if critical_ctes and scope not in critical_ctes:
            continue
        findings.append(
            _finding(
                "select_star_critical_cte",
                "warning",
                f"Critical CTE `{scope}` uses SELECT * and can keep unused columns in wide queries.",
                offset=int(projection.get("offset") or 0),
                sql=sql,
                source=source,
                cte=scope,
                remediation="Project only fields required by downstream chart slots and parity scenarios.",
            )
        )
    return findings


def _qualified_references(tokens: list[Token]) -> list[dict[str, Any]]:
    refs = []
    index = 0
    while index + 2 < len(tokens):
        if tokens[index].kind in {"word", "identifier"} and tokens[index + 1].value == "." and tokens[index + 2].kind in {
            "word",
            "identifier",
        }:
            parts = [_clean_identifier(tokens[index].value), _clean_identifier(tokens[index + 2].value)]
            cursor = index + 3
            while cursor + 1 < len(tokens) and tokens[cursor].value == "." and tokens[cursor + 1].kind in {"word", "identifier"}:
                parts.append(_clean_identifier(tokens[cursor + 1].value))
                cursor += 2
            refs.append({"parts": parts, "offset": tokens[index].start})
            index = cursor
            continue
        index += 1
    return refs


def _function_calls(tokens: list[Token]) -> list[dict[str, Any]]:
    calls = []
    for index, token in enumerate(tokens[:-1]):
        if token.kind in {"word", "identifier"} and tokens[index + 1].value == "(":
            function = _clean_identifier(token.value).lower()
            if function not in SQL_KEYWORDS:
                calls.append({"function": function, "offset": token.start})
        if token.lower == "over":
            calls.append({"function": "over", "offset": token.start})
    return calls


def _filter_pushdown(tokens: list[Token], scope: str) -> list[dict[str, Any]]:
    refs = _qualified_references(tokens)
    unqualified = [
        _clean_identifier(token.value)
        for token in tokens
        if token.kind in {"word", "identifier"} and token.lower not in SQL_KEYWORDS
    ]
    fields = sorted({*(ref["parts"][-1] for ref in refs), *unqualified})
    return [{"scope": scope, "fields": fields, "hash": _sha256(" ".join(token.value for token in tokens))}] if fields else []


def _grain_candidates(tokens: list[Token], function_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if tokens:
        parts = [".".join(ref["parts"]) for ref in _qualified_references(tokens)]
        parts.extend(
            _clean_identifier(token.value)
            for token in tokens
            if token.kind in {"word", "identifier"} and token.lower not in SQL_KEYWORDS
        )
        return [{"grain": sorted(set(parts)), "source": "group_by"}]
    if any(item["function"] in AGGREGATE_FUNCTIONS for item in function_calls):
        return [{"grain": [], "source": "global_aggregate"}]
    return [{"grain": ["row"], "source": "row_level"}]


def _join_hint(tokens: list[Token], join_type: str, scope: str) -> dict[str, Any]:
    refs = _qualified_references(tokens)
    keys = []
    for index, token in enumerate(tokens):
        if token.value == "=" and index > 0 and index + 1 < len(tokens):
            left = _near_identifier(tokens, index - 1, reverse=True)
            right = _near_identifier(tokens, index + 1, reverse=False)
            if left and right:
                keys.append({"left": left, "right": right})
    return {
        "scope": scope,
        "join_type": join_type,
        "keys": keys,
        "referenced_aliases": sorted({ref["parts"][0] for ref in refs}),
        "cardinality_hint": "unknown" if keys else "cross_or_unkeyed",
    }


def _near_identifier(tokens: list[Token], index: int, *, reverse: bool) -> str:
    parts = []
    step = -1 if reverse else 1
    cursor = index
    while 0 <= cursor < len(tokens) and len(parts) < 3:
        token = tokens[cursor]
        if token.kind in {"word", "identifier"}:
            parts.append(_clean_identifier(token.value))
        elif token.value != ".":
            break
        cursor += step
    if reverse:
        parts = list(reversed(parts))
    return ".".join(parts)


def _formula_identifiers(expression: str) -> list[str]:
    return sorted(
        {
            item.strip("[]").lower()
            for item in re.findall(r"\[([A-Za-z_][A-Za-z0-9_]*)\]|\b([A-Za-z_][A-Za-z0-9_]*)\b", expression)
            for item in item
            if item and item.lower() not in SQL_KEYWORDS and item.lower() not in AGGREGATE_FUNCTIONS
        }
    )


def _contract_columns(contract: dict[str, Any]) -> dict[str, set[str]]:
    tables = contract.get("tables") if isinstance(contract.get("tables"), dict) else {}
    if not tables and isinstance(contract.get("fields"), list):
        tables = {"": contract["fields"]}
    return {str(table).lower(): {str(col).lower() for col in cols} for table, cols in tables.items() if isinstance(cols, list)}


def _matching_contract_table(identifier: str, contract: dict[str, set[str]]) -> str:
    matches = [table for table, columns in contract.items() if identifier.lower() in columns]
    return matches[0] if matches else ""


def _contract_has_column(contract: dict[str, set[str]], table: str, identifier: str) -> bool:
    if not contract:
        return True
    if table and table.lower() in contract:
        return identifier.lower() in contract[table.lower()]
    return any(identifier.lower() in columns for columns in contract.values())


def _referenced_ctes(tokens: list[Token], cte_names: set[str]) -> set[str]:
    return {token.value for token in tokens if token.lower in {name.lower() for name in cte_names}}


def _split_top_level(tokens: list[Token], separator: str) -> list[list[Token]]:
    spans: list[list[Token]] = []
    start = 0
    depth = 0
    for index, token in enumerate(tokens):
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth = max(0, depth - 1)
        elif token.value == separator and depth == 0:
            spans.append(tokens[start:index])
            start = index + 1
    if start < len(tokens):
        spans.append(tokens[start:])
    return [span for span in spans if span]


def _top_level_keyword(tokens: list[Token], keyword: str, start: int) -> int | None:
    depth = 0
    for index in range(max(start, 0), len(tokens)):
        token = tokens[index]
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.lower == keyword:
            return index
    return None


def _next_join_index(tokens: list[Token], start: int) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.lower in {"join", "left", "right", "inner", "full", "cross"}:
            return index
    return len(tokens)


def _matching_paren(tokens: list[Token], open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(tokens)):
        if tokens[index].value == "(":
            depth += 1
        elif tokens[index].value == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _alias_after(tokens: list[Token], index: int) -> str:
    if index >= len(tokens):
        return ""
    if tokens[index].lower == "as" and index + 1 < len(tokens):
        return _clean_identifier(tokens[index + 1].value)
    if tokens[index].kind in {"word", "identifier"} and tokens[index].lower not in SQL_KEYWORDS:
        return _clean_identifier(tokens[index].value)
    return ""


def _looks_like_catalog_reference(ref: dict[str, Any], aliases: list[dict[str, str]]) -> bool:
    if len(ref["parts"]) >= 3:
        return True
    sources = {str(item.get("source") or "").split(".")[0].lower() for item in aliases}
    return ref["parts"][0].lower() in sources


def _quoted_end(sql: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(sql):
        if sql[index] == "\\":
            index += 2
            continue
        if sql[index] == quote:
            return index + 1
        index += 1
    return -1


def _tokens_text(tokens: list[Token], sql: str) -> str:
    if not tokens:
        return ""
    return sql[tokens[0].start : tokens[-1].end].strip()


def _clean_identifier(value: str) -> str:
    return value.strip("`\"")


def _finding(
    rule: str,
    severity: str,
    message: str,
    *,
    offset: int,
    sql: str,
    source: str,
    remediation: str,
    cte: str = "",
    identifier: str = "",
) -> dict[str, Any]:
    line, column = _line_col(sql, offset)
    return {
        "rule": rule,
        "severity": severity,
        "source_name": source,
        "line": line,
        "column": column,
        "offset": offset,
        "cte": cte,
        "identifier": identifier,
        "message": message,
        "remediation": remediation,
        "excerpt": _bounded(_excerpt(sql, offset), 240),
    }


def _graph_finding(rule: str, severity: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"rule": rule, "severity": severity, "message": message, **extra}


def _blocker(rule: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"rule": rule, "severity": "error", "message": message, **extra}


def _line_col(text: str, offset: int) -> tuple[int, int]:
    prefix = text[: max(offset, 0)]
    return prefix.count("\n") + 1, len(prefix.rsplit("\n", 1)[-1]) + 1


def _excerpt(text: str, offset: int, radius: int = 80) -> str:
    start = max(0, offset - radius)
    end = min(len(text), offset + radius)
    return " ".join(text[start:end].split())


def _bounded(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
