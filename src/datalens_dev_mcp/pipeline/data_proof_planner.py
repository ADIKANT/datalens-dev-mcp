from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.data_assertions import (
    ASSERTION_KINDS,
    evaluate_data_assertions,
    unexpected_empty_diagnostics,
)
from datalens_dev_mcp.pipeline.data_sample_budget import DataSampleBudget, enforce_sample_budget, externalize_data_sample
from datalens_dev_mcp.pipeline.dataset_preview import compile_dataset_preview_request, extract_dataset_fields, preview_dataset_data
from datalens_dev_mcp.pipeline.selector_semantics import validate_selector_semantics
from datalens_dev_mcp.pipeline.artifacts import write_json


def build_data_proof_plan(spec: dict[str, Any], *, dataset_fields: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(spec, dict):
        return _blocked(["spec must be an object"])
    assertions = spec.get("assertions") or []
    if not isinstance(assertions, list) or not assertions:
        issues.append("assertions must contain at least one typed assertion")
    else:
        unknown = sorted(
            {str(item.get("kind") or "") for item in assertions if isinstance(item, dict)} - ASSERTION_KINDS
        )
        if unknown:
            issues.append("unsupported assertion kinds: " + ", ".join(unknown))
    sample = spec.get("sample") or {}
    budget_config = spec.get("budget") or {}
    limit = int(sample.get("limit", 100))
    max_pages = int(sample.get("max_pages", 1))
    max_rows = int(budget_config.get("max_rows", 5_000))
    max_cells = int(budget_config.get("max_cells", 50_000))
    if limit * max_pages > max_rows:
        issues.append(f"requested sample can exceed row budget: {limit * max_pages} > {max_rows}")
    if limit * max_pages * len(spec.get("columns") or []) > max_cells:
        issues.append("requested sample can exceed cell budget")
    declared_tie_breakers = [str(item) for item in spec.get("tie_breaker_fields") or []]
    known_unique = {
        str(item.get("guid") or "")
        for item in dataset_fields
        if isinstance(item, dict) and bool(item.get("unique") or item.get("isUnique"))
    }
    if max_pages > 1 and declared_tie_breakers and not set(declared_tie_breakers).issubset(known_unique):
        issues.append("multi-page proof requires tie-breaker fields proven unique by saved dataset schema")
    compiled = compile_dataset_preview_request(
        dataset_id=str(spec.get("dataset_id") or ""),
        workbook_id=str(spec.get("workbook_id") or ""),
        columns=[str(item) for item in spec.get("columns") or []],
        dataset_fields=dataset_fields,
        filters=spec.get("filters") or [],
        params=spec.get("params") or [],
        sort=spec.get("sort") or [],
        limit=limit,
        offset=0,
        max_pages=max_pages,
        tie_breaker_fields=spec.get("tie_breaker_fields") or [],
    )
    issues.extend(compiled.get("issues") or [])
    selector = validate_selector_semantics(
        spec.get("selectors") or [], filters=spec.get("filters") or [], current_domains=spec.get("selector_domains") or {}
    )
    issues.extend(item["message"] for item in selector["issues"] if item["severity"] == "error")
    return {
        "schema_id": "data_proof_plan",
        "ok": not issues,
        "status": "ready" if not issues else "blocked",
        "issues": issues,
        "dataset_id": str(spec.get("dataset_id") or ""),
        "request": compiled.get("payload") or {},
        "paging": compiled.get("paging") or {},
        "assertions": assertions,
        "selector_semantics": selector,
        "privacy_policy": "full rows only in ignored local artifact; inline output contains aggregates and redacted examples",
    }


def prove_dataset_data(
    spec: dict[str, Any],
    *,
    project_root: str | Path = ".",
    client: Any | None = None,
    dataset_readback: dict[str, Any] | None = None,
    artifact_name: str = "data-proof",
) -> dict[str, Any]:
    if client is None:
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        client = DataLensApiClient(DataLensConfig.from_env())
    try:
        readback = dataset_readback or client.rpc_readonly(
            "getDataset", {"datasetId": str(spec.get("dataset_id") or ""), "branch": "saved"}
        )
    except Exception as exc:  # provider boundary: report evidence gap without claiming success
        return _fallback_result(spec, [], f"saved dataset readback failed: {type(exc).__name__}")
    fields = extract_dataset_fields(readback)
    plan = build_data_proof_plan(spec, dataset_fields=fields)
    if not plan["ok"]:
        return {
            **plan,
            "schema_id": "data_assertion_result",
            "live_data_verified": False,
            "proof_level": "source_static",
            "results": [],
        }
    try:
        preview = preview_dataset_data(
            dataset_id=spec["dataset_id"],
            workbook_id=spec.get("workbook_id", ""),
            columns=spec["columns"],
            filters=spec.get("filters") or [],
            params=spec.get("params") or [],
            sort=spec.get("sort") or [],
            limit=int((spec.get("sample") or {}).get("limit", 100)),
            max_pages=int((spec.get("sample") or {}).get("max_pages", 1)),
            tie_breaker_fields=spec.get("tie_breaker_fields") or [],
            inline_row_limit=0,
            project_root=project_root,
            artifact_name=f"{artifact_name}-preview",
            client=client,
            dataset_readback=readback,
        )
    except Exception as exc:  # experimental endpoint can be missing or unstable
        return _fallback_result(spec, fields, f"getDatasetData failed: {type(exc).__name__}")
    if not preview.get("ok"):
        return _fallback_result(spec, fields, str((preview.get("error") or {}).get("message") or preview.get("status")))
    artifact = json.loads(Path(preview["artifact_path"]).read_text(encoding="utf-8"))
    rows = artifact.get("rows") if isinstance(artifact.get("rows"), list) else []
    schema = artifact.get("schema") if isinstance(artifact.get("schema"), list) else []
    page_receipts = preview.get("page_receipts") or []
    limit = int((spec.get("sample") or {}).get("limit", 100))
    max_pages = int((spec.get("sample") or {}).get("max_pages", 1))
    last_count = int(page_receipts[-1]["row_count"]) if page_receipts else 0
    paging = {
        **(preview.get("paging") or {}),
        "complete": bool(last_count < limit or len(page_receipts) < max_pages),
        "pages_read": len(page_receipts),
    }
    budget_config = spec.get("budget") or {}
    budget = DataSampleBudget(
        max_rows=int(budget_config.get("max_rows", 5_000)),
        max_cells=int(budget_config.get("max_cells", 50_000)),
        max_bytes=int(budget_config.get("max_bytes", 2_000_000)),
        inline_examples=int(budget_config.get("inline_examples", 3)),
        inline_bytes=int(budget_config.get("inline_bytes", 8_000)),
    )
    sample_evidence = enforce_sample_budget(rows, schema=schema, budget=budget)
    externalized = externalize_data_sample(
        project_root=project_root,
        dataset_id=spec["dataset_id"],
        schema=schema,
        rows=rows,
        artifact_name=artifact_name,
    )
    assertions = evaluate_data_assertions(
        assertions=spec.get("assertions") or [],
        schema=schema,
        rows=rows,
        paging=paging,
        selector_domains=spec.get("selector_domains") or {},
    )
    expected_empty = any(item.get("kind") == "expected_empty" for item in spec.get("assertions") or [])
    diagnostics = [] if rows or expected_empty else unexpected_empty_diagnostics(spec)
    ok = bool(assertions["ok"] and sample_evidence["ok"])
    result = {
        **assertions,
        "ok": ok,
        "status": "passed" if ok else assertions["status"] if sample_evidence["ok"] else "blocked_budget",
        "live_data_verified": True,
        "proof_level": "live_read_only_api",
        "dataset_id": spec["dataset_id"],
        "schema": schema,
        "row_count": len(rows),
        "paging": paging,
        "sample_evidence": sample_evidence,
        "artifact_path": externalized["artifact_path"],
        "artifact_sha256": externalized["sha256"],
        "unexpected_empty_diagnostics": diagnostics,
        "raw_rows_inline": False,
    }
    write_json(Path(project_root) / "artifacts" / "data_assertion_result.json", result)
    return result


def _fallback_result(spec: dict[str, Any], fields: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "schema_id": "data_assertion_result",
        "ok": False,
        "status": "insufficient_evidence",
        "live_data_verified": False,
        "proof_level": "schema_static_fallback",
        "dataset_id": str(spec.get("dataset_id") or ""),
        "schema": fields,
        "reason": reason,
        "results": [
            {
                "kind": str(item.get("kind") or "unknown"),
                "status": "insufficient_evidence",
                "explanation": "Live rows were unavailable; static schema cannot prove this assertion.",
                "metrics": {},
            }
            for item in spec.get("assertions") or []
            if isinstance(item, dict)
        ],
        "fallback_evidence": ["saved dataset schema", "static filter, selector, and sort validation"],
    }


def _blocked(issues: list[str]) -> dict[str, Any]:
    return {"schema_id": "data_proof_plan", "ok": False, "status": "blocked", "issues": issues}
