from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.dq_reconciliation import (
    build_dq_before_after_report,
    build_dq_layer_reconciliation_plan,
    classify_dq_reconciliation,
    ingest_dq_control_summary,
)


def dl_ingest_dq_control_summary(
    project_root: str = ".",
    control_summary: dict[str, Any] | None = None,
    source_name: str = "control_file",
) -> dict[str, Any]:
    if not isinstance(control_summary, dict) or not control_summary:
        return {"ok": False, "error": {"category": "missing_input", "message": "control_summary is required"}}
    return ingest_dq_control_summary(project_root, control_summary, source_name=source_name)


def dl_build_dq_layer_reconciliation_plan(
    project_root: str = ".",
    control_summary: dict[str, Any] | None = None,
    identity_keys: dict[str, Any] | None = None,
    layers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_dq_layer_reconciliation_plan(
        project_root=project_root,
        control_summary=control_summary,
        identity_keys=identity_keys,
        layers=layers,
    )


def dl_classify_dq_reconciliation(
    control_records: list[dict[str, Any]] | None = None,
    evidence_records: list[dict[str, Any]] | None = None,
    strict_business_key: str = "business_key",
    stable_key: str = "stable_rk",
    amount_field: str = "amount",
) -> dict[str, Any]:
    if not isinstance(control_records, list) or not control_records:
        return {"ok": False, "error": {"category": "missing_input", "message": "control_records is required"}}
    if not isinstance(evidence_records, list):
        return {"ok": False, "error": {"category": "missing_input", "message": "evidence_records is required"}}
    return classify_dq_reconciliation(
        control_records,
        evidence_records,
        strict_business_key=strict_business_key,
        stable_key=stable_key,
        amount_field=amount_field,
    )


def dl_build_dq_before_after_report(
    project_root: str = ".",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    fix_scope: str = "dashboard",
    approved_upstream_override: bool = False,
) -> dict[str, Any]:
    if not isinstance(before, dict) or not before:
        return {"ok": False, "error": {"category": "missing_input", "message": "before is required"}}
    return build_dq_before_after_report(
        project_root,
        before,
        after,
        fix_scope=fix_scope,
        approved_upstream_override=approved_upstream_override,
    )
