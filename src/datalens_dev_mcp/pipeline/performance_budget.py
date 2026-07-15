from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PerformanceFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PerformanceBudgetResult:
    ok: bool
    publish_allowed: bool
    decision: str
    checked_tab_count: int
    checked_widget_count: int
    findings: list[PerformanceFinding] = field(default_factory=list)
    schema_version: str = "2026-07-01.performance_budget_policy_v2"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


DEFAULT_BUDGETS = {
    "preferred_initial_tab_load_sec": 5,
    "dashboard_first_useful_paint_seconds": 5,
    "tab_warning_seconds": 10,
    "tab_publish_block_seconds": 15,
    "observed_hard_fail_seconds": 20,
    "max_heavy_queries_per_tab": 6,
    "max_widgets_per_tab": 12,
    "max_generated_js_bytes": 200_000,
    "max_embedded_data_bytes": 120_000,
}

EDITOR_SOURCE_LIMITS = {
    "max_single_source_bytes": 50 * 1024 * 1024,
    "max_total_source_bytes": 100 * 1024 * 1024,
    "max_single_source_time_ms": 95_000,
    "max_total_source_time_ms": 95_000,
    "high_fanout_ratio": 10_000,
}

DELTA_V7_EDITOR_SOURCE_BUDGET_SCHEMA_VERSION = "datalens.delta_v7.editor_source_budget_evidence.v1"


def assess_performance_budget(payload: dict[str, Any], *, budgets: dict[str, Any] | None = None) -> PerformanceBudgetResult:
    budget = {**DEFAULT_BUDGETS, **(budgets or {})}
    findings: list[PerformanceFinding] = []
    tabs = _tabs(payload)
    widgets = _widgets(payload, tabs=tabs)
    if not tabs and widgets:
        tabs = [{"id": "default", "widgets": widgets}]
    for tab_index, tab in enumerate(tabs):
        tab_widgets = _widgets(tab)
        if len(tab_widgets) > int(budget["max_widgets_per_tab"]):
            findings.append(
                _finding(
                    "widget_count_per_tab_budget",
                    f"$.tabs[{tab_index}].widgets",
                    f"tab has {len(tab_widgets)} widgets, above {budget['max_widgets_per_tab']}",
                    severity="warning",
                )
            )
        timing = _tab_seconds(tab)
        if timing >= float(budget["observed_hard_fail_seconds"]):
            findings.append(
                _finding(
                    "observed_20_second_tab",
                    f"$.tabs[{tab_index}].timing",
                    f"tab observed/estimated at {timing:.2f}s, which is a hard publish fail",
                )
            )
        elif timing >= float(budget["tab_publish_block_seconds"]):
            findings.append(
                _finding(
                    "slow_tab_blocks_publish",
                    f"$.tabs[{tab_index}].timing",
                    f"tab observed/estimated at {timing:.2f}s, above publish block budget",
                )
            )
        elif timing > float(budget["tab_warning_seconds"]):
            findings.append(
                _finding(
                    "slow_tab_warning",
                    f"$.tabs[{tab_index}].timing",
                    f"tab observed/estimated at {timing:.2f}s, above warning budget",
                    severity="warning",
                )
            )
    sql_values = _sql_values(payload)
    findings.extend(_sql_findings(sql_values))
    heavy_duplicates = _duplicated_heavy_sql(sql_values)
    for fingerprint, count in heavy_duplicates.items():
        findings.append(
            _finding(
                "duplicated_heavy_source_without_cache",
                "$.sources",
                f"heavy source SQL fingerprint {fingerprint[:12]} is duplicated {count} times",
            )
        )
    js_bytes = _generated_js_bytes(payload)
    if js_bytes > int(budget["max_generated_js_bytes"]):
        findings.append(
            _finding("generated_js_size", "$.generated_js", f"generated JS size {js_bytes} exceeds budget")
        )
    embedded_bytes = _embedded_data_bytes(payload)
    if embedded_bytes > int(budget["max_embedded_data_bytes"]) and not payload.get("explicit_static_embedded_approval"):
        findings.append(
            _finding(
                "large_embedded_dataset_without_explicit_static_mode",
                "$.embedded_data",
                f"embedded data size {embedded_bytes} exceeds budget without explicit static approval",
            )
        )
    errors = [finding for finding in findings if finding.severity == "error"]
    decision = "block" if errors else "warning" if findings else "pass"
    return PerformanceBudgetResult(
        ok=not errors,
        publish_allowed=not errors,
        decision=decision,
        checked_tab_count=len(tabs),
        checked_widget_count=len(widgets),
        findings=findings,
    )


