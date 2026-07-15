from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


AvailabilityClassification = Literal[
    "present_with_data",
    "present_empty",
    "missing",
    "expected_unavailable",
    "error",
    "unknown",
]

DELTA_V7_SOURCE_MATRIX_SCHEMA_VERSION = "datalens.delta_v7.source_availability_consumer_matrix.v1"
DELTA_V8_SOURCE_MATRIX_SCHEMA_VERSION = "datalens.delta_v8.source_availability_runtime_matrix.v1"


@dataclass(frozen=True)
class AvailabilityDecision:
    source_key: str
    environment: str
    static_supported: bool
    runtime_available: bool
    effective_available: bool
    classification: AvailabilityClassification
    table_present: bool | None = None
    expected_exception: bool = False
    reason: str = ""
    schema_version: str = "datalens.dashboard-source-availability-decision.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_runtime_availability(runtime_param: Any, *, static_supported: bool) -> bool:
    if not static_supported:
        return False
    if runtime_param is None:
        return True
    if isinstance(runtime_param, list | tuple | set):
        if not runtime_param:
            return False
        return any(normalize_runtime_availability(item, static_supported=static_supported) for item in runtime_param)
    if isinstance(runtime_param, bool):
        return runtime_param
    if isinstance(runtime_param, int | float):
        return runtime_param != 0
    text = str(runtime_param).strip().strip("'\"").lower()
    if text in {"", "0", "false", "no", "off", "none", "null"}:
        return False
    if text in {"1", "true", "yes", "on", "available"}:
        return True
    return True


def effective_availability(
    matrix: dict[str, Any],
    source_key: str,
    environment: str,
    runtime_param: Any = None,
    *,
    row_count: int | None = None,
    error: str = "",
) -> AvailabilityDecision:
    source = _source_from_matrix(matrix, source_key)
    envs = source.get("environments") if isinstance(source, dict) else {}
    env = envs.get(environment) if isinstance(envs, dict) else {}
    static_supported = bool(env.get("static_supported")) if isinstance(env, dict) else False
    table_present_raw = env.get("table_present") if isinstance(env, dict) else None
    table_present = table_present_raw if isinstance(table_present_raw, bool) else None
    expected_exception = bool(env.get("expected_exception")) if isinstance(env, dict) else False
    runtime_available = normalize_runtime_availability(runtime_param, static_supported=static_supported)
    effective = bool(static_supported and runtime_available)
    classification = classify_availability(
        static_supported=static_supported,
        table_present=table_present,
        row_count=row_count,
        expected_exception=expected_exception,
        error=error,
    )
    return AvailabilityDecision(
        source_key=source_key,
        environment=environment,
        static_supported=static_supported,
        runtime_available=runtime_available,
        effective_available=effective,
        classification=classification,
        table_present=table_present,
        expected_exception=expected_exception,
        reason=str(env.get("reason") or "") if isinstance(env, dict) else "source or environment is absent from matrix",
    )


def classify_availability(
    *,
    static_supported: bool,
    table_present: bool | None,
    row_count: int | None = None,
    expected_exception: bool = False,
    error: str = "",
) -> AvailabilityClassification:
    if error:
        return "error"
    if not static_supported:
        return "expected_unavailable" if expected_exception else "missing"
    if table_present is False:
        return "expected_unavailable" if expected_exception else "missing"
    if table_present is True and row_count == 0:
        return "present_empty"
    if table_present is True and isinstance(row_count, int) and row_count > 0:
        return "present_with_data"
    if table_present is True:
        return "unknown"
    return "unknown"


