from __future__ import annotations

import re
from typing import Any


SQL_RUNTIME_REALITY_SCHEMA_VERSION = "datalens.delta_v8.sql_runtime_reality_check.v1"


def build_sql_runtime_reality_check(
    *,
    sql: str = "",
    payload: dict[str, Any] | None = None,
    dialect: str = "unknown",
    target_execution_engine: str = "browser_runtime",
    validated_by: list[str] | None = None,
    dialect_equivalent: bool = False,
    result: str = "not_run",
) -> dict[str, Any]:
    normalized_dialect = _enum_value(dialect, {"clickhouse", "trino", "mixed", "unknown"}, "unknown")
    normalized_engine = _enum_value(
        target_execution_engine,
        {"datalens_clickhouse", "trino", "browser_runtime", "unknown"},
        "unknown",
    )
    validators = [
        item
        for item in [str(value) for value in validated_by or []]
        if item in {"static_lint", "validateDataset", "metadata_fetch_trino", "browser_runtime", "datalens_query_preview", "manual"}
    ]
    risk_patterns = detect_sql_runtime_risk_patterns(sql=sql, payload=payload or {})
    runtime_validated = any(item in validators for item in {"browser_runtime", "datalens_query_preview"})
    runtime_probe_required = not runtime_validated and normalized_engine in {"datalens_clickhouse", "browser_runtime"}
    known_limitations = []
    if "validateDataset" in validators:
        known_limitations.append("validateDataset is a schema/compile hint, not runtime acceptance")
    if "metadata_fetch_trino" in validators and not dialect_equivalent:
        known_limitations.append("metadata-fetch Trino success is not ClickHouse/DataLens runtime proof")
    if risk_patterns and not runtime_validated:
        known_limitations.append("logged DataLens/ClickHouse risk patterns still require browser/runtime smoke")
    normalized_result = _enum_value(result, {"passed", "failed", "not_run", "not_applicable"}, "not_run")
    if risk_patterns and runtime_validated and normalized_result == "passed":
        normalized_result = "failed"
    return {
        "schema_version": SQL_RUNTIME_REALITY_SCHEMA_VERSION,
        "dialect": normalized_dialect,
        "target_execution_engine": normalized_engine,
        "validated_by": validators,
        "runtime_probe_required": runtime_probe_required,
        "dialect_equivalent": bool(dialect_equivalent),
        "risk_patterns": risk_patterns,
        "known_limitations": known_limitations,
        "result": normalized_result,
    }


def detect_sql_runtime_risk_patterns(*, sql: str = "", payload: dict[str, Any] | None = None) -> list[str]:
    text = _combined_sql_text(sql=sql, payload=payload or {})
    compact = " ".join(text.split())
    lowered = compact.lower()
    risks: list[str] = []
    if _aggregate_alias_in_where(compact):
        risks.append("aggregate_alias_in_where")
    if "chart_local" in lowered and ("dataset" in lowered or "field" in lowered):
        risks.append("chart_only_synthetic_field_referenced_as_dataset_field")
    if _cte_join_with_alias(compact):
        risks.append("cte_on_join_side_with_external_or_free_variables")
    if re.search(r"\b[a-z][a-z0-9_]*\.[a-zA-Z_][\w]*", compact) and "select *" not in lowered:
        risks.append("source_alias_leakage")
    if re.search(r"\bselect\s+\*\b", lowered):
        risks.append("select_star_in_subquery_or_wizard_source")
    if ("array(string)" in lowered and "string" in lowered) or "label_array" in lowered:
        risks.append("string_array_common_type_ambiguity")
    if _requires_raw_schema(payload or {}):
        risks.append("missing_raw_schema_for_ch_subselect")
    if "_mend" in lowered or "old_guid" in lowered or "stale" in lowered and "guid" in lowered:
        risks.append("stale_template_or_guid_reference")
    if "trino" in lowered and "clickhouse" in lowered and "equivalent" not in lowered:
        risks.append("trino_clickhouse_table_or_dialect_mismatch")
    return _dedupe(risks)


def _combined_sql_text(*, sql: str, payload: dict[str, Any]) -> str:
    parts = [str(sql or "")]
    _collect_strings(payload, parts)
    return "\n".join(parts)


def _collect_strings(value: Any, parts: list[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, parts)
    elif isinstance(value, list):
        for item in value:
            _collect_strings(item, parts)
    elif isinstance(value, str):
        parts.append(value)


def _aggregate_alias_in_where(sql: str) -> bool:
    aliases = {
        match.group(1).lower()
        for match in re.finditer(
            r"\b(?:any|sum|avg|count|min|max|median|quantile)\s*\([^)]*\)\s+as\s+([a-zA-Z_][\w]*)",
            sql,
            flags=re.IGNORECASE,
        )
    }
    if not aliases:
        return False
    where_parts = re.findall(r"\bwhere\b(.+?)(?:\bgroup\b|\border\b|\blimit\b|$)", sql, flags=re.IGNORECASE)
    return any(re.search(rf"\b{re.escape(alias)}\b", part, flags=re.IGNORECASE) for alias in aliases for part in where_parts)


def _cte_join_with_alias(sql: str) -> bool:
    ctes = {
        match.group(1).lower()
        for match in re.finditer(r"\bwith\s+([a-zA-Z_][\w]*)\s+as\s*\(", sql, flags=re.IGNORECASE)
    }
    return any(re.search(rf"\bjoin\s+{re.escape(cte)}\b", sql, flags=re.IGNORECASE) for cte in ctes)


def _requires_raw_schema(payload: dict[str, Any]) -> bool:
    source_type = str(
        payload.get("dataset_type")
        or payload.get("source_type")
        or payload.get("connection_type")
        or ""
    ).upper()
    if source_type != "CH_SUBSELECT":
        return False
    return payload.get("raw_schema") in (None, "", [], {})


def _enum_value(value: str, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
