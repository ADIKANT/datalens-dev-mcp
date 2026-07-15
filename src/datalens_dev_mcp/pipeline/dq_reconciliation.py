from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import write_json, write_text


CLASSIFICATION_BUCKETS = (
    "ok_exact_dm",
    "ok_rk_renumbered",
    "source_status_conflict",
    "missing_raw",
    "missing_current_edm_order",
    "missing_edm_item_amount",
    "missing_dm_amount",
    "dashboard_logic_issue",
    "extra_dashboard_row",
)
UPSTREAM_CONTRADICTION_BUCKETS = {
    "source_status_conflict",
    "missing_raw",
    "missing_current_edm_order",
    "missing_edm_item_amount",
    "missing_dm_amount",
}
SENSITIVE_KEYS = {"raw_rows", "rows", "full_rows", "token", "authorization", "cookie", "password", "secret", "iam"}


def ingest_dq_control_summary(
    project_root: str | Path,
    control_summary: dict[str, Any],
    *,
    source_name: str = "control_file",
) -> dict[str, Any]:
    root = Path(project_root)
    sanitized = _sanitize_control_summary(control_summary)
    artifact = {
        "schema_version": "2026-06-11.dq_control_summary.v1",
        "ingested_at": _now(),
        "source_name": source_name,
        "raw_control_file_committed": False,
        "control_summary": sanitized,
        "omitted_keys": sorted(key for key in control_summary if key.lower() in SENSITIVE_KEYS),
    }
    target = root / "reports" / "dq" / "control_summary.json"
    write_json(target, artifact)
    write_text(
        root / "requirements" / "dq_reconciliation.md",
        "# DQ Reconciliation\n\n"
        f"- Control summary: `{target}`\n"
        "- Raw control files are not stored in the project.\n",
    )
    return {"ok": True, "artifact_path": str(target), **artifact}


