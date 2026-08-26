from __future__ import annotations

from typing import Any, Callable

from datalens_dev_mcp.editor.protected_regions import validate_protected_regions
from datalens_dev_mcp.pipeline.semantic_patch import (
    apply_target_sections,
    canonical_hash,
    section_value,
    target_payload,
    validate_semantic_patch_plan,
)


def preflight_semantic_patch_batch(
    plan: dict[str, Any],
    *,
    fresh_targets: dict[str, dict[str, Any]],
    value_resolver: Callable[[str], Any] | None = None,
    payload_validator: Callable[[str, Any], list[str]] | None = None,
) -> dict[str, Any]:
    issues = validate_semantic_patch_plan(plan)
    target_results: list[dict[str, Any]] = []
    materialized: dict[str, Any] = {}
    plan_target_ids = {str(item.get("object_id") or "") for item in plan.get("targets") or []}
    for target in plan.get("targets") or []:
        object_id = str(target.get("object_id") or "")
        target_issues: list[str] = []
        fresh = fresh_targets.get(object_id)
        if not isinstance(fresh, dict):
            target_issues.append("target does not exist in fresh read batch")
            target_results.append(_target_result(target, target_issues))
            issues.extend(f"target {object_id}: {item}" for item in target_issues)
            continue
        actual_type = str(fresh.get("object_type") or target.get("object_type") or "")
        if actual_type != str(target.get("object_type") or ""):
            target_issues.append("object type mismatch")
        dependencies = set(target.get("dependencies") or [])
        missing_dependencies = sorted(dependencies - set(fresh_targets) - plan_target_ids)
        if missing_dependencies:
            target_issues.append("missing object graph dependencies: " + ", ".join(missing_dependencies))
        payload = target_payload(fresh)
        actual_revision = _revision(fresh)
        revision_match = str(actual_revision) == str(target.get("saved_revision"))
        hash_match = canonical_hash(payload) == str(target.get("saved_hash") or "")
        already_applied = canonical_hash(payload) == str(target.get("expected_after_hash") or "")
        if already_applied:
            target_results.append(
                {
                    **_target_result(target, target_issues),
                    "ok": not target_issues,
                    "status": "already_applied",
                    "active_section_count": 0,
                    "noop_section_count": len(target.get("sections") or []),
                    "after_hash": canonical_hash(payload),
                }
            )
            materialized[object_id] = payload
            issues.extend(f"target {object_id}: {item}" for item in target_issues)
            continue
        if not revision_match or not hash_match:
            target_issues.append("saved revision/hash mismatch; fresh read and recovery plan required")
            target_results.append(
                {
                    **_target_result(target, target_issues),
                    "status": "stale",
                    "recovery_required": True,
                }
            )
            issues.extend(f"target {object_id}: {item}" for item in target_issues)
            continue
        try:
            applied = apply_target_sections(payload, target, value_resolver=value_resolver)
        except ValueError as exc:
            target_issues.append(str(exc))
            target_results.append(_target_result(target, target_issues))
            issues.extend(f"target {object_id}: {item}" for item in target_issues)
            continue
        protected = list(target.get("protected_regions") or [])
        if protected:
            before_tabs = _tabs(payload)
            after_tabs = _tabs(applied["payload"])
            protected_result = validate_protected_regions(before_tabs, after_tabs, protected)
            if not protected_result["ok"]:
                target_issues.append("protected region change rejected")
        if payload_validator is not None:
            target_issues.extend(payload_validator(str(target.get("object_type") or ""), applied["payload"]))
        active = sum(not item["noop"] for item in applied["sections"])
        noop = len(applied["sections"]) - active
        if applied["after_hash"] != str(target.get("expected_after_hash") or ""):
            target_issues.append("full expected after-hash mismatch")
        materialized[object_id] = applied["payload"]
        target_results.append(
            {
                **_target_result(target, target_issues),
                "status": "ready" if active else "noop",
                "active_section_count": active,
                "noop_section_count": noop,
                "after_hash": applied["after_hash"],
            }
        )
        issues.extend(f"target {object_id}: {item}" for item in target_issues)
    return {
        "ok": not issues,
        "status": "ready" if not issues else "blocked",
        "issues": issues,
        "targets": target_results,
        "materialized_payloads": materialized if not issues else {},
        "write_count": 0,
        "all_targets_preflighted": len(target_results) == len(plan.get("targets") or []),
    }


def verify_semantic_patch_readback(
    plan: dict[str, Any],
    *,
    readback_targets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mismatches: list[dict[str, str]] = []
    for target in plan.get("targets") or []:
        object_id = str(target.get("object_id") or "")
        readback = readback_targets.get(object_id)
        actual_hash = canonical_hash(target_payload(readback)) if isinstance(readback, dict) else ""
        expected_hash = str(target.get("expected_after_hash") or "")
        if actual_hash != expected_hash:
            mismatches.append(
                {"object_id": object_id, "expected_after_hash": expected_hash, "actual_hash": actual_hash}
            )
    return {
        "ok": not mismatches,
        "status": "verified" if not mismatches else "mismatch",
        "mismatches": mismatches,
        "verified_target_count": len(plan.get("targets") or []) - len(mismatches),
    }


def _target_result(target: dict[str, Any], issues: list[str]) -> dict[str, Any]:
    return {
        "object_id": str(target.get("object_id") or ""),
        "object_type": str(target.get("object_type") or ""),
        "ok": not issues,
        "status": "ready" if not issues else "blocked",
        "issues": list(issues),
        "recovery_required": False,
    }


def _revision(value: dict[str, Any]) -> Any:
    for key in ("saved_revision", "revision", "revId", "revisionId"):
        if key in value:
            return value[key]
    payload = target_payload(value)
    if isinstance(payload, dict):
        for key in ("revId", "revision", "revisionId"):
            if key in payload:
                return payload[key]
    return None


def _tabs(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("tabs"), dict):
        return {str(key): str(value) for key, value in payload["tabs"].items()}
    candidates = payload.get("data")
    if not isinstance(candidates, dict) and isinstance(payload.get("entry"), dict):
        candidates = payload["entry"].get("data")
    if not isinstance(candidates, dict):
        return {}
    suffix = {"meta": ".json", "params": ".js", "sources": ".js", "controls": ".js", "prepare": ".js", "config": ".js"}
    return {f"{key}{suffix.get(str(key), '')}": str(value) for key, value in candidates.items()}
