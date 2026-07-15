#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.api.client import DataLensApiClient  # noqa: E402
from datalens_dev_mcp.config import DataLensConfig, load_env_file  # noqa: E402
from datalens_dev_mcp.mcp.response_projection import (  # noqa: E402
    dashboard_summary,
    editor_chart_summary,
    sanitize_response,
    serialized_metadata,
    stable_sha256,
    workbook_entries_summary,
)
from datalens_dev_mcp.mcp.tools.runtime import dl_auth_probe, dl_runtime_status  # noqa: E402
from datalens_dev_mcp.pipeline.sql_performance import (  # noqa: E402
    _extract_sql_values,
    analyze_sql,
    inspector_import_contract,
    plan_optimizations,
    profile_performance,
)


READ_ONLY_ENV = {
    "DATALENS_MCP_ENABLE_WRITES": "0",
    "DATALENS_MCP_ENABLE_EXPERT_RPC": "0",
    "DATALENS_MCP_LIVE_ALLOW_SAVE": "0",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "0",
    "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "0",
}
TARGET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
TARGET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def parse_target(value: str) -> dict[str, str]:
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("target must use NAME:WORKBOOK_ID:DASHBOARD_ID")
    name, workbook_id, dashboard_id = (part.strip() for part in parts)
    if not TARGET_NAME_PATTERN.fullmatch(name):
        raise argparse.ArgumentTypeError("target NAME must contain only letters, digits, underscores, or hyphens")
    for label, target_id in (("WORKBOOK_ID", workbook_id), ("DASHBOARD_ID", dashboard_id)):
        if not TARGET_ID_PATTERN.fullmatch(target_id):
            raise argparse.ArgumentTypeError(f"target {label} must be a non-empty DataLens identifier")
    return {"name": name, "workbook_id": workbook_id, "dashboard_id": dashboard_id}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only SQL/performance live diagnostics.")
    parser.add_argument("--artifact-dir", default="artifacts/sql_performance/live", help="Directory for sanitized evidence.")
    parser.add_argument("--env-file", default="~/.config/datalens-dev-mcp/env")
    parser.add_argument("--max-charts-per-dashboard", type=int, default=40)
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        type=parse_target,
        metavar="NAME:WORKBOOK_ID:DASHBOARD_ID",
        help="Explicit read-only target. Repeat the option to inspect multiple dashboards.",
    )
    args = parser.parse_args()
    if args.max_charts_per_dashboard <= 0:
        parser.error("--max-charts-per-dashboard must be greater than zero")
    names = [target["name"] for target in args.target]
    if len(names) != len(set(names)):
        parser.error("each --target NAME must be unique")
    return args


def now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Any) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_response(payload)
    path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), **serialized_metadata(sanitized)}


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def chart_ids_from_dashboard(response: dict[str, Any], entry_index: dict[str, dict[str, str]]) -> list[str]:
    summary = dashboard_summary(response)
    ids = summary.get("linked_object_ids") if isinstance(summary.get("linked_object_ids"), list) else []
    candidates = [str(item) for item in ids if str(item)]

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {"chartId", "chart_id", "widgetId", "widget_id"} and isinstance(nested, str):
                    candidates.append(nested)
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(response)
    return _ordered_unique([item for item in candidates if item in entry_index])


