#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.config import DataLensConfig, read_env_file
from datalens_dev_mcp.pipeline.data_assertions import evaluate_data_assertions
from datalens_dev_mcp.pipeline.dataset_context_profile import build_dataset_context_profile
from datalens_dev_mcp.pipeline.dataset_data_failures import dataset_failure_receipt
from datalens_dev_mcp.pipeline.dataset_data_normalizer import normalize_dataset_data_response
from datalens_dev_mcp.pipeline.dataset_parameters import extract_dashboard_parameter_defaults
from datalens_dev_mcp.pipeline.dataset_probe_planner import DatasetProbePlanner
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService, parse_target_url
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded read-only getDatasetData probes across dashboards.")
    parser.add_argument("--dashboard", action="append", required=True, help="Dashboard URL or exact ID; repeat it.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--org-env-file", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-objects", type=int, default=50)
    parser.add_argument(
        "--mode",
        choices=("context_probe", "assertion_probe", "diagnostic_probe"),
        default="context_probe",
    )
    args = parser.parse_args()

    config = DataLensConfig.from_env(args.env_file)
    if not config.org_id and args.org_env_file:
        fallback = read_env_file(args.org_env_file)
        if fallback.get("DATALENS_ORG_ID"):
            config = replace(config, org_id=fallback["DATALENS_ORG_ID"], org_id_source="fallback_env_file")
    if not config.org_id:
        raise SystemExit("DataLens organization ID is missing")
    client = DataLensApiClient(config)
    receipts = []
    provider_methods: list[str] = []
    for locator in args.dashboard:
        dashboard_id = parse_target_url(locator) or str(locator).strip()
        contract = {
            "mode": "review",
            "target": {"dashboard_id": dashboard_id, "object_ids": [dashboard_id]},
            "scope": {"allowed_objects": [dashboard_id]},
            "acceptance": [],
        }
        try:
            discovery = TargetDiscoveryService(client, max_objects=args.max_objects).discover(
                contract,
                target_url=locator,
            )
        except Exception as exc:  # noqa: BLE001
            receipts.append(
                {
                    "dashboard_id_hash": canonical_hash(dashboard_id),
                    "status": "discovery_error",
                    "error_family": exc.__class__.__name__,
                }
            )
            continue
        provider_methods.extend(str(item.get("method") or "") for item in discovery.get("provider_calls") or [])
        if discovery.get("status") != "success":
            receipts.append(
                {
                    "dashboard_id_hash": canonical_hash(dashboard_id),
                    "status": "discovery_blocked",
                    "reason_hash": canonical_hash(str(discovery.get("reason") or "")),
                }
            )
            continue
        graph = dict(discovery["target_graph"])
        parameter_defaults = extract_dashboard_parameter_defaults(discovery.get("baselines") or {})
        datasets = [
            item for item in graph.get("nodes") or [] if isinstance(item, dict) and item.get("object_type") == "dataset"
        ]
        dataset_receipts = []
        for dataset in datasets:
            dataset_id = str(dataset.get("object_id") or "")
            scoped_contract = {
                **contract,
                "target": {
                    "workbook_id": str((discovery.get("target_binding") or {}).get("workbook_id") or ""),
                    "dashboard_id": dashboard_id,
                    "object_ids": [dataset_id],
                },
                "scope": {"allowed_objects": [dataset_id]},
            }
            planned = DatasetProbePlanner().plan(
                scoped_contract,
                graph,
                mode=args.mode,
                limit=max(1, min(200, int(args.limit))),
                parameter_defaults={} if args.mode == "diagnostic_probe" else parameter_defaults,
            )
            if not planned.get("ok"):
                dataset_receipts.append(
                    {
                        "dataset_id_hash": canonical_hash(dataset_id),
                        "status": "plan_blocked",
                        "issue_hashes": [canonical_hash(str(item)) for item in planned.get("issues") or []],
                    }
                )
                continue
            plan = dict(planned["plan"])
            query = dict(plan["queries"][0])
            payload = dict(query["payload"])
            try:
                response = client.rpc_readonly("getDatasetData", payload)
                provider_methods.append("getDatasetData")
                observed_at = _utc_now()
                normalized = normalize_dataset_data_response(
                    response,
                    request_hash=str(query.get("query_hash") or canonical_hash(payload)),
                    observed_at=observed_at,
                )
                rows = list(normalized.get("plain_rows") or [])
                profile = build_dataset_context_profile(
                    dataset_id=dataset_id,
                    workbook_id=str(scoped_contract["target"]["workbook_id"]),
                    dataset_revision=str(plan.get("dataset_revision") or ""),
                    query_set_hash=str(plan.get("query_set_hash") or ""),
                    schema_hash=str(normalized.get("schema_hash") or plan.get("dataset_schema_hash") or ""),
                    field_catalog=list(plan.get("field_catalog") or []),
                    rows=rows,
                    pages_read=1,
                    requested_limit=int(payload.get("limit") or args.limit),
                    deterministic=bool((query.get("paging") or {}).get("deterministic")),
                    limitations=list(plan.get("limitations") or []),
                    observed_at=observed_at,
                )
            except Exception as exc:  # noqa: BLE001
                failure = dataset_failure_receipt(exc)
                dataset_receipts.append(
                    {
                        "dataset_id_hash": canonical_hash(dataset_id),
                        "status": failure["error_family"],
                        "query_hash": query.get("query_hash"),
                        **failure,
                        "requested_parameter_count": len(payload.get("params") or []),
                        "dataset_data_semantics": "unknown_experimental",
                    }
                )
                continue
            parse_statuses: dict[str, int] = {}
            for row in normalized.get("typed_rows") or []:
                for value in row.values():
                    if isinstance(value, dict):
                        status = str(value.get("parse_status") or "unknown")
                        parse_statuses[status] = parse_statuses.get(status, 0) + 1
            receipt = {
                "dataset_id_hash": canonical_hash(dataset_id),
                "dataset_revision_hash": canonical_hash(str(plan.get("dataset_revision") or "")),
                "status": "success",
                "query_hash": query.get("query_hash"),
                "query_set_hash": plan.get("query_set_hash"),
                "schema_hash": normalized.get("schema_hash"),
                "profile_hash": profile.get("profile_hash"),
                "requested_column_count": len(payload.get("columns") or []),
                "requested_parameter_count": len(payload.get("params") or []),
                "response_schema_count": len(normalized.get("schema") or []),
                "row_count": normalized.get("row_count"),
                "parse_statuses": dict(sorted(parse_statuses.items())),
                "field_type_counts": _counts(item.get("type") for item in profile.get("fields") or []),
                "role_counts": _counts(
                    role for item in profile.get("fields") or [] for role in item.get("role_candidates") or []
                ),
                "selector_candidate_count": len(profile.get("selector_candidates") or []),
                "quality_finding_counts": _counts(item.get("kind") for item in profile.get("quality_findings") or []),
                "sample_scope": profile.get("sample_scope"),
                "admissible_claims": profile.get("admissible_claims"),
                "forbidden_claims": profile.get("forbidden_claims"),
                "dataset_data_semantics": profile.get("dataset_data_semantics"),
                "raw_rows_inline": profile.get("raw_rows_inline"),
                "probe_mode": args.mode,
            }
            if args.mode == "assertion_probe":
                assertion = evaluate_data_assertions(
                    assertions=[{"kind": "not_empty", "scope": "sample"}],
                    schema=list(normalized.get("schema") or []),
                    rows=rows,
                    paging={
                        "complete": len(rows) < int(payload.get("limit") or args.limit),
                        "pages_read": 1,
                        "bounded_sample": True,
                    },
                )
                receipt["assertion"] = {
                    "kind": "not_empty",
                    "status": assertion["status"],
                    "passed": assertion["passed"],
                    "failed": assertion["failed"],
                    "raw_rows_inline": False,
                }
                if not assertion["ok"]:
                    receipt["status"] = "assertion_failed"
            elif args.mode == "diagnostic_probe":
                receipt["diagnostic"] = {
                    "status": "data_visible" if rows else "still_empty",
                    "dashboard_parameters_removed": True,
                    "requested_parameter_count": len(payload.get("params") or []),
                    "raw_rows_inline": False,
                }
            dataset_receipts.append(receipt)
        receipts.append(
            {
                "dashboard_id_hash": canonical_hash(dashboard_id),
                "status": "success" if dataset_receipts else "no_dataset_dependency",
                "target_graph_hash": graph.get("graph_hash"),
                "dataset_count": len(datasets),
                "dataset_receipts": dataset_receipts,
            }
        )
    result = {
        "schema_id": "datalens_dataset_data_context_canary",
        "observed_at": _utc_now(),
        "read_only": True,
        "probe_mode": args.mode,
        "dashboard_count": len(args.dashboard),
        "successful_dataset_probe_count": sum(
            item.get("status") == "success"
            for dashboard in receipts
            for item in dashboard.get("dataset_receipts") or []
        ),
        "provider_method_counts": _counts(provider_methods),
        "write_method_count": sum(
            method.lower().startswith(("create", "update", "delete", "publish")) for method in provider_methods
        ),
        "dashboards": receipts,
    }
    result["receipt_hash"] = canonical_hash(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": bool(result["successful_dataset_probe_count"] >= 2 and result["write_method_count"] == 0),
                "dashboard_count": result["dashboard_count"],
                "successful_dataset_probe_count": result["successful_dataset_probe_count"],
                "write_method_count": result["write_method_count"],
                "receipt_hash": result["receipt_hash"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["successful_dataset_probe_count"] >= 2 and result["write_method_count"] == 0 else 1


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