def _tabs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("tabs") or ((payload.get("dashboard") or {}).get("tabs") if isinstance(payload.get("dashboard"), dict) else [])
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _widgets(payload: dict[str, Any], *, tabs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if tabs is not None:
        result: list[dict[str, Any]] = []
        for tab in tabs:
            result.extend(_widgets(tab))
        return result
    raw = payload.get("widgets") or payload.get("charts") or payload.get("items") or []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _tab_seconds(tab: dict[str, Any]) -> float:
    for key in ("observed_seconds", "estimated_seconds", "render_seconds", "duration_seconds"):
        value = tab.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    timings = tab.get("timings") if isinstance(tab.get("timings"), dict) else {}
    for key in ("browser_ms", "duration_ms", "render_ms"):
        value = timings.get(key)
        if isinstance(value, (int, float)):
            return float(value) / 1000
    return 0.0


def _sql_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"sql", "query", "source_query"} and isinstance(item, str):
                values.append(item)
            else:
                values.extend(_sql_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_sql_values(item))
    return values


def _sql_findings(sql_values: list[str]) -> list[PerformanceFinding]:
    findings: list[PerformanceFinding] = []
    for index, sql in enumerate(sql_values):
        lowered = re.sub(r"\s+", " ", sql.lower())
        if "select *" in lowered and " limit " not in lowered:
            findings.append(_finding("unbounded_detail_query", f"$.sql[{index}]", "SELECT * without LIMIT is blocked"))
        if "cross join" in lowered and " total" in lowered:
            findings.append(
                _finding(
                    "cross_join_totals_when_window_total_possible",
                    f"$.sql[{index}]",
                    "CROSS JOIN totals pattern should use window totals or pre-aggregation",
                )
            )
        if re.search(r"\bjoin\b.+\bwhere\b.+\bor\b", lowered):
            findings.append(_finding("broad_or_after_join", f"$.sql[{index}]", "broad OR after JOIN is blocked"))
    return findings


def _duplicated_heavy_sql(sql_values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sql in sql_values:
        if not _heavy_sql(sql):
            continue
        digest = hashlib.sha256(re.sub(r"\s+", " ", sql.strip()).encode("utf-8")).hexdigest()
        counts[digest] = counts.get(digest, 0) + 1
    return {digest: count for digest, count in counts.items() if count > 1}


def _heavy_sql(sql: str) -> bool:
    lowered = sql.lower()
    return len(sql) > 500 or lowered.count(" join ") >= 2 or lowered.count(" with ") >= 1 or lowered.count("select") >= 3


def _generated_js_bytes(value: Any) -> int:
    total = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).endswith(".js") or str(key).lower() in {"prepare", "sources", "controls", "generated_js"}:
                if isinstance(item, str):
                    total += len(item.encode("utf-8"))
            total += _generated_js_bytes(item)
    elif isinstance(value, list):
        for item in value:
            total += _generated_js_bytes(item)
    return total


def _embedded_data_bytes(value: Any) -> int:
    if isinstance(value, dict):
        total = 0
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"embedded_data", "static_rows", "rows"} and isinstance(item, list):
                total += len(str(item).encode("utf-8"))
            total += _embedded_data_bytes(item)
        return total
    if isinstance(value, list):
        return sum(_embedded_data_bytes(item) for item in value)
    return 0


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> PerformanceFinding:
    return PerformanceFinding(rule=rule, severity=severity, path=path, message=message)


