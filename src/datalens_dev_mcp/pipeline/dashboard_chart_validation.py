from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from datalens_dev_mcp.pipeline.source_availability import effective_availability


def build_dashboard_chart_validation(
    *,
    dashboard_id: str,
    workbook_id: str,
    branch: str,
    charts: list[dict[str, Any]],
    source_availability_matrix: dict[str, Any],
    environments: list[str] | None = None,
    browser_status: str = "not_checked",
) -> dict[str, Any]:
    envs = environments or _matrix_environments(source_availability_matrix)
    chart_rows = []
    for chart in charts:
        source_keys = [str(item) for item in chart.get("source_keys") or []]
        environment_results: dict[str, Any] = {}
        for environment in envs:
            decisions = [
                effective_availability(
                    source_availability_matrix,
                    source_key,
                    environment,
                    chart.get("runtime_params", {}).get(f"{source_key}_table_available")
                    if isinstance(chart.get("runtime_params"), dict)
                    else None,
                    row_count=_row_count(chart, source_key=source_key, environment=environment),
                    error=str(chart.get("source_errors", {}).get(source_key) or "")
                    if isinstance(chart.get("source_errors"), dict)
                    else "",
                )
                for source_key in source_keys
            ]
            environment_results[environment] = _environment_result(decisions, browser_status=browser_status)
        chart_rows.append(
            {
                "entry_id": str(chart.get("entry_id") or chart.get("entryId") or ""),
                "path": str(chart.get("path") or ""),
                "tab": str(chart.get("tab") or ""),
                "source_keys": source_keys,
                "environment_results": environment_results,
            }
        )
    failed = [
        chart
        for chart in chart_rows
        if any(result["errors"] for result in chart["environment_results"].values())
    ]
    browser_checked_count = sum(
        1
        for chart in chart_rows
        for result in chart["environment_results"].values()
        if result["render_status"] == "browser_pass"
    )
    auth_required_count = sum(
        1
        for chart in chart_rows
        for result in chart["environment_results"].values()
        if result["render_status"] == "browser_auth_required"
    )
    return {
        "schema_version": "datalens.dashboard-chart-validation.v1",
        "dashboard_id": dashboard_id,
        "workbook_id": workbook_id,
        "branch": branch,
        "validated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "environments": envs,
        "charts": chart_rows,
        "summary": {
            "chart_count": len(chart_rows),
            "failed_chart_count": len(failed),
            "browser_checked_count": browser_checked_count,
            "browser_auth_required_count": auth_required_count,
        },
    }


def _environment_result(decisions: list[Any], *, browser_status: str) -> dict[str, Any]:
    errors: list[str] = []
    if not decisions:
        return {
            "availability_classification": "unknown",
            "sql_status": "unknown",
            "render_status": browser_status,
            "errors": ["no_source_keys_declared"],
        }
    classifications = [decision.classification for decision in decisions]
    if "error" in classifications:
        errors.append("source_error")
        sql_status = "source_error"
        classification = "error"
    elif all(not decision.effective_available for decision in decisions):
        sql_status = "not_emitted"
        classification = "expected_unavailable" if any(decision.expected_exception for decision in decisions) else classifications[0]
    else:
        sql_status = "compiled"
        classification = next((item for item in classifications if item != "expected_unavailable"), classifications[0])
    return {
        "availability_classification": classification,
        "sql_status": sql_status,
        "render_status": browser_status,
        "errors": errors,
    }


def _matrix_environments(matrix: dict[str, Any]) -> list[str]:
    envs: list[str] = []
    for source in (matrix.get("sources") or {}).values():
        if isinstance(source, dict):
            for env in (source.get("environments") or {}):
                if env not in envs:
                    envs.append(str(env))
    return envs or ["default"]


def _row_count(chart: dict[str, Any], *, source_key: str, environment: str) -> int | None:
    row_counts = chart.get("row_counts")
    if not isinstance(row_counts, dict):
        return None
    value = row_counts.get(f"{source_key}:{environment}")
    if isinstance(value, int):
        return value
    nested = row_counts.get(source_key)
    if isinstance(nested, dict) and isinstance(nested.get(environment), int):
        return int(nested[environment])
    return None

