from __future__ import annotations

import json
from typing import Any

from datalens_dev_mcp.editor.protected_regions import build_protected_regions
from datalens_dev_mcp.editor.semantic_slots import discover_semantic_slots
from datalens_dev_mcp.pipeline.effective_visual_contract import constraints_for_action
from datalens_dev_mcp.pipeline.patch_preflight import preflight_semantic_patch_batch
from datalens_dev_mcp.pipeline.semantic_payload import semantic_object_payload
from datalens_dev_mcp.pipeline.semantic_patch import build_semantic_patch_plan, semantic_patch_plan_hash
from datalens_dev_mcp.pipeline.target_discovery import compact_object_index
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.pipeline.visual_decisions import VisualDecisionEngine


class SemanticChangePlanner:
    def plan(
        self,
        contract: dict[str, Any],
        *,
        target_graph: dict[str, Any],
        baselines: dict[str, dict[str, Any]],
        changes: list[dict[str, Any]] | None = None,
        binding_hashes: dict[str, str] | None = None,
        effective_visual_contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        requested = list(changes or _contract_changes(contract))
        if not requested:
            return _needs_semantic_actions(
                contract,
                target_graph=target_graph,
                effective_visual_contract=effective_visual_contract or {},
            )
        effective = dict(effective_visual_contract or {})
        if effective and effective.get("schema_id") != "datalens_effective_visual_contract":
            return {
                "ok": False,
                "status": "blocked",
                "issues": ["effective visual contract schema is invalid"],
            }
        nodes = {
            str(item.get("object_id") or ""): item
            for item in target_graph.get("nodes") or []
            if isinstance(item, dict)
        }
        chart_decisions = _chart_decisions(requested, effective)
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
            baseline_revision = _baseline_revision(baseline)
            node_revision = str(node.get("saved_revision") or "")
            if baseline_revision and node_revision and baseline_revision != node_revision:
                issues.append(f"semantic change target revision is stale: {target_id}")
                continue
            payload = semantic_object_payload(baseline)
            tabs = _tabs(payload)
            discovered_slots = {str(item.get("id") or ""): item for item in discover_semantic_slots(tabs)}
            sections: list[dict[str, Any]] = []
            target_constraints: list[dict[str, Any]] = []
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
                applied_constraints = constraints_for_action(
                    effective,
                    change,
                    target_id=target_id,
                    tab_id=tab,
                ) if effective else {}
                forbidden_issue = _forbidden_change_issue(change, applied_constraints)
                if forbidden_issue:
                    issues.append(forbidden_issue)
                    continue
                sections.append(
                    {
                        "tab": tab,
                        "anchor": anchor,
                        "operation": "replace",
                        "value": change.get("value"),
                        "effective_visual_constraints": applied_constraints,
                    }
                )
                if applied_constraints:
                    target_constraints.append(applied_constraints)
            if sections:
                object_type = str(node.get("object_type") or "")
                target = {
                    "object_id": target_id,
                    "object_type": object_type,
                    "saved_revision": str(node.get("saved_revision") or ""),
                    "payload": payload,
                    "dependencies": _dependencies(target_graph, target_id),
                    "protected_regions": _merged_protected_regions(
                        build_protected_regions(tabs),
                        effective,
                    ),
                    "sections": sections,
                    "effective_visual_constraints": target_constraints,
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
                        "payload": semantic_object_payload(dependency_baseline),
                    }
        if issues:
            return {"ok": False, "status": "blocked", "issues": issues}
        patch_plan = build_semantic_patch_plan(task_id=str(contract.get("task_id") or ""), targets=targets)
        planned_by_id = {
            str(item.get("object_id") or ""): item
            for item in patch_plan.get("targets") or []
            if isinstance(item, dict)
        }
        applied_visual_constraints: list[dict[str, Any]] = []
        for target in targets:
            target_id = str(target.get("object_id") or "")
            constraints = list(target.get("effective_visual_constraints") or [])
            if constraints and target_id in planned_by_id:
                planned_by_id[target_id]["effective_visual_constraints"] = constraints
                applied_visual_constraints.extend(constraints)
        if effective:
            patch_plan["effective_visual_contract_hash"] = str(effective.get("contract_hash") or "")
        patch_plan["plan_hash"] = semantic_patch_plan_hash(patch_plan)
        if binding_hashes:
            patch_plan["bindings"] = {key: str(value or "") for key, value in sorted(binding_hashes.items())}
            patch_plan["plan_hash"] = semantic_patch_plan_hash(patch_plan)
        preflight = preflight_semantic_patch_batch(patch_plan, fresh_targets=fresh_targets)
        if not preflight["ok"]:
            return {"ok": False, "status": "blocked", "issues": preflight["issues"], "semantic_patch_plan": patch_plan}
        active = sum(int(item.get("active_section_count") or 0) for item in preflight["targets"])
        if not active:
            return {
                "ok": True,
                "status": "already_satisfied_no_write",
                "matched_assertions": _matched_assertions(requested, preflight),
                "semantic_patch_plan": patch_plan,
                "preflight": preflight,
                "fresh_targets": fresh_targets,
                "effective_visual_contract": effective,
                "applied_visual_constraints": applied_visual_constraints,
                "chart_decisions": chart_decisions,
            }
        return {
            "ok": True,
            "status": "semantic_plan_ready",
            "semantic_patch_plan": patch_plan,
            "preflight": preflight,
            "materialized_payloads": preflight["materialized_payloads"],
            "fresh_targets": fresh_targets,
            "effective_visual_contract": effective,
            "applied_visual_constraints": applied_visual_constraints,
            "chart_decisions": chart_decisions,
        }


def _needs_semantic_actions(
    contract: dict[str, Any],
    *,
    target_graph: dict[str, Any],
    effective_visual_contract: dict[str, Any],
) -> dict[str, Any]:
    task_id = str(contract.get("task_id") or "")
    revision = int(contract.get("contract_revision") or 1)
    nodes = [item for item in target_graph.get("nodes") or [] if isinstance(item, dict)]
    return {
        "ok": False,
        "status": "needs_semantic_actions",
        "state": "needs_semantic_actions",
        "task_id": task_id,
        "contract_revision": revision,
        "target_summary": {
            "object_count": len(nodes),
            "object_ids": [str(item.get("object_id") or "") for item in nodes[:50] if item.get("object_id")],
            "saved_revisions": {
                str(item.get("object_id") or ""): str(item.get("saved_revision") or "")
                for item in nodes[:50]
                if item.get("object_id")
            },
        },
        "object_index": compact_object_index(target_graph, max_objects=50),
        "active_visual_constraints": {
            key: effective_visual_contract.get(key) or {}
            for key in ("required", "preserve", "forbidden", "defaults")
        },
        "semantic_action_schema": {
            "type": "object",
            "required": ["target_id", "value"],
            "properties": {
                "target_id": {"type": "string"},
                "tab": {"type": "string"},
                "slot_id": {"type": "string"},
                "anchor": {"type": "object"},
                "category": {"type": "string"},
                "typed_value": {},
                "value": {},
                "visual_contract": {"type": "object"},
            },
            "anyOf": [{"required": ["slot_id"]}, {"required": ["anchor"]}],
        },
        "task_handle": {
            "task_id": task_id,
            "expected_contract_revision": revision,
        },
        "missing_fields": ["semantic_changes"],
        "required_next_call": None,
        "issues": ["mutation request requires a valid typed semantic action set"],
    }


def _matched_assertions(
    requested: list[dict[str, Any]],
    preflight: dict[str, Any],
) -> list[dict[str, Any]]:
    target_status = {
        str(item.get("object_id") or ""): str(item.get("status") or "")
        for item in preflight.get("targets") or []
        if isinstance(item, dict)
    }
    return [
        {
            "target_id": str(item.get("target_id") or item.get("object_id") or ""),
            "tab": str(item.get("tab") or ""),
            "slot_id": str(item.get("slot_id") or ""),
            "expected": item.get("value"),
            "matched": True,
            "fresh_state": target_status.get(str(item.get("target_id") or item.get("object_id") or ""), "noop"),
        }
        for item in requested
    ]


def _merged_protected_regions(
    discovered: list[dict[str, Any]],
    effective: dict[str, Any],
) -> list[dict[str, Any]]:
    advanced = ((effective.get("preserve") or {}).get("advanced_editor") or {}) if effective else {}
    declared = advanced.get("protected_regions") if isinstance(advanced, dict) else []
    rows = [dict(item) for item in [*discovered, *(declared or [])] if isinstance(item, dict)]
    return list({canonical_hash(item): item for item in rows}.values())


def _forbidden_change_issue(change: dict[str, Any], constraints: dict[str, Any]) -> str:
    forbidden = constraints.get("forbidden") if isinstance(constraints.get("forbidden"), dict) else {}
    slot = str(change.get("slot_id") or change.get("field") or "")
    value = change.get("value")
    for category, section in forbidden.items():
        if isinstance(section, dict) and slot in section and section[slot] == value:
            return f"semantic change violates effective visual contract: {category}.{slot}"
        if not isinstance(section, dict) and section == value:
            return f"semantic change violates effective visual contract: {category}"
    return ""


def _chart_decisions(
    requested: list[dict[str, Any]],
    effective_visual_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    engine = VisualDecisionEngine()
    for index, change in enumerate(requested):
        family = str(change.get("requested_family") or change.get("visualization_family") or "")
        question = str(change.get("business_question") or change.get("chart_purpose") or "")
        if not family and not question:
            continue
        record = engine.decide(
            chart_id=str(change.get("target_id") or change.get("object_id") or f"planned-chart-{index + 1}"),
            business_question=question or "Render the declared typed chart requirement.",
            audience=list(change.get("audience") or []),
            data_shape=dict(change.get("data_shape") or {}),
            metric_semantics=dict(change.get("metric_semantics") or {}),
            requested_family=family,
            requested_route=str(change.get("route") or ""),
            negative_requirements=list(change.get("negative_requirements") or []),
            effective_visual_contract=effective_visual_contract,
            source_evidence_refs=["typed_semantic_action", "effective_visual_contract"],
        )
        rows.append(record.to_dict())
    return rows


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
    identified = next(
        (value for value in baselines.values() if object_id in _baseline_identity_values(value)),
        None,
    )
    if identified is not None:
        return identified
    return next((value for value in baselines.values() if _contains_value(value, object_id)), {})


def _baseline_identity_values(response: dict[str, Any]) -> set[str]:
    value: Any = response.get("result") if isinstance(response.get("result"), dict) else response
    candidates = [value] if isinstance(value, dict) else []
    if isinstance(value, dict):
        candidates.extend(
            nested
            for key in ("dashboard", "chart", "entry", "dataset", "connection")
            if isinstance((nested := value.get(key)), dict)
        )
    rows: set[str] = set()
    for candidate in candidates:
        entry = candidate.get("entry") if isinstance(candidate.get("entry"), dict) else candidate
        for key in ("entryId", "dashboardId", "chartId", "datasetId", "connectionId", "object_id"):
            if entry.get(key):
                rows.add(str(entry[key]))
    return rows


def _baseline_revision(response: dict[str, Any]) -> str:
    value: Any = response.get("result") if isinstance(response.get("result"), dict) else response
    candidates = [value] if isinstance(value, dict) else []
    if isinstance(value, dict):
        candidates.extend(
            nested
            for key in ("dashboard", "chart", "entry", "dataset", "connection")
            if isinstance((nested := value.get(key)), dict)
        )
    for candidate in candidates:
        entry = candidate.get("entry") if isinstance(candidate.get("entry"), dict) else candidate
        for key in ("revId", "revisionId", "revision", "saved_revision"):
            if entry.get(key):
                return str(entry[key])
    return ""


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