def build_editor_source_budget_evidence(
    sources: list[dict[str, Any]],
    *,
    dashboard_id: str = "",
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_limits = {**EDITOR_SOURCE_LIMITS, **(limits or {})}
    source_rows: list[dict[str, Any]] = []
    total_bytes = sum(int(item.get("estimated_single_source_bytes") or item.get("estimated_bytes") or 0) for item in sources)
    total_time = sum(int(item.get("estimated_source_time_ms") or item.get("estimated_time_ms") or 0) for item in sources)
    for item in sources:
        row = _source_budget_row(item, total_bytes=total_bytes, total_time=total_time, limits=active_limits)
        source_rows.append(row)
    return {
        "schema_version": "datalens.source-performance-budget.v1",
        "dashboard_id": dashboard_id,
        "limits": active_limits,
        "sources": source_rows,
        "summary": {
            "source_count": len(source_rows),
            "failed_source_count": sum(1 for row in source_rows if row["source_budget_status"] == "fail"),
            "unknown_source_count": sum(1 for row in source_rows if row["source_budget_status"] == "unknown"),
            "warn_source_count": sum(1 for row in source_rows if row["source_budget_status"] == "warn"),
        },
    }


def extract_editor_source_budget_evidence_v7(
    payload: dict[str, Any],
    *,
    supplied_evidence: dict[str, Any] | list[dict[str, Any]] | None = None,
    dashboard_id: str = "",
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = _extract_editor_sources(payload)
    evidence_rows = _evidence_rows_by_key(supplied_evidence)
    enriched = []
    for source in sources:
        key = str(source.get("source_key") or "")
        supplied = evidence_rows.get(key, {})
        merged = {**source, **supplied}
        enriched.append(merged)
    normalized = normalize_editor_source_budget_evidence_v7(
        build_editor_source_budget_evidence(enriched, dashboard_id=dashboard_id, limits=limits).get("sources", [])
    )
    return {
        "schema_version": "datalens.delta_v7.editor_source_budget_collection.v1",
        "dashboard_id": dashboard_id,
        "sources": normalized,
        "blocked_reasons": [
            f"{row.get('entry_id') or '<unknown>'}:{row.get('source_key') or '<unknown>'}:{row.get('decision')}"
            for row in normalized
            if row.get("decision") in {"block", "insufficient_evidence"}
        ],
    }


def normalize_editor_source_budget_evidence_v7(
    evidence: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]]
    if isinstance(evidence, dict):
        raw = evidence.get("sources") if isinstance(evidence.get("sources"), list) else [evidence]
        rows = [row for row in raw if isinstance(row, dict)]
    elif isinstance(evidence, list):
        rows = [row for row in evidence if isinstance(row, dict)]
    else:
        rows = []
    return [_delta_v7_source_budget_row(row) for row in rows]


def _extract_editor_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _collect_editor_sources(payload, rows, path="$", entry_id=str(payload.get("entryId") or payload.get("chartId") or ""))
    return rows


def _collect_editor_sources(value: Any, rows: list[dict[str, Any]], *, path: str, entry_id: str) -> None:
    if isinstance(value, dict):
        local_entry_id = str(value.get("entryId") or value.get("chartId") or entry_id or "")
        for key, item in value.items():
            child_path = f"{path}.{key}"
            lowered = str(key).lower()
            if lowered in {"sources", "source", "external_controls", "dashboard_controls", "controls"}:
                rows.extend(_sources_from_container(item, path=child_path, entry_id=local_entry_id, default_consumer=lowered))
                continue
            elif lowered in {"sql", "query", "source_query"} and isinstance(item, str):
                rows.append(
                    {
                        "entry_id": local_entry_id,
                        "path": child_path,
                        "source_key": _source_key_from_path(child_path),
                        "consumer_type": "chart",
                        "sql": item,
                    }
                )
            _collect_editor_sources(item, rows, path=child_path, entry_id=local_entry_id)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_editor_sources(item, rows, path=f"{path}[{index}]", entry_id=entry_id)


def _sources_from_container(value: Any, *, path: str, entry_id: str, default_consumer: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            source_path = f"{path}.{key}"
            if isinstance(item, dict):
                rows.append(
                    _source_from_mapping(
                        item,
                        entry_id=entry_id,
                        path=source_path,
                        source_key=str(key),
                        default_consumer=default_consumer,
                    )
                )
            elif isinstance(item, str) and _looks_like_sql(item):
                rows.append(
                    {
                        "entry_id": entry_id,
                        "path": source_path,
                        "source_key": str(key),
                        "consumer_type": _consumer_type(default_consumer),
                        "sql": item,
                    }
                )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            source_path = f"{path}[{index}]"
            if isinstance(item, dict):
                rows.append(
                    _source_from_mapping(
                        item,
                        entry_id=entry_id,
                        path=source_path,
                        source_key=str(item.get("source_key") or item.get("name") or item.get("key") or index),
                        default_consumer=default_consumer,
                    )
                )
            elif isinstance(item, str) and _looks_like_sql(item):
                rows.append(
                    {
                        "entry_id": entry_id,
                        "path": source_path,
                        "source_key": str(index),
                        "consumer_type": _consumer_type(default_consumer),
                        "sql": item,
                    }
                )
    elif isinstance(value, str) and _looks_like_sql(value):
        rows.append(
            {
                "entry_id": entry_id,
                "path": path,
                "source_key": _source_key_from_path(path),
                "consumer_type": _consumer_type(default_consumer),
                "sql": value,
            }
        )
    return rows


def _source_from_mapping(
    value: dict[str, Any],
    *,
    entry_id: str,
    path: str,
    source_key: str,
    default_consumer: str,
) -> dict[str, Any]:
    sql = str(value.get("sql") or value.get("query") or value.get("source_query") or "")
    return {
        **value,
        "entry_id": str(value.get("entry_id") or value.get("entryId") or entry_id),
        "path": str(value.get("path") or path),
        "source_key": str(value.get("source_key") or value.get("key") or value.get("name") or source_key),
        "consumer_type": str(value.get("consumer_type") or _consumer_type(default_consumer)),
        "sql": sql,
    }


def _delta_v7_source_budget_row(row: dict[str, Any]) -> dict[str, Any]:
    sql = str(row.get("sql") or row.get("query") or row.get("source_query") or "")
    legacy_decision = str(row.get("source_budget_status") or row.get("decision") or "").strip().lower()
    if legacy_decision in {"fail", "block", "blocked"}:
        decision = "block"
    elif legacy_decision == "unknown":
        decision = "insufficient_evidence"
    elif legacy_decision in {"warn", "warning"}:
        decision = "warn"
    elif legacy_decision in {"pass", "ok"}:
        decision = "pass"
    else:
        decision = "insufficient_evidence" if _is_selector_or_large_table_source(row) else "pass"
    reasons = [str(item) for item in row.get("blocked_reasons") or row.get("reasons") or [] if str(item)]
    if decision == "insufficient_evidence" and not reasons:
        reasons.append("source_budget_evidence_required")
    physical_rows = _optional_int(row.get("physical_rows_before", row.get("estimated_physical_rows")))
    output_rows = _optional_int(row.get("business_grain_rows_after", row.get("estimated_output_rows")))
    fanout = _fanout_ratio(physical_rows, output_rows)
    has_filter = bool(row.get("has_sql_side_filter", row.get("bounded_in_sql", _bounded_in_sql(row))))
    has_dedupe = bool(
        row.get("has_business_grain_dedupe", row.get("deduped_to_business_grain", _deduped_to_business_grain(row)))
    )
    if decision == "insufficient_evidence" and physical_rows is not None and output_rows is not None and has_filter and has_dedupe:
        decision = "warn" if fanout and fanout >= float(EDITOR_SOURCE_LIMITS["high_fanout_ratio"]) else "pass"
        reasons = []
    return {
        "schema_version": DELTA_V7_EDITOR_SOURCE_BUDGET_SCHEMA_VERSION,
        "entry_id": str(row.get("entry_id") or row.get("entryId") or ""),
        "source_key": str(row.get("source_key") or ""),
        "consumer_type": str(row.get("consumer_type") or row.get("used_by") or ""),
        "physical_tables": _physical_tables(row, sql),
        "selector_params_used": [str(item) for item in row.get("selector_params_used") or row.get("selector_params") or []],
        "default_window_policy": row.get("default_window") or row.get("default_window_policy") or {},
        "sql_hash": hashlib.sha256(sql.encode("utf-8")).hexdigest() if sql else str(row.get("sql_hash") or ""),
        "sql_preview": re.sub(r"\s+", " ", sql).strip()[:500],
        "has_sql_side_filter": has_filter,
        "has_business_grain_dedupe": has_dedupe,
        "estimated_physical_rows": physical_rows,
        "estimated_output_rows": output_rows,
        "fanout_ratio": fanout,
        "timeout_or_502_evidence": [str(path) for path in row.get("timeout_evidence_paths") or row.get("timeout_or_502_evidence") or []],
        "decision": decision,
        "reasons": reasons,
    }


def _evidence_rows_by_key(evidence: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if isinstance(evidence, dict):
        raw = evidence.get("sources") if isinstance(evidence.get("sources"), list) else [evidence]
        rows = [row for row in raw if isinstance(row, dict)]
    elif isinstance(evidence, list):
        rows = [row for row in evidence if isinstance(row, dict)]
    else:
        rows = []
    return {str(row.get("source_key") or ""): row for row in rows if row.get("source_key")}


def _physical_tables(row: dict[str, Any], sql: str) -> list[str]:
    explicit = row.get("physical_tables") or row.get("tables") or row.get("table")
    values: list[str] = []
    if isinstance(explicit, list):
        values.extend(str(item) for item in explicit if str(item))
    elif explicit:
        values.append(str(explicit))
    for match in re.finditer(r"\b(?:from|join)\s+([a-zA-Z0-9_.]+)", sql, flags=re.IGNORECASE):
        table = match.group(1)
        if table not in values:
            values.append(table)
    return values


def _consumer_type(value: str) -> str:
    lowered = str(value).lower()
    if "control" in lowered:
        return "control"
    if "selector" in lowered:
        return "selector"
    return "chart"


def _source_key_from_path(path: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", path).strip("_")
    return cleaned or "source"


def _looks_like_sql(value: str) -> bool:
    lowered = value.lower()
    return "select " in lowered and (" from " in lowered or "\nfrom " in lowered)


def _source_budget_row(
    item: dict[str, Any],
    *,
    total_bytes: int,
    total_time: int,
    limits: dict[str, Any],
) -> dict[str, Any]:
    source_bytes = _optional_int(item.get("estimated_single_source_bytes", item.get("estimated_bytes")))
    source_time = _optional_int(item.get("estimated_source_time_ms", item.get("estimated_time_ms")))
    physical_rows = _optional_int(item.get("physical_rows_before"))
    business_rows = _optional_int(item.get("business_grain_rows_after"))
    fanout_ratio = _fanout_ratio(physical_rows, business_rows)
    selector_source = _is_selector_or_large_table_source(item)
    bounded_in_sql = _bounded_in_sql(item)
    deduped_to_business_grain = _deduped_to_business_grain(item)
    blocked: list[str] = []
    warnings: list[str] = []
    if source_bytes is not None and source_bytes > int(limits["max_single_source_bytes"]):
        blocked.append("single_source_50mb_limit_exceeded")
    if total_bytes > int(limits["max_total_source_bytes"]):
        blocked.append("total_source_100mb_limit_exceeded")
    if source_time is not None and source_time > int(limits["max_single_source_time_ms"]):
        blocked.append("single_source_95s_limit_exceeded")
    if total_time > int(limits["max_total_source_time_ms"]):
        blocked.append("total_source_95s_limit_exceeded")
    if fanout_ratio is not None and fanout_ratio >= float(limits["high_fanout_ratio"]):
        warnings.append("high_fanout_candidate")
        if selector_source and not bounded_in_sql:
            blocked.append("high_fanout_selector_requires_sql_filter_pushdown")
        if selector_source and not deduped_to_business_grain:
            blocked.append("high_fanout_selector_requires_business_grain_dedupe")
    if selector_source and (physical_rows is None or business_rows is None):
        blocked.append("selector_source_budget_evidence_required")
    if blocked:
        status = "fail"
    elif source_bytes is None and source_time is None:
        status = "unknown"
    elif warnings:
        status = "warn"
    else:
        status = "pass"
    return {
        "schema_version": "datalens.editor-source-budget.v1",
        "entry_id": str(item.get("entry_id") or item.get("entryId") or ""),
        "path": str(item.get("path") or ""),
        "source_key": str(item.get("source_key") or ""),
        "table": str(item.get("table") or ""),
        "source_count": int(item.get("source_count") or 1),
        "default_window": item.get("default_window") or {},
        "consumer_type": str(item.get("consumer_type") or item.get("used_by") or ""),
        "bounded_in_sql": bounded_in_sql,
        "deduped_to_business_grain": deduped_to_business_grain,
        "physical_rows_before": physical_rows,
        "business_grain_rows_after": business_rows,
        "fanout_ratio": fanout_ratio,
        "estimated_single_source_bytes": source_bytes,
        "estimated_total_bytes": total_bytes or None,
        "estimated_source_time_ms": source_time,
        "estimated_total_time_ms": total_time or None,
        "risk_level": "high" if blocked else "medium" if warnings else "unknown" if status == "unknown" else "low",
        "source_budget_status": status,
        "blocked_reasons": blocked,
        "warnings": warnings,
        "timeout_evidence_paths": [str(path) for path in item.get("timeout_evidence_paths") or []],
        "fix_strategy": str(item.get("fix_strategy") or ""),
    }


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fanout_ratio(physical_rows: int | None, business_rows: int | None) -> float | None:
    if physical_rows is None or business_rows is None or business_rows <= 0:
        return None
    return physical_rows / business_rows


def _is_selector_or_large_table_source(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key) or "") for key in ("consumer_type", "used_by", "source_role", "entry_type")).lower()
    return any(term in text for term in ("selector", "control", "large_table", "detail_table", "table"))


def _bounded_in_sql(item: dict[str, Any]) -> bool:
    if item.get("bounded_in_sql") or item.get("filters_pushed_down") or item.get("default_window_pushed_to_sql"):
        return True
    sql = str(item.get("query") or item.get("sql") or item.get("source_query") or "").lower()
    has_window = bool(item.get("default_window")) and ("where" in sql or "{{" in sql or ":" in sql)
    has_limit_or_filter = " where " in f" {sql} " or " limit " in f" {sql} " or " prewhere " in f" {sql} "
    return bool(has_window or has_limit_or_filter)


def _deduped_to_business_grain(item: dict[str, Any]) -> bool:
    if item.get("deduped_to_business_grain") or item.get("business_grain_deduped"):
        return True
    strategy = str(item.get("fix_strategy") or item.get("grain_strategy") or "").lower()
    return any(term in strategy for term in ("dedupe", "dedup", "group", "business_grain", "pre-aggregat", "preaggregat"))
