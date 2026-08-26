from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from datalens_dev_mcp.pipeline.patch_anchors import anchor_hash, replace_anchor, resolve_anchor


def canonical_hash(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_semantic_patch_plan(
    *,
    task_id: str,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    planned_targets: list[dict[str, Any]] = []
    for target in targets:
        payload = _target_payload(target)
        working = _clone(payload)
        sections: list[dict[str, Any]] = []
        for requested in target.get("sections") or []:
            tab = str(requested.get("tab") or "")
            section_document = section_value(working, tab)
            match = resolve_anchor(section_document, dict(requested.get("anchor") or {}), tab=tab)
            value = requested.get("value")
            after_document = replace_anchor(section_document, match, value)
            working = set_section_value(working, tab, after_document)
            anchor = dict(requested.get("anchor") or {})
            anchor["anchor_hash"] = anchor_hash(match.value)
            sections.append(
                {
                    "tab": tab,
                    "tab_hash": canonical_hash(section_document),
                    "anchor": anchor,
                    "operation": "replace",
                    "value": _clone(value),
                    "value_artifact": str(requested.get("value_artifact") or ""),
                    "expected_after_hash": anchor_hash(value),
                    "expected_section_after_hash": canonical_hash(after_document),
                }
            )
        planned_targets.append(
            {
                "object_id": str(target.get("object_id") or ""),
                "object_type": str(target.get("object_type") or ""),
                "saved_revision": target.get("saved_revision"),
                "saved_hash": canonical_hash(payload),
                "expected_after_hash": canonical_hash(working),
                "dependencies": sorted({str(item) for item in target.get("dependencies") or [] if str(item)}),
                "protected_regions": _clone(target.get("protected_regions") or []),
                "sections": sections,
            }
        )
    plan = {
        "schema_id": "semantic_patch_plan",
        "task_id": str(task_id or ""),
        "targets": planned_targets,
    }
    plan["plan_hash"] = semantic_patch_plan_hash(plan)
    return plan


def semantic_patch_plan_hash(plan: dict[str, Any]) -> str:
    canonical = {key: value for key, value in plan.items() if key != "plan_hash"}
    return canonical_hash(canonical)


def validate_semantic_patch_plan(plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if plan.get("schema_id") != "semantic_patch_plan":
        issues.append("schema_id must be semantic_patch_plan")
    if not plan.get("task_id"):
        issues.append("task_id is required")
    targets = plan.get("targets")
    if not isinstance(targets, list) or not targets:
        issues.append("targets must be a non-empty array")
        return issues
    if plan.get("plan_hash") != semantic_patch_plan_hash(plan):
        issues.append("plan_hash mismatch")
    seen: set[str] = set()
    for index, target in enumerate(targets):
        object_id = str(target.get("object_id") or "") if isinstance(target, dict) else ""
        if not object_id:
            issues.append(f"targets[{index}].object_id is required")
        elif object_id in seen:
            issues.append(f"targets[{index}].object_id is duplicated")
        seen.add(object_id)
        if not str(target.get("object_type") or ""):
            issues.append(f"targets[{index}].object_type is required")
        if not target.get("sections"):
            issues.append(f"targets[{index}].sections must be non-empty")
        for section_index, section in enumerate(target.get("sections") or []):
            if section.get("operation") != "replace":
                issues.append(f"targets[{index}].sections[{section_index}] operation must be replace")
            if not str((section.get("anchor") or {}).get("anchor_hash") or ""):
                issues.append(f"targets[{index}].sections[{section_index}] anchor_hash is required")
            anchor = section.get("anchor") or {}
            if (
                str(target.get("object_type") or "") == "dashboard"
                and anchor.get("kind") == "json_pointer"
                and any(token.isdigit() for token in str(anchor.get("pointer") or "").split("/") if token)
            ):
                issues.append(
                    f"targets[{index}].sections[{section_index}] dashboard anchors must use semantic identity, not raw array positions"
                )
    return issues


def apply_target_sections(
    payload: Any,
    target: dict[str, Any],
    *,
    value_resolver: Callable[[str], Any] | None = None,
    allow_stale_section_hash: bool = False,
) -> dict[str, Any]:
    working = _clone(payload)
    results: list[dict[str, Any]] = []
    for index, section in enumerate(target.get("sections") or []):
        tab = str(section.get("tab") or "")
        document = section_value(working, tab)
        if not allow_stale_section_hash and canonical_hash(document) != str(section.get("tab_hash") or ""):
            raise ValueError(f"section {index} tab hash is stale")
        match = resolve_anchor(document, dict(section.get("anchor") or {}), tab=tab)
        if anchor_hash(match.value) != str((section.get("anchor") or {}).get("anchor_hash") or ""):
            raise ValueError(f"section {index} anchor hash is stale")
        value = section.get("value")
        artifact = str(section.get("value_artifact") or "")
        if artifact:
            if value_resolver is None:
                raise ValueError(f"section {index} requires value artifact resolution")
            value = value_resolver(artifact)
        if anchor_hash(value) != str(section.get("expected_after_hash") or ""):
            raise ValueError(f"section {index} expected value hash mismatch")
        noop = anchor_hash(match.value) == anchor_hash(value)
        after = replace_anchor(document, match, value)
        if not allow_stale_section_hash and canonical_hash(after) != str(section.get("expected_section_after_hash") or ""):
            raise ValueError(f"section {index} expected section hash mismatch")
        working = set_section_value(working, tab, after)
        results.append({"index": index, "tab": tab, "noop": noop, "after_hash": canonical_hash(after)})
    return {"payload": working, "sections": results, "after_hash": canonical_hash(working)}


def section_value(payload: Any, tab: str) -> Any:
    if not tab:
        return payload
    if not isinstance(payload, dict):
        raise ValueError(f"tab {tab} requires an object payload")
    tabs = payload.get("tabs")
    if isinstance(tabs, dict) and tab in tabs:
        return tabs[tab]
    data = payload.get("data")
    normalized = tab.removesuffix(".js").removesuffix(".json")
    if isinstance(data, dict) and normalized in data:
        return data[normalized]
    entry = payload.get("entry")
    if isinstance(entry, dict) and isinstance(entry.get("data"), dict) and normalized in entry["data"]:
        return entry["data"][normalized]
    raise ValueError(f"tab {tab} is missing")


def set_section_value(payload: Any, tab: str, value: Any) -> Any:
    if not tab:
        return _clone(value)
    result = _clone(payload)
    if isinstance(result.get("tabs"), dict) and tab in result["tabs"]:
        result["tabs"][tab] = value
        return result
    normalized = tab.removesuffix(".js").removesuffix(".json")
    if isinstance(result.get("data"), dict) and normalized in result["data"]:
        result["data"][normalized] = value
        return result
    if isinstance(result.get("entry"), dict) and isinstance(result["entry"].get("data"), dict):
        if normalized in result["entry"]["data"]:
            result["entry"]["data"][normalized] = value
            return result
    raise ValueError(f"tab {tab} is missing")


def target_payload(value: dict[str, Any]) -> Any:
    return _target_payload(value)


def _target_payload(value: dict[str, Any]) -> Any:
    for key in ("payload", "saved_payload", "document"):
        if key in value:
            return value[key]
    return value


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))
