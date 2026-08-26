from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.patch_anchors import anchor_hash, resolve_anchor
from datalens_dev_mcp.pipeline.semantic_patch import (
    build_semantic_patch_plan,
    section_value,
    target_payload,
)


def recover_semantic_patch_plan(
    plan: dict[str, Any],
    *,
    base_targets: dict[str, dict[str, Any]],
    fresh_targets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    recovered_targets: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for target in plan.get("targets") or []:
        object_id = str(target.get("object_id") or "")
        base = base_targets.get(object_id)
        fresh = fresh_targets.get(object_id)
        if not isinstance(base, dict) or not isinstance(fresh, dict):
            conflicts.append({"object_id": object_id, "reason": "base_or_fresh_target_missing"})
            continue
        base_payload = target_payload(base)
        fresh_payload = target_payload(fresh)
        requested_sections: list[dict[str, Any]] = []
        for section in target.get("sections") or []:
            tab = str(section.get("tab") or "")
            anchor = dict(section.get("anchor") or {})
            try:
                base_match = resolve_anchor(section_value(base_payload, tab), anchor, tab=tab)
                fresh_match = resolve_anchor(section_value(fresh_payload, tab), anchor, tab=tab)
            except ValueError as exc:
                conflicts.append({"object_id": object_id, "tab": tab, "reason": str(exc)})
                continue
            if anchor_hash(base_match.value) != anchor_hash(fresh_match.value):
                conflicts.append({"object_id": object_id, "tab": tab, "reason": "targeted_anchor_changed"})
                continue
            requested_sections.append(
                {
                    "tab": tab,
                    "anchor": {key: value for key, value in anchor.items() if key != "anchor_hash"},
                    "operation": "replace",
                    "value": section.get("value"),
                    "value_artifact": section.get("value_artifact"),
                }
            )
        recovered_targets.append(
            {
                "object_id": object_id,
                "object_type": target.get("object_type"),
                "saved_revision": _revision(fresh),
                "payload": fresh_payload,
                "dependencies": target.get("dependencies") or [],
                "protected_regions": target.get("protected_regions") or [],
                "sections": requested_sections,
            }
        )
    if conflicts:
        return {"ok": False, "status": "conflict", "conflicts": conflicts, "plan": None}
    recovered = build_semantic_patch_plan(task_id=str(plan.get("task_id") or ""), targets=recovered_targets)
    recovered["recovered_from_plan_hash"] = str(plan.get("plan_hash") or "")
    from datalens_dev_mcp.pipeline.semantic_patch import semantic_patch_plan_hash

    recovered["plan_hash"] = semantic_patch_plan_hash(recovered)
    return {
        "ok": True,
        "status": "recovered",
        "conflicts": [],
        "old_plan_hash": str(plan.get("plan_hash") or ""),
        "new_plan_hash": recovered["plan_hash"],
        "plan": recovered,
    }


def _revision(value: dict[str, Any]) -> Any:
    for key in ("saved_revision", "revision", "revId", "revisionId"):
        if key in value:
            return value[key]
    return None