def load_source_availability_matrix(
    *,
    project: str,
    metadata_fetch_artifact: str | Path = "",
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if metadata_fetch_artifact:
        path = Path(metadata_fetch_artifact)
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return source_availability_from_metadata_fetch(payload, project=project, generated_from=str(path))
    if fallback:
        return validate_source_availability_matrix(fallback, project=project)
    return {"schema_version": "datalens.dashboard-source-availability.v1", "project": project, "sources": {}}


def source_availability_from_metadata_fetch(
    payload: dict[str, Any],
    *,
    project: str,
    generated_from: str = "metadata-fetch",
) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    rows = payload.get("sources") or payload.get("source_matrix") or payload.get("rows") or []
    if isinstance(rows, dict):
        rows = [
            {"source_key": source_key, **value}
            for source_key, value in rows.items()
            if isinstance(value, dict)
        ]
    for row in (rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        source_key = str(row.get("source_key") or row.get("source") or row.get("name") or "").strip()
        environment = str(row.get("environment") or row.get("env") or "default").strip().lower()
        if not source_key:
            continue
        source = sources.setdefault(source_key, {"physical_tables": [], "environments": {}})
        for table in _list_values(row.get("physical_tables") or row.get("tables") or row.get("table")):
            if table not in source["physical_tables"]:
                source["physical_tables"].append(table)
        table_present = _optional_bool(row.get("table_present", row.get("present")))
        static_supported = bool(row.get("static_supported", table_present is not False))
        source["environments"][environment] = {
            "static_supported": static_supported,
            "table_present": table_present,
            "expected_exception": bool(row.get("expected_exception", False)),
            "reason": str(row.get("reason") or row.get("status") or ""),
        }
    return validate_source_availability_matrix(
        {
            "schema_version": "datalens.dashboard-source-availability.v1",
            "project": project,
            "generated_from": generated_from,
            "sources": sources,
        },
        project=project,
    )


def validate_source_availability_matrix(matrix: dict[str, Any], *, project: str = "") -> dict[str, Any]:
    result = dict(matrix)
    result["schema_version"] = "datalens.dashboard-source-availability.v1"
    if project and not result.get("project"):
        result["project"] = project
    result.setdefault("project", project)
    result.setdefault("sources", {})
    for source_key, source in list((result.get("sources") or {}).items()):
        if not isinstance(source, dict):
            result["sources"][source_key] = {"physical_tables": [], "environments": {}}
            continue
        source.setdefault("physical_tables", [])
        source.setdefault("environments", {})
        for environment, env in list((source.get("environments") or {}).items()):
            if not isinstance(env, dict):
                source["environments"][environment] = {"static_supported": False}
                continue
            env["static_supported"] = bool(env.get("static_supported"))
            if "table_present" not in env:
                env["table_present"] = None
            env["expected_exception"] = bool(env.get("expected_exception", False))
    return result


def build_source_availability_contract(
    *,
    dashboard_id: str,
    workbook_id: str = "",
    environments: list[str] | None = None,
    sources: list[dict[str, Any]] | dict[str, Any] | None = None,
    artifact_paths: list[str] | None = None,
) -> dict[str, Any]:
    normalized_sources = _source_rows_for_contract(sources or {})
    envs = environments or sorted(
        {
            env
            for source in normalized_sources
            for env in set(source.get("expected_by_environment") or {}) | set(source.get("observed_by_environment") or {})
        }
    )
    conflicts = _source_matrix_conflicts(normalized_sources, envs)
    return {
        "schema_version": "datalens.source-availability-matrix.delta-v6",
        "dashboard_id": dashboard_id,
        "workbook_id": workbook_id,
        "generated_at": _generated_at(),
        "environments": envs,
        "sources": normalized_sources,
        "conflicts": conflicts,
        "artifact_paths": [str(path) for path in artifact_paths or [] if str(path)],
    }


def source_status_label(decision: AvailabilityDecision) -> str:
    if decision.classification in {"missing", "expected_unavailable"}:
        return "NO TABLE"
    if decision.classification == "present_empty":
        return "NO DATA"
    if decision.classification == "error":
        return "ERROR"
    if decision.classification == "present_with_data":
        return "OK"
    return "UNKNOWN"


def validate_source_consumer_consistency(
    matrix: dict[str, Any],
    consumers: list[dict[str, Any]],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    for consumer in consumers:
        source_key = str(consumer.get("source_key") or "").strip()
        environment = str(consumer.get("environment") or consumer.get("env") or "").strip().lower()
        if not source_key or not environment:
            continue
        decision = effective_availability(
            matrix,
            source_key,
            environment,
            consumer.get("runtime_param"),
            row_count=_optional_int(consumer.get("row_count")),
            error=str(consumer.get("error") or ""),
        )
        expected = source_status_label(decision)
        actual = str(consumer.get("status") or consumer.get("display_status") or "").strip()
        if actual and actual != expected:
            issues.append(
                {
                    "source_key": source_key,
                    "environment": environment,
                    "consumer": str(consumer.get("consumer") or consumer.get("tab") or ""),
                    "expected_status": expected,
                    "actual_status": actual,
                }
            )
    return {"ok": not issues, "issues": issues}


def build_dashboard_source_availability_matrix(
    *,
    dashboard_snapshot_path: str = "",
    metadata_fetch_inventory_path: str = "",
    data_health_readback_path: str = "",
    source_catalog_path: str = "",
    environments: list[str] | None = None,
    dashboard_object_ids: list[str] | None = None,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    evidence_paths = [
        path
        for path in (
            dashboard_snapshot_path,
            metadata_fetch_inventory_path,
            data_health_readback_path,
            source_catalog_path,
        )
        if path
    ]
    payloads = [_read_json_payload(path) for path in evidence_paths]
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        rows.extend(_delta_v7_rows_from_payload(payload))
    if not rows:
        return {
            "ok": False,
            "status": "insufficient_evidence",
            "schema_version": DELTA_V7_SOURCE_MATRIX_SCHEMA_VERSION,
            "evidence_paths": evidence_paths,
            "sources": [],
            "blocked_reasons": ["insufficient_evidence"],
        }
    env_filter = {str(env).strip().lower() for env in environments or [] if str(env).strip()}
    object_filter = {str(item).strip() for item in dashboard_object_ids or [] if str(item).strip()}
    normalized = []
    for row in rows:
        source_key = str(row.get("source_key") or row.get("source") or row.get("name") or "").strip()
        environment = str(row.get("environment") or row.get("env") or "default").strip().lower()
        if not source_key:
            continue
        if env_filter and environment not in env_filter:
            continue
        if object_filter and not _row_mentions_any_object(row, object_filter):
            continue
        normalized.append(_delta_v7_source_row(row, source_key=source_key, environment=environment, strict=strict_publish_gate))
    blocked = [
        f"{row['source_key']}:{row['environment']}:{row['expected_status']}"
        for row in normalized
        if row.get("publish_blocking")
    ]
    return {
        "ok": not blocked,
        "status": "blocked" if blocked else "pass",
        "schema_version": DELTA_V7_SOURCE_MATRIX_SCHEMA_VERSION,
        "evidence_paths": evidence_paths,
        "sources": normalized,
        "blocked_reasons": blocked,
    }


def validate_source_availability_consumers(
    matrix: dict[str, Any] | None = None,
    consumers: list[dict[str, Any]] | None = None,
    *,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    if not isinstance(matrix, dict) or not matrix:
        return {
            "ok": False,
            "status": "insufficient_evidence",
            "blocked_reasons": ["insufficient_evidence"],
            "issues": [],
        }
    if matrix.get("schema_version") == DELTA_V7_SOURCE_MATRIX_SCHEMA_VERSION:
        rows = [row for row in matrix.get("sources") or [] if isinstance(row, dict)]
    else:
        rows = [
            _delta_v7_source_row(
                row,
                source_key=str(row.get("source_key") or ""),
                environment=str(row.get("environment") or "default"),
                strict=strict_publish_gate,
            )
            for row in _delta_v7_rows_from_payload(matrix)
            if isinstance(row, dict)
        ]
    extra_consumer_rows = [
        _consumer_issue(row)
        for row in consumers or []
        if isinstance(row, dict)
    ]
    issues = [issue for issue in extra_consumer_rows if issue]
    for row in rows:
        if row.get("conflict"):
            issues.append(
                {
                    "source_key": str(row.get("source_key") or ""),
                    "environment": str(row.get("environment") or ""),
                    "rule": "consumer_status_conflict",
                }
            )
        if strict_publish_gate and row.get("publish_blocking"):
            issues.append(
                {
                    "source_key": str(row.get("source_key") or ""),
                    "environment": str(row.get("environment") or ""),
                    "rule": "publish_blocking_source_availability",
                }
            )
    blocked = [
        f"{issue.get('source_key') or '<unknown>'}:{issue.get('environment') or '<unknown>'}:{issue.get('rule')}"
        for issue in issues
    ]
    return {
        "ok": not blocked,
        "status": "blocked" if blocked else "pass",
        "issues": issues,
        "blocked_reasons": blocked,
    }


def build_source_availability_runtime_matrix(
    matrix: dict[str, Any] | None = None,
    *,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    source = matrix if isinstance(matrix, dict) else {}
    if source.get("schema_version") == DELTA_V7_SOURCE_MATRIX_SCHEMA_VERSION:
        rows = [
            _delta_v7_source_row(
                row,
                source_key=str(row.get("source_key") or ""),
                environment=str(row.get("environment") or "default"),
                strict=strict_publish_gate,
            )
            for row in source.get("sources") or []
            if isinstance(row, dict)
        ]
    else:
        rows = [
            _delta_v7_source_row(
                row,
                source_key=str(row.get("source_key") or row.get("source") or row.get("name") or ""),
                environment=str(row.get("environment") or row.get("env") or "default"),
                strict=strict_publish_gate,
            )
            for row in _delta_v7_rows_from_payload(source)
            if isinstance(row, dict)
        ]
    normalized = [_delta_v8_source_row(row) for row in rows]
    conflicts = [
        {
            "source_key": row["source_key"],
            "environment": row["environment"],
            "consumers": row["consumers"],
            "expected_status": row["expected_status"],
            "rule": "consumer_status_conflict",
        }
        for row in normalized
        if row.get("conflict")
    ]
    blocked = [
        f"{row['source_key']}:{row['environment']}:{row['expected_status']}"
        for row in normalized
        if row.get("publish_blocking")
    ]
    return {
        "ok": not blocked and not conflicts,
        "status": "blocked" if blocked or conflicts else "pass",
        "schema_version": DELTA_V8_SOURCE_MATRIX_SCHEMA_VERSION,
        "sources": normalized,
        "conflicts": conflicts,
        "blocked_reasons": blocked
        + [
            f"{item['source_key']}:{item['environment']}:{item['rule']}"
            for item in conflicts
        ],
    }


def plan_source_availability_patch(
    matrix: dict[str, Any] | None = None,
    *,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    validation = validate_source_availability_consumers(matrix, strict_publish_gate=strict_publish_gate)
    rows = [row for row in (matrix or {}).get("sources", []) if isinstance(row, dict)]
    actions = []
    for row in rows:
        if not row.get("publish_blocking"):
            continue
        expected = str(row.get("expected_status") or "")
        if expected == "NO_TABLE":
            recommendation = "disable runtime query for this environment and render an explicit NO TABLE state"
        elif expected == "NO_DATA":
            recommendation = "render NO DATA without relabeling the source as missing"
        elif expected == "ERROR":
            recommendation = "fix the query/runtime error before publish"
        else:
            recommendation = "supply enough inventory/readback evidence to classify the source"
        actions.append(
            {
                "source_key": row.get("source_key"),
                "environment": row.get("environment"),
                "expected_status": expected,
                "recommendation": recommendation,
            }
        )
    return {
        "ok": validation["ok"],
        "status": "planned" if actions else validation["status"],
        "actions": actions,
        "blocked_reasons": validation.get("blocked_reasons") or [],
    }


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


def _delta_v7_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("sources") or payload.get("source_matrix") or payload.get("rows") or []
    if isinstance(rows, dict):
        return [{"source_key": key, **value} for key, value in rows.items() if isinstance(value, dict)]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _delta_v7_source_row(row: dict[str, Any], *, source_key: str, environment: str, strict: bool) -> dict[str, Any]:
    physical_present = _optional_bool(
        row.get("physical_table_present", row.get("table_present", row.get("present")))
    )
    row_count = _optional_int(row.get("row_count"))
    schema_present = _optional_bool(row.get("schema_present", row.get("schema_exists")))
    static_supported = bool(row.get("static_supported", physical_present is not False))
    runtime_available = _optional_bool(row.get("runtime_param_available", row.get("runtime_available")))
    error = str(row.get("error") or row.get("runtime_error") or "").strip()
    expected_status = str(row.get("expected_status") or "").strip().upper()
    if expected_status not in {"OK", "NO_DATA", "NO_TABLE", "ERROR", "UNKNOWN"}:
        expected_status = _delta_v7_expected_status(
            static_supported=static_supported,
            physical_present=physical_present,
            row_count=row_count,
            error=error,
        )
    consumer_statuses = _consumer_statuses(row)
    conflict = _consumer_conflict(expected_status, consumer_statuses)
    stale_runtime_expands = static_supported is False and runtime_available is True
    publish_blocking = bool(
        strict
        and (
            conflict
            or stale_runtime_expands
            or expected_status in {"ERROR", "UNKNOWN"}
            or (expected_status == "NO_TABLE" and row.get("query_would_execute"))
        )
    )
    return {
        "source_key": source_key,
        "environment": environment,
        "physical_table_present": physical_present if physical_present is not None else "unknown",
        "row_count": row_count if row_count is not None else "unknown",
        "schema_present": schema_present if schema_present is not None else "unknown",
        "static_supported": static_supported,
        "runtime_param_available": runtime_available if runtime_available is not None else "unknown",
        "effective_available": bool(static_supported and runtime_available is not False and physical_present is not False),
        "expected_status": expected_status,
        "consumer_statuses": consumer_statuses,
        "conflict": conflict or stale_runtime_expands,
        "publish_blocking": publish_blocking,
    }


def _delta_v8_source_row(row: dict[str, Any]) -> dict[str, Any]:
    physical_present = row.get("physical_table_present")
    physical_tables = row.get("physical_tables")
    if not isinstance(physical_tables, list):
        physical_tables = _list_values(row.get("physical_table") or row.get("table"))
    consumers = row.get("consumer_statuses") if isinstance(row.get("consumer_statuses"), dict) else {}
    return {
        "source_key": str(row.get("source_key") or ""),
        "environment": str(row.get("environment") or "default"),
        "physical_tables": physical_tables,
        "static_available": bool(row.get("static_supported")),
        "runtime_available": False if row.get("runtime_param_available") is False else True,
        "effective_available": bool(row.get("effective_available")),
        "row_count": row.get("row_count") if isinstance(row.get("row_count"), int) else None,
        "expected_status": str(row.get("expected_status") or "UNKNOWN"),
        "consumers": consumers,
        "conflict": bool(row.get("conflict")),
        "publish_blocking": bool(row.get("publish_blocking")),
        "notes": [
            "NO TABLE means physically absent or statically unsupported; NO DATA means present with zero rows",
            "stale runtime params cannot make statically unsupported sources available",
        ],
        "physical_table_present": physical_present,
    }


def _delta_v7_expected_status(
    *,
    static_supported: bool,
    physical_present: bool | None,
    row_count: int | None,
    error: str,
) -> str:
    if error:
        return "ERROR"
    if not static_supported or physical_present is False:
        return "NO_TABLE"
    if physical_present is True and row_count == 0:
        return "NO_DATA"
    if physical_present is True and isinstance(row_count, int) and row_count > 0:
        return "OK"
    return "UNKNOWN"


def _consumer_statuses(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("consumer_statuses")
    if isinstance(raw, dict):
        return {str(key): _normalize_status_label(value) for key, value in raw.items()}
    result: dict[str, Any] = {}
    for key in ("data_health_status", "source_tables_status", "overview_status", "data_quality_status", "selector_status"):
        if row.get(key) not in (None, ""):
            result[key] = _normalize_status_label(row.get(key))
    observed = row.get("observed_status") or row.get("status")
    if observed not in (None, ""):
        result.setdefault("observed", _normalize_status_label(observed))
    return result


def _consumer_conflict(expected_status: str, consumer_statuses: dict[str, Any]) -> bool:
    statuses = {str(value).upper() for value in consumer_statuses.values() if str(value)}
    if not statuses:
        return False
    if expected_status in statuses and len(statuses) == 1:
        return False
    if "OK" in statuses and "NO_TABLE" in statuses:
        return True
    return any(status not in {expected_status, "UNKNOWN"} for status in statuses)


def _normalize_status_label(value: Any) -> str:
    status = _status_text(value).upper()
    aliases = {
        "PRESENT": "OK",
        "PRESENT_WITH_DATA": "OK",
        "EXISTS": "OK",
        "EMPTY": "NO_DATA",
        "PRESENT_EMPTY": "NO_DATA",
        "MISSING": "NO_TABLE",
        "ABSENT": "NO_TABLE",
        "EXPECTED_UNAVAILABLE": "NO_TABLE",
    }
    return aliases.get(status, status if status in {"OK", "NO_DATA", "NO_TABLE", "ERROR", "UNKNOWN"} else "UNKNOWN")


def _consumer_issue(row: dict[str, Any]) -> dict[str, str] | None:
    expected = _normalize_status_label(row.get("expected_status"))
    actual = _normalize_status_label(row.get("status") or row.get("actual_status") or row.get("display_status"))
    if expected and actual and expected != "UNKNOWN" and actual != "UNKNOWN" and expected != actual:
        return {
            "source_key": str(row.get("source_key") or ""),
            "environment": str(row.get("environment") or row.get("env") or ""),
            "rule": "consumer_status_mismatch",
        }
    return None


def _row_mentions_any_object(row: dict[str, Any], object_ids: set[str]) -> bool:
    text = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return any(object_id in text for object_id in object_ids)


def _read_json_payload(path: str) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _source_from_matrix(matrix: dict[str, Any], source_key: str) -> dict[str, Any]:
    sources = matrix.get("sources") if isinstance(matrix, dict) else {}
    if isinstance(sources, dict):
        return sources.get(source_key) if isinstance(sources.get(source_key), dict) else {}
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict) and str(source.get("source_key") or "") == source_key:
                return _contract_row_to_legacy_source(source)
    return {}


def _contract_row_to_legacy_source(row: dict[str, Any]) -> dict[str, Any]:
    envs: dict[str, Any] = {}
    expected = row.get("expected_by_environment") if isinstance(row.get("expected_by_environment"), dict) else {}
    observed = row.get("observed_by_environment") if isinstance(row.get("observed_by_environment"), dict) else {}
    no_table_allowed = (
        row.get("no_table_allowed_by_environment") if isinstance(row.get("no_table_allowed_by_environment"), dict) else {}
    )
    for environment in set(expected) | set(observed) | set(no_table_allowed):
        expected_status = _status_text(expected.get(environment))
        observed_status = _status_text(observed.get(environment))
        allowed_no_table = bool(no_table_allowed.get(environment))
        table_present = _table_present_from_status(observed_status or expected_status)
        static_supported = not allowed_no_table and expected_status not in {"missing", "expected_unavailable", "no_table"}
        envs[str(environment).lower()] = {
            "static_supported": static_supported,
            "table_present": table_present,
            "expected_exception": allowed_no_table,
            "reason": observed_status or expected_status,
        }
    return {"physical_tables": _list_values(row.get("tables")), "environments": envs}


def _source_rows_for_contract(sources: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(sources, list):
        return [dict(item) for item in sources if isinstance(item, dict)]
    rows: list[dict[str, Any]] = []
    for source_key, source in sources.items():
        if not isinstance(source, dict):
            continue
        expected: dict[str, Any] = {}
        observed: dict[str, Any] = {}
        no_table: dict[str, Any] = {}
        for environment, env in (source.get("environments") or {}).items():
            if not isinstance(env, dict):
                continue
            static_supported = bool(env.get("static_supported"))
            table_present = env.get("table_present") if isinstance(env.get("table_present"), bool) else None
            expected[str(environment)] = "present" if static_supported else "expected_unavailable"
            observed[str(environment)] = _observed_status(table_present)
            no_table[str(environment)] = bool(env.get("expected_exception") or not static_supported)
        rows.append(
            {
                "source_key": str(source_key),
                "tables": _list_values(source.get("physical_tables")),
                "expected_by_environment": expected,
                "observed_by_environment": observed,
                "no_table_allowed_by_environment": no_table,
                "notes": _list_values(source.get("notes")),
            }
        )
    return rows


def _source_matrix_conflicts(sources: list[dict[str, Any]], environments: list[str]) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for source in sources:
        expected = source.get("expected_by_environment") if isinstance(source.get("expected_by_environment"), dict) else {}
        observed = source.get("observed_by_environment") if isinstance(source.get("observed_by_environment"), dict) else {}
        no_table = (
            source.get("no_table_allowed_by_environment")
            if isinstance(source.get("no_table_allowed_by_environment"), dict)
            else {}
        )
        for environment in environments:
            if bool(no_table.get(environment)) and _table_present_from_status(_status_text(observed.get(environment))) is True:
                conflicts.append(
                    {
                        "source_key": str(source.get("source_key") or ""),
                        "environment": environment,
                        "rule": "no_table_conflicts_with_inventory_present",
                    }
                )
            expected_no_table = _status_text(expected.get(environment)) == "no_table"
            observed_present = _table_present_from_status(_status_text(observed.get(environment))) is True
            if expected_no_table and observed_present:
                conflicts.append(
                    {
                        "source_key": str(source.get("source_key") or ""),
                        "environment": environment,
                        "rule": "expected_no_table_conflicts_with_observed_present",
                    }
                )
    return conflicts


def _status_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("status") or value.get("classification") or value.get("expected") or value.get("observed")
    return str(value or "").strip().lower().replace(" ", "_")


def _table_present_from_status(status: str) -> bool | None:
    if status in {"present", "present_with_data", "present_empty", "no_data", "ok", "exists"}:
        return True
    if status in {"missing", "expected_unavailable", "no_table", "absent"}:
        return False
    return None


def _observed_status(table_present: bool | None) -> str:
    if table_present is True:
        return "present"
    if table_present is False:
        return "missing"
    return "unknown"


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "present", "exists"}:
        return True
    if text in {"0", "false", "no", "missing", "absent"}:
        return False
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _generated_at() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
