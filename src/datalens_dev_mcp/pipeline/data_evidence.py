from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import write_json

EVIDENCE_STATUSES = {
    "AVAILABLE",
    "UNAVAILABLE_CONFIRMED",
    "NOT_PROBED",
    "PROBE_BLOCKED",
    "INCONCLUSIVE_TRUNCATED",
}
PROBE_OPERATIONS = {
    "table_discovery",
    "column_list",
    "bounded_row_count",
    "bounded_sample",
    "cte_stage_count",
    "link_direction",
    "source_freshness_availability",
}
SENSITIVE_KEY_RE = re.compile(r"(token|authorization|subjecttoken|password|secret|cookie|iam)", re.IGNORECASE)
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=\-]+")
TOKEN_VALUE_RE = re.compile(r"\by0_[A-Za-z0-9._~+/=\-]{12,}\b")


def build_data_evidence_probe_plan(
    *,
    project_root: str | Path = ".",
    provider_config: dict[str, Any] | None = None,
    probe_operation: str = "table_discovery",
    table_ref: str = "",
    columns: list[str] | None = None,
    where_clause: str = "",
    cte_sql: str = "",
    graph_config: dict[str, Any] | None = None,
    sample_limit: int = 50,
    environment: str = "dev",
    artifact_name: str = "latest",
) -> dict[str, Any]:
    operation = probe_operation.strip()
    if operation not in PROBE_OPERATIONS:
        return _error("missing_input", f"probe_operation must be one of {sorted(PROBE_OPERATIONS)}")
    provider = _provider(provider_config)
    table = _parse_table_ref(table_ref)
    if operation != "cte_stage_count" and not table["ok"]:
        return _error("missing_input", table["error"])
    validation = _validate_probe_inputs(
        operation=operation,
        table_ref=table_ref,
        columns=columns or [],
        cte_sql=cte_sql,
        environment=environment,
    )
    if validation:
        return {
            "ok": False,
            "status": "PROBE_BLOCKED",
            "error": {"category": "unsafe_probe", "message": validation},
            "provider": provider,
            "probe_operation": operation,
            "execute_now": False,
        }
    probe = _probe_sql(
        provider=provider,
        operation=operation,
        table=table,
        columns=columns or [],
        where_clause=where_clause,
        cte_sql=cte_sql,
        graph_config=graph_config or {},
        sample_limit=max(1, min(int(sample_limit or 50), 1000)),
    )
    artifact_rel = f"reports/data_evidence/{_safe_artifact_name(artifact_name)}.json"
    return {
        "ok": True,
        "status": "NOT_PROBED",
        "schema_version": "2026-06-11.data_evidence_probe_plan.v1",
        "generated_at": _now(),
        "project_root": str(Path(project_root)),
        "provider": provider,
        "probe_operation": operation,
        "evidence_level": "probe_plan_only",
        "execute_now": False,
        "table_ref": table_ref,
        "environment": environment,
        "sql": probe["sql"],
        "parameters": probe["parameters"],
        "expected_result_contract": probe["result_contract"],
        "artifact_path": str(Path(project_root) / artifact_rel),
        "artifact_policy": "write sanitized evidence under project reports/data_evidence or requirements only",
        "absence_rule": "Do not claim table absence unless targeted table_discovery returns UNAVAILABLE_CONFIRMED.",
    }