def _entry_name(entry: dict[str, Any]) -> str:
    for key in ("name", "title", "displayName"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def entry_metadata_index(entries_response: dict[str, Any]) -> dict[str, dict[str, str]]:
    entries = entries_response.get("entries") if isinstance(entries_response.get("entries"), list) else []
    return {
        str(entry.get("entryId")): {
            "scope": str(entry.get("scope") or ""),
            "type": str(entry.get("type") or ""),
            "name": _entry_name(entry),
        }
        for entry in entries
        if isinstance(entry, dict) and entry.get("entryId")
    }


def widget_ids_from_workbook(entry_index: dict[str, dict[str, str]]) -> list[str]:
    return [
        entry_id
        for entry_id, metadata in entry_index.items()
        if metadata.get("scope") == "widget" or "chart" in metadata.get("type", "")
    ]


def read_methods_for_entry(metadata: dict[str, str]) -> list[str]:
    raw = " ".join([metadata.get("scope", ""), metadata.get("type", "")]).lower()
    methods: list[str] = []
    if "wizard" in raw:
        methods.append("getWizardChart")
    if "ql" in raw:
        methods.append("getQLChart")
    if any(marker in raw for marker in ("advanced", "editor", "table_node", "control_node", "chart_node")):
        methods.append("getEditorChart")
    if not methods:
        methods.extend(["getEditorChart", "getWizardChart"])
    methods.extend(["getEditorChart", "getWizardChart"])
    return _ordered_unique(methods)


def dashboard_structure_hash(summary: dict[str, Any]) -> str:
    structure = json.loads(json.dumps(summary))
    identity = structure.get("identity")
    if isinstance(identity, dict):
        identity.pop("rev_id", None)
        identity.pop("saved_id", None)
    return stable_sha256(structure)


def read_dashboard_target(
    *,
    name: str,
    target: dict[str, str],
    client: DataLensApiClient,
    artifact_root: Path,
    max_charts: int,
) -> dict[str, Any]:
    workbook_payload = {"workbookId": target["workbook_id"]}
    entries_response = client.rpc_readonly("getWorkbookEntries", workbook_payload)
    entries_summary = workbook_entries_summary(entries_response)
    write_json(artifact_root / f"{name}.workbook_entries.summary.json", entries_summary)
    write_json(artifact_root / f"{name}.workbook_entries.full.json", entries_response)
    entry_index = entry_metadata_index(entries_response)

    dashboard_reads: list[dict[str, Any]] = []
    for label in ("first", "repeat"):
        payload = {"dashboardId": target["dashboard_id"], "branch": "saved"}
        response = client.rpc_readonly("getDashboard", payload)
        summary = dashboard_summary(response)
        dashboard_reads.append({"summary": summary, "response": response})
        write_json(artifact_root / f"{name}.dashboard_saved_{label}.summary.json", summary)
        write_json(artifact_root / f"{name}.dashboard_saved_{label}.full.json", response)

    chart_ids = chart_ids_from_dashboard(dashboard_reads[0]["response"], entry_index)
    if not chart_ids:
        chart_ids = widget_ids_from_workbook(entry_index)
    chart_ids = chart_ids[:max_charts]

    chart_rows: list[dict[str, Any]] = []
    sql_findings: list[dict[str, Any]] = []
    chart_read_evidence: list[dict[str, Any]] = []
    for chart_id in chart_ids:
        metadata = entry_index.get(chart_id, {"scope": "", "type": "", "name": ""})
        response: dict[str, Any] | None = None
        method = ""
        failures: list[dict[str, str]] = []
        for candidate_method in read_methods_for_entry(metadata):
            try:
                response = client.rpc_readonly(candidate_method, {"chartId": chart_id, "branch": "saved"})
                method = candidate_method
                break
            except Exception as exc:  # noqa: BLE001
                failures.append({"method": candidate_method, "error": exc.__class__.__name__})
        if response is None:
            sql_findings.append(
                {
                    "chart_id": chart_id,
                    "status": "read_failed",
                    "entry_scope": metadata.get("scope", ""),
                    "entry_type": metadata.get("type", ""),
                    "errors": failures[:3],
                }
            )
            chart_read_evidence.append(
                {
                    "chart_id": chart_id,
                    "entry_scope": metadata.get("scope", ""),
                    "entry_type": metadata.get("type", ""),
                    "read_method": "",
                    "status": "read_failed",
                    "errors": failures[:3],
                }
            )
            continue
        chart_read_evidence.append(
            {
                "chart_id": chart_id,
                "entry_scope": metadata.get("scope", ""),
                "entry_type": metadata.get("type", ""),
                "read_method": method,
                "status": "ok",
                "fallback_failures": failures[:2],
            }
        )
        summary = (
            editor_chart_summary(response)
            if method == "getEditorChart"
            else {
                "identity": {"id": chart_id},
                "scope": metadata.get("scope", ""),
                "type": metadata.get("type", ""),
                "method": method,
            }
        )
        write_json(artifact_root / f"{name}.{chart_id}.summary.json", summary)
        write_json(artifact_root / f"{name}.{chart_id}.full.json", response)
        sql_values = _extract_sql_values(response)
        if not sql_values:
            chart_rows.append(
                {
                    "chart_id": chart_id,
                    "dataset_id": "",
                    "source_sql": "",
                    "fields": [],
                    "timings": {},
                    "entry_scope": metadata.get("scope", ""),
                    "entry_type": metadata.get("type", ""),
                    "read_method": method,
                }
            )
            continue
        for index, sql in enumerate(sql_values[:3]):
            sql_report = analyze_sql(sql, source_name=f"{name}.{chart_id}.sql[{index}]")
            sql_findings.extend(
                {
                    "chart_id": chart_id,
                    "source_hash": sql_report.get("source_hash"),
                    "rule": issue.get("rule"),
                    "severity": issue.get("severity"),
                    "line": issue.get("line"),
                    "column": issue.get("column"),
                    "cte": issue.get("cte"),
                }
                for issue in sql_report.get("diagnostics", [])
            )
            chart_rows.append(
                {
                    "chart_id": chart_id,
                    "dataset_id": "",
                    "visible_tab": name,
                    "source_sql": sql,
                    "fields": [],
                    "timings": {},
                    "entry_scope": metadata.get("scope", ""),
                    "entry_type": metadata.get("type", ""),
                    "read_method": method,
                }
            )

    performance = profile_performance({"charts": chart_rows})
    optimization = plan_optimizations({"performance": performance})
    unchanged = {
        "revision_unchanged": (dashboard_reads[0]["summary"].get("identity") or {}).get("rev_id")
        == (dashboard_reads[1]["summary"].get("identity") or {}).get("rev_id"),
        "structure_hash_unchanged": dashboard_structure_hash(dashboard_reads[0]["summary"])
        == dashboard_structure_hash(dashboard_reads[1]["summary"]),
        "first_structure_hash": dashboard_structure_hash(dashboard_reads[0]["summary"]),
        "repeat_structure_hash": dashboard_structure_hash(dashboard_reads[1]["summary"]),
    }
    return {
        "target": name,
        "dashboard_id": target["dashboard_id"],
        "workbook_id": target["workbook_id"],
        "chart_count": len(chart_ids),
        "chart_ids": chart_ids,
        "chart_read_evidence": chart_read_evidence,
        "unchanged": unchanged,
        "sql_findings": sql_findings,
        "performance": performance,
        "optimization": optimization,
        "semantic_graph": {
            "ok": True,
            "status": "not_evaluated",
            "reason": "live chart reads did not supply a complete dataset field contract",
        },
    }


def write_chart_performance_csv(path: Path, targets: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "target",
        "chart_id",
        "source_query_hash",
        "cte_count",
        "joins",
        "windows",
        "aggregates",
        "timing_status",
        "confidence",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for target in targets:
            for row in target.get("performance", {}).get("chart_performance", []):
                writer.writerow({"target": target["target"], **{key: row.get(key, "") for key in fieldnames if key != "target"}})


def main() -> int:
    args = parse_args()
    artifact_dir = Path(args.artifact_dir).resolve()
    artifact_root = artifact_dir / now_run_id()
    env_file = Path(args.env_file).expanduser()

    os.environ["DATALENS_ENV_FILE"] = str(env_file)
    load_env_file(env_file, override=True)
    os.environ.update(READ_ONLY_ENV)
    os.environ["DATALENS_ENV_FILE"] = ""

    status = dl_runtime_status(project_root=str(artifact_dir), local_config_path="")
    auth = dl_auth_probe()
    result: dict[str, Any] = {
        "ok": False,
        "read_only": True,
        "targets": [],
        "runtime": {
            "allow_writes": status.get("allow_writes"),
            "allow_save": status.get("allow_save"),
            "allow_publish": status.get("allow_publish"),
            "expert_rpc_enabled": status.get("expert_rpc_enabled"),
            "token_present": status.get("token_present"),
            "org_id_set": status.get("org_id_set"),
        },
        "auth_probe": {"ok": auth.get("ok"), "method": auth.get("method"), "error": auth.get("error")},
        "browser_inspector_import": inspector_import_contract(),
        "external_query_timing": {
            "status": "not_called",
            "reason": "query-engine timing evidence is optional and must be supplied separately",
        },
        "timing_limitation": "DataLens public read API did not provide browser Inspector render timing in these reads.",
    }

    runtime_is_read_only = all(
        status.get(key) is False for key in ("allow_writes", "allow_save", "allow_publish", "expert_rpc_enabled")
    )
    if not runtime_is_read_only:
        result["error"] = "read_only_runtime_gate_failed"
        write_json(artifact_dir / "live_benchmark_result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    if not auth.get("ok"):
        write_json(artifact_dir / "live_benchmark_result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    client = DataLensApiClient(DataLensConfig.from_env())
    targets = []
    for target in args.target:
        targets.append(
            read_dashboard_target(
                name=target["name"],
                target=target,
                client=client,
                artifact_root=artifact_root,
                max_charts=args.max_charts_per_dashboard,
            )
        )
    result["targets"] = targets
    result["ok"] = all(item["unchanged"]["revision_unchanged"] and item["unchanged"]["structure_hash_unchanged"] for item in targets)
    write_chart_performance_csv(artifact_dir / "chart_performance_live.csv", targets)
    write_json(artifact_dir / "live_benchmark_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
