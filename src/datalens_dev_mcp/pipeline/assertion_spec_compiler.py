from __future__ import annotations

import json
from typing import Any

from datalens_dev_mcp.pipeline.data_assertions import ASSERTION_KINDS
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


ALIASES = {
    "row_count_range": "row_count_between",
    "selector_domain": "value_domain",
    "sort_order": "sort_total_order",
    "aggregation_consistency": "ratio_consistency",
}


class AssertionSpecCompiler:
    def compile(
        self,
        contract: dict[str, Any],
        probe_plan: dict[str, Any],
        *,
        planning_profile: dict[str, Any],
        target_binding: dict[str, Any],
    ) -> dict[str, Any]:
        queries = list(probe_plan.get("queries") or [])
        if not queries:
            return _blocked("assertion probe plan has no query")
        query = dict(queries[0])
        payload = dict(query.get("payload") or {})
        assertions: list[dict[str, Any]] = []
        issues: list[str] = []
        for acceptance_index, criterion in enumerate(contract.get("acceptance") or []):
            if not isinstance(criterion, dict) or criterion.get("hard") is False:
                continue
            kind = ALIASES.get(str(criterion.get("kind") or ""), str(criterion.get("kind") or ""))
            if kind not in ASSERTION_KINDS:
                continue
            parsed = _criterion_payload(str(criterion.get("statement") or ""))
            assertion = {
                "kind": kind,
                **parsed,
                "acceptance_index": acceptance_index,
                "criterion_hash": canonical_hash(
                    {
                        "kind": str(criterion.get("kind") or ""),
                        "statement": str(criterion.get("statement") or ""),
                        "hard": bool(criterion.get("hard", True)),
                    }
                ),
            }
            assertion.setdefault("scope", "population")
            assertions.append(assertion)
        if not assertions:
            assertions = [{"kind": "not_empty", "scope": "sample"}]
        expected_empty = any(item.get("kind") == "expected_empty" for item in assertions)
        if not expected_empty and not any(item.get("kind") == "not_empty" for item in assertions):
            assertions.insert(0, {"kind": "not_empty", "scope": "sample"})
        known = {str(item.get("guid") or "") for item in probe_plan.get("field_catalog") or []}
        for assertion in assertions:
            for field in _assertion_fields(assertion):
                if field and field not in known:
                    issues.append(f"assertion references unknown field GUID: {field}")
        spec = {
            "schema_id": "task_data_proof_plan",
            "spec_version": 1,
            "task_id": str(contract.get("task_id") or ""),
            "contract_hash": str(contract.get("contract_hash") or ""),
            "target_binding_hash": str(target_binding.get("binding_hash") or ""),
            "planning_profile_hash": str(planning_profile.get("profile_hash") or ""),
            "planning_query_set_hash": str(planning_profile.get("query_set_hash") or ""),
            "planning_schema_hash": str(planning_profile.get("schema_hash") or ""),
            "dataset_id": str(probe_plan.get("dataset_id") or payload.get("datasetId") or ""),
            "workbook_id": str(payload.get("workbookId") or ""),
            "columns": list(payload.get("columns") or []),
            "filters": list(payload.get("filters") or []),
            "params": list(payload.get("params") or []),
            "sort": list(payload.get("sort") or []),
            "tie_breaker_fields": list((query.get("paging") or {}).get("tie_breaker_fields") or []),
            "sample": {"limit": int(payload.get("limit") or 100), "max_pages": 1},
            "budget": {
                "max_rows": 2000,
                "max_cells": 20000,
                "max_bytes": 1000000,
                "inline_examples": 0,
                "inline_bytes": 0,
            },
            "assertions": assertions,
            "dataset_data_semantics": "unknown_experimental",
            "fresh_required": True,
            "issues": sorted(set(issues)),
        }
        spec["plan_hash"] = canonical_hash(spec)
        spec["ok"] = not issues
        spec["status"] = "ready" if not issues else "blocked"
        return spec


def _criterion_payload(statement: str) -> dict[str, Any]:
    try:
        value = json.loads(statement)
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _assertion_fields(assertion: dict[str, Any]) -> list[str]:
    fields = list(assertion.get("fields") or [])
    fields.extend(
        str(assertion.get(key) or "")
        for key in ("field", "numerator", "denominator", "ratio")
        if assertion.get(key)
    )
    return [str(item) for item in fields if str(item)]


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "schema_id": "task_data_proof_plan",
        "spec_version": 1,
        "ok": False,
        "status": "blocked",
        "issues": [reason],
    }