def evaluate_data_evidence(
    *,
    table_ref: str = "",
    inventory: dict[str, Any] | None = None,
    targeted_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not table_ref:
        return _error("missing_input", "table_ref is required")
    inventory = inventory or {}
    targeted_evidence = targeted_evidence or {}
    targeted_status = _targeted_status(table_ref, targeted_evidence)
    if targeted_status in {"AVAILABLE", "UNAVAILABLE_CONFIRMED", "PROBE_BLOCKED"}:
        return {
            "ok": targeted_status == "AVAILABLE",
            "table_ref": table_ref,
            "status": targeted_status,
            "evidence_level": "targeted_table_discovery",
            "reason": "Targeted table_discovery evidence overrides aggregate inventory.",
            "next_steps": [] if targeted_status == "AVAILABLE" else ["Review targeted probe output and provider error details."],
        }
    inventory_tables = {_normalize_table_ref(str(item)) for item in _inventory_tables(inventory)}
    normalized = _normalize_table_ref(table_ref)
    if normalized in inventory_tables:
        return {
            "ok": True,
            "table_ref": table_ref,
            "status": "AVAILABLE",
            "evidence_level": "aggregate_inventory",
            "reason": "Table is present in aggregate inventory.",
            "next_steps": ["Run targeted column_list before field-level conclusions."],
        }
    if bool(inventory.get("truncated") or inventory.get("is_truncated")):
        return {
            "ok": False,
            "table_ref": table_ref,
            "status": "INCONCLUSIVE_TRUNCATED",
            "evidence_level": "aggregate_inventory_truncated",
            "reason": "Aggregate inventory is truncated and cannot prove absence.",
            "next_steps": ["Run targeted table_discovery through a read-only metadata/data evidence provider."],
        }
    if inventory_tables:
        return {
            "ok": False,
            "table_ref": table_ref,
            "status": "NOT_PROBED",
            "evidence_level": "aggregate_inventory_only",
            "reason": "Aggregate inventory does not include the table, but no targeted table_discovery evidence was supplied.",
            "next_steps": ["Run targeted table_discovery before claiming absence."],
        }
    return {
        "ok": False,
        "table_ref": table_ref,
        "status": "NOT_PROBED",
        "evidence_level": "none",
        "reason": "No inventory or targeted probe evidence was supplied.",
        "next_steps": ["Run targeted table_discovery and column_list probes."],
    }


def record_data_evidence(
    *,
    project_root: str | Path = ".",
    evidence: dict[str, Any] | None = None,
    artifact_name: str = "latest",
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or not evidence:
        return _error("missing_input", "evidence is required")
    root = Path(project_root)
    sanitized = _sanitize(evidence)
    artifact = {
        "schema_version": "2026-06-11.data_evidence_artifact.v1",
        "recorded_at": _now(),
        "provider_label": "read-only metadata/data evidence provider",
        "evidence": sanitized,
        "status": _status_from_evidence(sanitized),
        "evidence_level": sanitized.get("evidence_level") or sanitized.get("probe_operation") or "recorded_probe_result",
    }
    rel = Path("reports") / "data_evidence" / f"{_safe_artifact_name(artifact_name)}.json"
    write_json(root / rel, artifact)
    _write_requirements_summary(root, artifact)
    return {
        "ok": True,
        "status": artifact["status"],
        "artifact_path": str(root / rel),
        "requirements_summary_path": str(root / "requirements" / "data_evidence.md"),
        "provider_label": artifact["provider_label"],
    }


def _provider(provider_config: dict[str, Any] | None) -> dict[str, Any]:
    provider_config = provider_config or {}
    engine = str(provider_config.get("engine") or provider_config.get("dialect") or "trino").lower()
    if engine not in {"trino", "clickhouse"}:
        engine = "trino"
    return {
        "label": "read-only metadata/data evidence provider",
        "engine": engine,
        "configured": bool(provider_config),
        "supports_runtime_execution": bool(provider_config.get("supports_runtime_execution", False)),
        "execution_policy": "read_only_bounded_probes_only",
    }


def _probe_sql(
    *,
    provider: dict[str, Any],
    operation: str,
    table: dict[str, Any],
    columns: list[str],
    where_clause: str,
    cte_sql: str,
    graph_config: dict[str, Any],
    sample_limit: int,
) -> dict[str, Any]:
    engine = provider["engine"]
    full_name = table.get("full_name", "")
    quoted_columns = ", ".join(_ident(column) for column in columns)
    bounded_where = _where(where_clause)
    if operation == "table_discovery":
        if engine == "clickhouse":
            sql = (
                "SELECT database AS table_schema, name AS table_name FROM system.tables "
                f"WHERE database = '{_sql_literal(table['schema'])}' AND name = '{_sql_literal(table['table'])}' LIMIT 2"
            )
        else:
            sql = (
                f"SELECT table_catalog, table_schema, table_name FROM {_ident(table['catalog'])}.information_schema.tables "
                f"WHERE table_schema = '{_sql_literal(table['schema'])}' AND table_name = '{_sql_literal(table['table'])}' LIMIT 2"
            )
        contract = {"zero_rows": "UNAVAILABLE_CONFIRMED", "one_row": "AVAILABLE", "more_than_one": "PROBE_BLOCKED"}
    elif operation == "column_list":
        if engine == "clickhouse":
            sql = (
                "SELECT name AS column_name, type AS data_type FROM system.columns "
                f"WHERE database = '{_sql_literal(table['schema'])}' AND table = '{_sql_literal(table['table'])}' "
                "ORDER BY position"
            )
        else:
            sql = (
                f"SELECT column_name, data_type, ordinal_position FROM {_ident(table['catalog'])}.information_schema.columns "
                f"WHERE table_schema = '{_sql_literal(table['schema'])}' AND table_name = '{_sql_literal(table['table'])}' "
                "ORDER BY ordinal_position"
            )
        contract = {"rows": "columns", "zero_rows": "NOT_PROBED unless table_discovery already proved availability"}
    elif operation == "bounded_row_count":
        sql = f"SELECT count(*) AS row_count FROM {full_name}{bounded_where}"
        contract = {"one_row": "row_count", "requires_bound": bool(where_clause)}
    elif operation == "bounded_sample":
        sql = f"SELECT {quoted_columns} FROM {full_name}{bounded_where} LIMIT {sample_limit}"
        contract = {"max_rows": sample_limit, "columns": columns}
    elif operation == "cte_stage_count":
        stage = str(graph_config.get("stage_name") or "stage")
        sql = f"WITH {cte_sql.strip()} SELECT count(*) AS row_count FROM {_ident(stage)} LIMIT 1"
        contract = {"one_row": "row_count", "stage_name": stage}
    elif operation == "link_direction":
        source_key = _ident(str(graph_config.get("source_key") or "source_id"))
        target_key = _ident(str(graph_config.get("target_key") or "target_id"))
        probe_value = str(graph_config.get("probe_value") or "")
        value_filter = (
            f"WHERE {source_key} = '{_sql_literal(probe_value)}' "
            f"OR {target_key} = '{_sql_literal(probe_value)}'"
            if probe_value
            else ""
        )
        sql = (
            "SELECT "
            f"sum(CASE WHEN {source_key} IS NOT NULL THEN 1 ELSE 0 END) AS source_side_rows, "
            f"sum(CASE WHEN {target_key} IS NOT NULL THEN 1 ELSE 0 END) AS target_side_rows "
            f"FROM {full_name} {value_filter}"
        )
        contract = {"one_row": "source_side_rows,target_side_rows", "classification": "source_only,target_only,bidirectional,none"}
    else:
        timestamp_column = _ident(str(graph_config.get("timestamp_column") or "dlh_load_dttm"))
        sql = f"SELECT max({timestamp_column}) AS max_timestamp, count(*) AS row_count FROM {full_name}{bounded_where}"
        contract = {"one_row": "max_timestamp,row_count", "availability": "AVAILABLE when row_count > 0"}
    return {"sql": sql, "parameters": {"table_ref": table.get("input") or "", "sample_limit": sample_limit}, "result_contract": contract}


def _validate_probe_inputs(
    *,
    operation: str,
    table_ref: str,
    columns: list[str],
    cte_sql: str,
    environment: str,
) -> str:
    if operation == "bounded_sample":
        if not columns:
            return "bounded_sample requires explicit columns; SELECT * is not allowed"
        if any(str(column).strip() == "*" for column in columns):
            return "SELECT * is not allowed in bounded samples"
    if operation == "cte_stage_count" and not cte_sql.strip():
        return "cte_stage_count requires cte_sql"
    if _is_prod(environment):
        sql_text = " ".join([table_ref, cte_sql, " ".join(columns)])
        if re.search(r"\bselect\s+\*", sql_text, flags=re.IGNORECASE) or "*" in {str(column).strip() for column in columns}:
            return "SELECT * is rejected for production probes; enumerate columns explicitly"
    return ""


def _targeted_status(table_ref: str, evidence: dict[str, Any]) -> str:
    status = str(evidence.get("status") or "").upper()
    if status in EVIDENCE_STATUSES and _normalize_table_ref(str(evidence.get("table_ref") or table_ref)) == _normalize_table_ref(table_ref):
        return status
    rows = evidence.get("rows")
    if evidence.get("probe_operation") == "table_discovery" and isinstance(rows, list):
        return "AVAILABLE" if rows else "UNAVAILABLE_CONFIRMED"
    return ""


def _inventory_tables(inventory: dict[str, Any]) -> list[str]:
    tables = inventory.get("tables") or inventory.get("table_refs") or []
    values: list[str] = []
    for item in tables:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict):
            values.append(str(item.get("table_ref") or item.get("full_name") or item.get("name") or ""))
    return [value for value in values if value]


def _parse_table_ref(table_ref: str) -> dict[str, Any]:
    raw = table_ref.strip()
    if not raw:
        return {"ok": False, "error": "table_ref is required"}
    parts = raw.split(".")
    if len(parts) == 3:
        catalog, schema, table = parts
    elif len(parts) == 2:
        catalog, schema, table = "", parts[0], parts[1]
    else:
        return {"ok": False, "error": "table_ref must be schema.table or catalog.schema.table"}
    if not schema or not table:
        return {"ok": False, "error": "table_ref must include schema and table"}
    full_name = ".".join(_ident(part) for part in parts if part)
    return {"ok": True, "input": raw, "catalog": catalog or "default", "schema": schema, "table": table, "full_name": full_name}


def _ident(value: str) -> str:
    cleaned = value.strip().replace('"', "")
    if not cleaned:
        return ""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
        return cleaned
    return '"' + cleaned.replace('"', '""') + '"'


def _where(where_clause: str) -> str:
    stripped = where_clause.strip()
    if not stripped:
        return ""
    if stripped.lower().startswith("where "):
        return " " + stripped
    return " WHERE " + stripped


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _normalize_table_ref(value: str) -> str:
    return value.strip().strip('"').lower()


def _status_from_evidence(evidence: dict[str, Any]) -> str:
    status = str(evidence.get("status") or "").upper()
    return status if status in EVIDENCE_STATUSES else "NOT_PROBED"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if SENSITIVE_KEY_RE.search(str(key)):
                result[key] = "<redacted>"
            else:
                result[key] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return TOKEN_VALUE_RE.sub("<redacted>", BEARER_RE.sub("Bearer <redacted>", value))
    return value


def _write_requirements_summary(root: Path, artifact: dict[str, Any]) -> None:
    target = root / "requirements" / "data_evidence.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    evidence = artifact.get("evidence") if isinstance(artifact.get("evidence"), dict) else {}
    line = (
        f"- {artifact['recorded_at']} | {artifact['status']} | "
        f"{evidence.get('probe_operation', 'recorded_probe_result')} | "
        f"{evidence.get('table_ref', '')}\n"
    )
    if target.is_file():
        existing = target.read_text(encoding="utf-8")
    else:
        existing = "# Data Evidence\n\n"
    target.write_text(existing.rstrip() + "\n" + line, encoding="utf-8")


def _safe_artifact_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip() or "latest").strip("._")
    return cleaned or "latest"


def _is_prod(environment: str) -> bool:
    return environment.strip().lower() in {"prod", "production", "prd"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _error(category: str, message: str) -> dict[str, Any]:
    return {"ok": False, "status": "PROBE_BLOCKED", "error": {"category": category, "message": message}}
