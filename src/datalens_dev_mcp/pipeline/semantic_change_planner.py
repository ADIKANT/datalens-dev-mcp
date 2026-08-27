from __future__ import annotations

import json
from typing import Any

from datalens_dev_mcp.editor.protected_regions import build_protected_regions
from datalens_dev_mcp.editor.semantic_slots import discover_semantic_slots
from datalens_dev_mcp.pipeline.patch_preflight import preflight_semantic_patch_batch
from datalens_dev_mcp.pipeline.semantic_patch import build_semantic_patch_plan


class SemanticChangePlanner:
    def plan(
        self,
        contract: dict[str, Any],
        *,
        target_graph: dict[str, Any],
        baselines: dict[str, dict[str, Any]],
        changes: list[dict[str, Any]] | None = None,
        binding_hashes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        requested = list(changes or _contract_changes(contract))
        if not requested:
            return {
                "ok": False,
                "status": "NO_CHANGE_REQUIRED",
                "issues": ["task contains no explicit semantic change"],
            }
        nodes = {
            str(item.get("object_id") or ""): item
            for item in target_graph.get("nodes") or []
            if isinstance(item, dict)
        }
        grouped: dict[str, list[dict[str, Any]]] = {}
        for change in requested:
            target_id = str(change.get("target_id") or change.get("object_id") or "")
            if not target_id:
                target_id = _default_change_target(nodes)
            grouped.setdefault(target_id, []).append(change)
        targets: list[dict[str, Any]] = []
        fresh_targets: dict[str, dict[str, Any]] = {}
        scope = contract.get("scope") or {}
        allowed_objects = set(scope.get("allowed_objects") or [])
        allowed_tabs = set(scope.get("allowed_tabs") or [])
        allowed_slots = set(scope.get("allowed_semantic_slots") or [])
        issues: list[str] = []
        for target_id, target_changes in grouped.items():
            node = nodes.get(target_id)
            if node is None:
                issues.append(f"semantic change target is not in fresh target graph: {target_id}")
                continue
            if allowed_objects and target_id not in allowed_objects:
                issues.append(f"semantic change target is outside allowed object scope: {target_id}")
                continue
            baseline = _baseline_for(target_id, baselines)
            if not baseline:
                issues.append(f"fresh baseline is unavailable for semantic target: {target_id}")
                continue
            payload = _object_payload(baseline)
            tabs = _tabs(payload)
            discovered_slots = {str(item.get("id") or ""): item for item in discover_semantic_slots(tabs)}
            sections: list[dict[str, Any]] = []
            for change in target_changes:
                tab = str(change.get("tab") or "")
                slot_id = str(change.get("slot_id") or "")
                anchor = dict(change.get("anchor") or {})
                if slot_id:
                    slot = discovered_slots.get(slot_id)
                    if slot is None:
                        issues.append(f"semantic slot is unavailable or stale: {slot_id}")
                        continue
                    tab = tab or str(slot.get("tab") or "")
                    anchor = {"kind": "semantic_slot", "slot_id": slot_id}
                if not anchor:
                    issues.append("semantic change requires slot_id or an exact semantic anchor")
                    continue
                if allowed_tabs and tab not in allowed_tabs:
                    issues.append(f"semantic change tab is outside allowed scope: {tab}")
                    continue
                if allowed_slots and slot_id and slot_id not in allowed_slots:
                    issues.append(f"semantic slot is outside allowed scope: {slot_id}")
                    continue
                sections.append(
                    {
                        "tab": tab,
                        "anchor": anchor,
                        "operation": "replace",
                        "value": change.get("value"),
                    }
                )
            if sections:
                object_type = str(node.get("object_type") or "")
                target = {
                    "object_id": target_id,
                    "object_type": object_type,
                    "saved_revision": str(node.get("saved_revision") or ""),
                    "payload": payload,
                    "dependencies": _dependencies(target_graph, target_id),
                    "protected_regions": build_protected_regions(tabs),
                    "sections": sections,
                }
                targets.append(target)
                fresh_targets[target_id] = {
                    "object_type": object_type,
                    "saved_revision": str(node.get("saved_revision") or ""),
                    "payload": payload,
                }
        for target in targets:
            for dependency_id in target.get("dependencies") or []:
                if dependency_id in fresh_targets or dependency_id not in nodes:
                    continue
                dependency_baseline = _baseline_for(dependency_id, baselines)
                if dependency_baseline:
                    dependency_node = nodes[dependency_id]
                    fresh_targets[dependency_id] = {
                        "object_type": str(dependency_node.get("object_type") or ""),
                        "saved_revision": str(dependency_node.get("saved_revision") or ""),
                        "payload": _object_payload(dependency_baseline),
                    }
        if issues:
            return {"ok": False, "status": "blocked", "issues": issues}
        patch_plan = build_semantic_patch_plan(task_id=str(contract.get("task_id") or ""), targets=targets)
        if binding_hashes:
            patch_plan["bindings"] = {key: str(value or "") for key, value in sorted(binding_hashes.items())}
            from datalens_dev_mcp.pipeline.semantic_patch import semantic_patch_plan_hash

            patch_plan["plan_hash"] = semantic_patch_plan_hash(patch_plan)
        preflight = preflight_semantic_patch_batch(patch_plan, fresh_targets=fresh_targets)
        if not preflight["ok"]:
            return {"ok": False, "status": "blocked", "issues": preflight["issues"], "semantic_patch_plan": patch_plan}
        active = sum(int(item.get("active_section_count") or 0) for item in preflight["targets"])
        if not active:
            return {
                "ok": False,
                "status": "NO_CHANGE_REQUIRED",
                "issues": ["semantic plan is a no-op"],
                "semantic_patch_plan": patch_plan,
            }
        return {
            "ok": True,
            "status": "ready",
            "semantic_patch_plan": patch_plan,
            "preflight": preflight,
            "materialized_payloads": preflight["materialized_payloads"],
            "fresh_targets": fresh_targets,
        }


def _contract_changes(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in contract.get("acceptance") or []:
        if not isinstance(item, dict) or item.get("kind") != "semantic_change":
            continue
        try:
            parsed = json.loads(str(item.get("statement") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _default_change_target(nodes: dict[str, dict[str, Any]]) -> str:
    return next(
        (
            object_id for object_id, item in nodes.items()
            if "chart" in str(item.get("object_type") or "") or item.get("object_type") in {"control", "markdown"}
        ),
        next(iter(nodes), ""),
    )


def _baseline_for(object_id: str, baselines: dict[str, dict[str, Any]]) -> dict[str, Any]:
    named = next((value for name, value in baselines.items() if f"-{object_id}-" in name), None)
    if named is not None:
        return named
    return next((value for value in baselines.values() if _contains_value(value, object_id)), {})


def _object_payload(response: dict[str, Any]) -> dict[str, Any]:
    value: Any = response.get("result") if isinstance(response.get("result"), dict) else response
    if isinstance(value, dict):
        for key in ("dashboard", "chart", "entry"):
            if isinstance(value.get(key), dict):
                value = value[key]
                break
    if not isinstance(value, dict):
        return {}
    entry = dict(value.get("entry") or {}) if isinstance(value.get("entry"), dict) else {}
    data = value.get("data")
    if entry:
        if data is not None:
            entry["data"] = data
        return entry
    return dict(value)


def _tabs(payload: dict[str, Any]) -> dict[str, str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    aliases = {
        "meta": "meta.json",
        "params": "params.js",
        "sources": "sources.js",
        "controls": "controls.js",
        "prepare": "prepare.js",
        "config": "config.js",
    }
    return {
        aliases[key]: value
        for key, value in data.items()
        if key in aliases and isinstance(value, str)
    }


def _dependencies(graph: dict[str, Any], object_id: str) -> list[str]:
    return sorted(
        str(item.get("target") or "")
        for item in graph.get("edges") or []
        if isinstance(item, dict) and item.get("source") == object_id and item.get("target")
    )


def _contains_value(value: Any, expected: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_value(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value(item, expected) for item in value)
    return str(value) == expected