def build_dq_layer_reconciliation_plan(
    project_root: str | Path = ".",
    control_summary: dict[str, Any] | None = None,
    identity_keys: dict[str, Any] | None = None,
    layers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    identity = identity_keys or {}
    strict_key = str(identity.get("strict_business_key") or "business_key")
    stable_key = str(identity.get("stable_rk_key") or identity.get("stable_key") or "stable_rk")
    resolved_key = str(identity.get("resolved_key") or stable_key)
    default_layers = [
        {"name": "control_baseline", "role": "baseline", "required_evidence": ["row_count", "amount_total"]},
        {"name": "raw", "role": "source_presence", "required_evidence": [strict_key, stable_key]},
        {"name": "edm_history", "role": "history_identity", "required_evidence": [strict_key, stable_key, "status"]},
        {"name": "edm_current", "role": "current_status", "required_evidence": [stable_key, "current_status"]},
        {"name": "dm", "role": "mart_amount", "required_evidence": [resolved_key, "dm_amount"]},
        {"name": "dashboard", "role": "reproduction", "required_evidence": [resolved_key, "dashboard_amount"]},
    ]
    plan = {
        "ok": True,
        "schema_version": "2026-06-11.dq_layer_reconciliation_plan.v1",
        "project_root": str(Path(project_root)),
        "control_summary": _sanitize_control_summary(control_summary or {}),
        "identity_keys": {
            "strict_business_key": strict_key,
            "stable_rk_key": stable_key,
            "resolved_key": resolved_key,
        },
        "layers": layers or default_layers,
        "classification_buckets": list(CLASSIFICATION_BUCKETS),
        "evidence_policy": {
            "raw_files_committed": False,
            "provider_label": "read-only metadata/data evidence provider",
            "dashboard_fix_guard": "dashboard-side fixes are blocked when upstream evidence contradicts the control baseline",
        },
        "next_steps": [
            "Record sanitized control totals only.",
            "Probe each layer by strict business key and stable RK/resolved key.",
            "Classify records with dl_classify_dq_reconciliation.",
            "Use dl_build_dq_before_after_report before dashboard-side fixes.",
        ],
    }
    target = Path(project_root) / "reports" / "dq" / "layer_reconciliation_plan.json"
    write_json(target, plan)
    plan["artifact_path"] = str(target)
    return plan


def classify_dq_reconciliation(
    control_records: list[dict[str, Any]],
    evidence_records: list[dict[str, Any]],
    *,
    strict_business_key: str = "business_key",
    stable_key: str = "stable_rk",
    amount_field: str = "amount",
) -> dict[str, Any]:
    evidence_by_stable = {str(item.get(stable_key) or ""): item for item in evidence_records if item.get(stable_key)}
    evidence_by_business = {str(item.get(strict_business_key) or ""): item for item in evidence_records if item.get(strict_business_key)}
    rows: list[dict[str, Any]] = []
    bucket_totals = _empty_bucket_totals()
    matched_evidence_ids: set[int] = set()
    defects: list[dict[str, Any]] = []

    for control in control_records:
        control_business = str(control.get(strict_business_key) or "").strip()
        control_stable = str(control.get(stable_key) or "").strip()
        evidence = evidence_by_stable.get(control_stable) or evidence_by_business.get(control_business) or {}
        if evidence:
            matched_evidence_ids.add(id(evidence))
        bucket = _classify_control_record(
            control,
            evidence,
            strict_business_key=strict_business_key,
            stable_key=stable_key,
            amount_field=amount_field,
        )
        baseline_amount = _number(control.get(amount_field))
        dashboard_amount = _number(evidence.get("dashboard_amount", evidence.get(amount_field, 0))) if evidence else 0.0
        bucket_totals[bucket]["count"] += 1
        bucket_totals[bucket]["baseline_amount"] += baseline_amount
        bucket_totals[bucket]["dashboard_amount"] += dashboard_amount
        row = {
            "strict_business_key": control_business,
            "stable_rk": control_stable,
            "bucket": bucket,
            "baseline_amount": baseline_amount,
            "dashboard_amount": dashboard_amount,
        }
        if evidence and str(evidence.get(strict_business_key) or "") != control_business:
            row["resolved_by_stable_rk"] = True
        rows.append(row)
        if evidence.get("fallback_duplicate") or _number(evidence.get("dashboard_row_count")) > 1:
            defects.append(
                {
                    "type": "fallback_duplicate",
                    "strict_business_key": control_business,
                    "stable_rk": control_stable,
                    "dashboard_row_count": int(_number(evidence.get("dashboard_row_count")) or 0),
                }
            )

    for evidence in evidence_records:
        if id(evidence) in matched_evidence_ids:
            continue
        dashboard_amount = _number(evidence.get("dashboard_amount", evidence.get(amount_field, 0)))
        bucket_totals["extra_dashboard_row"]["count"] += 1
        bucket_totals["extra_dashboard_row"]["dashboard_amount"] += dashboard_amount
        rows.append(
            {
                "strict_business_key": str(evidence.get(strict_business_key) or ""),
                "stable_rk": str(evidence.get(stable_key) or ""),
                "bucket": "extra_dashboard_row",
                "baseline_amount": 0.0,
                "dashboard_amount": dashboard_amount,
            }
        )

    bridge = _amount_count_bridge(bucket_totals)
    upstream_conflicts = [
        bucket for bucket, totals in bucket_totals.items() if bucket in UPSTREAM_CONTRADICTION_BUCKETS and totals["count"]
    ]
    return {
        "ok": bridge["baseline_reconciles"] and bridge["dashboard_reconciles"],
        "schema_version": "2026-06-11.dq_reconciliation.v1",
        "classification_buckets": bucket_totals,
        "classified_rows": rows,
        "amount_count_bridge": bridge,
        "defects": defects,
        "dashboard_fix_guard": {
            "dashboard_fix_allowed": not upstream_conflicts,
            "blocked_by_buckets": upstream_conflicts,
            "message": (
                "Dashboard-only fix is blocked because upstream evidence contradicts the control baseline."
                if upstream_conflicts
                else "Dashboard-side fix can be considered if dashboard_logic_issue remains after upstream evidence review."
            ),
        },
    }


def build_dq_before_after_report(
    project_root: str | Path,
    before: dict[str, Any],
    after: dict[str, Any] | None = None,
    *,
    fix_scope: str = "dashboard",
    approved_upstream_override: bool = False,
) -> dict[str, Any]:
    before_guard = before.get("dashboard_fix_guard") if isinstance(before.get("dashboard_fix_guard"), dict) else {}
    blocked = (
        fix_scope == "dashboard"
        and not approved_upstream_override
        and before_guard.get("dashboard_fix_allowed") is False
    )
    report = {
        "ok": not blocked,
        "schema_version": "2026-06-11.dq_before_after_report.v1",
        "generated_at": _now(),
        "fix_scope": fix_scope,
        "before": _report_summary(before),
        "after": _report_summary(after or {}),
        "dashboard_fix_guard": {
            "blocked": blocked,
            "blocked_by_buckets": before_guard.get("blocked_by_buckets") or [],
            "message": (
                "Do not adjust dashboard logic just to match the control baseline while upstream evidence contradicts it."
                if blocked
                else "Guard passed for the requested fix scope."
            ),
        },
        "raw_control_data_included": False,
    }
    target = Path(project_root) / "reports" / "dq" / "before_after_report.json"
    write_json(target, report)
    report["artifact_path"] = str(target)
    return report


def _classify_control_record(
    control: dict[str, Any],
    evidence: dict[str, Any],
    *,
    strict_business_key: str,
    stable_key: str,
    amount_field: str,
) -> str:
    if not evidence or evidence.get("raw_present") is False:
        return "missing_raw"
    if evidence.get("source_status_conflict"):
        return "source_status_conflict"
    if evidence.get("current_edm_present") is False:
        return "missing_current_edm_order"
    if evidence.get("edm_item_amount") is None:
        return "missing_edm_item_amount"
    if evidence.get("dm_amount") is None:
        return "missing_dm_amount"
    baseline_amount = _number(control.get(amount_field))
    dm_amount = _number(evidence.get("dm_amount"))
    dashboard_amount = _number(evidence.get("dashboard_amount", dm_amount))
    if abs(dm_amount - baseline_amount) > 0.000001 or abs(dashboard_amount - dm_amount) > 0.000001:
        return "dashboard_logic_issue"
    evidence_business = str(evidence.get(strict_business_key) or "")
    control_business = str(control.get(strict_business_key) or "")
    evidence_stable = str(evidence.get(stable_key) or "")
    control_stable = str(control.get(stable_key) or "")
    if evidence_business != control_business and evidence_stable == control_stable:
        return "ok_rk_renumbered"
    return "ok_exact_dm"


def _amount_count_bridge(bucket_totals: dict[str, dict[str, float]]) -> dict[str, Any]:
    baseline_amount = sum(item["baseline_amount"] for item in bucket_totals.values())
    dashboard_amount = sum(item["dashboard_amount"] for item in bucket_totals.values())
    control_count = sum(item["count"] for bucket, item in bucket_totals.items() if bucket != "extra_dashboard_row")
    dashboard_count = control_count + bucket_totals["extra_dashboard_row"]["count"]
    adjustments = []
    for bucket, totals in bucket_totals.items():
        amount_delta = totals["dashboard_amount"] - totals["baseline_amount"]
        count_delta = (totals["count"] if bucket == "extra_dashboard_row" else 0)
        if amount_delta or count_delta:
            adjustments.append({"bucket": bucket, "amount_delta": amount_delta, "count_delta": count_delta})
    return {
        "baseline_count": control_count,
        "dashboard_reproduction_count": dashboard_count,
        "baseline_amount": baseline_amount,
        "dashboard_reproduction_amount": dashboard_amount,
        "adjustments": adjustments,
        "bridged_amount": baseline_amount + sum(item["amount_delta"] for item in adjustments),
        "bridged_count": control_count + sum(item["count_delta"] for item in adjustments),
        "baseline_reconciles": abs(sum(item["baseline_amount"] for item in bucket_totals.values()) - baseline_amount) < 0.000001,
        "dashboard_reconciles": abs(
            baseline_amount + sum(item["amount_delta"] for item in adjustments) - dashboard_amount
        )
        < 0.000001,
    }


def _empty_bucket_totals() -> dict[str, dict[str, float]]:
    return {bucket: {"count": 0, "baseline_amount": 0.0, "dashboard_amount": 0.0} for bucket in CLASSIFICATION_BUCKETS}


def _sanitize_control_summary(summary: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in summary.items():
        if key.lower() in SENSITIVE_KEYS:
            continue
        if isinstance(value, dict):
            sanitized[key] = _sanitize_control_summary(value)
        elif isinstance(value, list):
            sanitized[key] = {"omitted_list_count": len(value)}
        else:
            sanitized[key] = value
    return sanitized


def _report_summary(payload: dict[str, Any]) -> dict[str, Any]:
    bridge = payload.get("amount_count_bridge") if isinstance(payload.get("amount_count_bridge"), dict) else {}
    return {
        "ok": bool(payload.get("ok")),
        "baseline_amount": bridge.get("baseline_amount", 0),
        "dashboard_reproduction_amount": bridge.get("dashboard_reproduction_amount", 0),
        "bucket_counts": {
            bucket: totals.get("count", 0)
            for bucket, totals in (payload.get("classification_buckets") or {}).items()
            if isinstance(totals, dict)
        },
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
