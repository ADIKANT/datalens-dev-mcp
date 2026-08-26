from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.pipeline.browser_policy import compile_browser_policy
from datalens_dev_mcp.pipeline.negative_requirements import compile_correction_constraints
from datalens_dev_mcp.pipeline.question_policy import resolve_question_policy
from datalens_dev_mcp.pipeline.route_contract import normalize_route
from datalens_dev_mcp.pipeline.task_contract import (
    AcceptanceCriterion,
    DeliveryContract,
    EvidenceContract,
    ReferenceContract,
    ScopeContract,
    TargetContract,
    TaskMode,
    WorkspaceContract,
    create_task_contract,
    validate_task_contract,
)
from datalens_dev_mcp.pipeline.user_request import NormalizedUserRequest, normalize_user_request


WRITE_MODES = {"create", "update", "redesign", "publish_only"}
CANONICAL_ROUTES = {
    "editor_advanced",
    "editor_table",
    "editor_markdown",
    "editor_js_control",
    "wizard_native",
    "ql_explicit",
}


def compile_task_contract(
    raw_request: str,
    *,
    project_root: str = ".",
    portfolio_subproject: str = "",
    config_path: str = "",
    current_live: dict[str, Any] | None = None,
    portfolio_source: dict[str, Any] | None = None,
    workspace_policy: dict[str, Any] | None = None,
    current_task_journal: dict[str, Any] | None = None,
    historical_context: dict[str, Any] | None = None,
    corrections: list[str] | tuple[str, ...] | None = None,
    scope_overrides: dict[str, Any] | None = None,
    reference: dict[str, Any] | None = None,
    acceptance: list[dict[str, Any] | str] | tuple[dict[str, Any] | str, ...] | None = None,
    discovered_facts: dict[str, Any] | None = None,
    unresolved_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    correction_values = tuple(str(item).strip() for item in corrections or () if str(item).strip())
    current = current_live or {}
    portfolio = portfolio_source or {}
    workspace = workspace_policy or {}
    journal = current_task_journal or {}
    historical = historical_context or {}

    normalized = normalize_user_request(raw_request)
    correction_request = normalize_user_request("\n".join(correction_values)) if correction_values else None
    mode = _compile_mode(raw_request, normalized, correction_request)
    target, target_trace = _compile_target(
        normalized,
        correction_request=correction_request,
        current_live=current,
        portfolio_source=portfolio,
        workspace_policy=workspace,
        current_task_journal=journal,
    )
    route = _compile_route(normalized, correction_request, mode=mode, target=target)
    correction_contract = compile_correction_constraints(correction_values)
    scope = _compile_scope(target, current, scope_overrides or {}, correction_contract)
    reference_contract = _compile_reference(
        raw_request,
        correction_values,
        reference=reference or {},
        portfolio_source=portfolio,
        current_live=current,
    )
    browser_policy = compile_browser_policy(
        raw_request,
        corrections=correction_values,
        workspace_policy=workspace,
    )
    delivery = _compile_delivery(normalized, correction_request, mode)
    acceptance_contract = _compile_acceptance(acceptance or (), correction_contract)

    required_facts = _required_discoverable_facts(mode, target, route)
    discovery = _compile_discovered_facts(discovered_facts or {}, current, target, reference_contract, browser_policy)
    unresolved = dict(unresolved_facts or {})
    if delivery.destructive:
        unresolved.setdefault("destructive_scope", True)
    candidate_references = reference.get("candidates") if isinstance(reference, dict) else None
    if reference_contract.required_exact_style and not reference_contract.locator and candidate_references:
        unresolved.setdefault("exact_reference", list(candidate_references))
    question_decision = resolve_question_policy(
        required_discoverable_facts=required_facts,
        discovered_facts=discovery,
        unresolved_facts=unresolved,
    )
    stop_conditions = _stop_conditions(mode, target, delivery, question_decision.to_dict())
    available_facts = tuple(sorted(key for key, value in discovery.items() if _present(value)))
    unavailable_facts = tuple(sorted(key for key in required_facts if key not in available_facts))

    contract = create_task_contract(
        raw_request=raw_request,
        mode=mode,
        route=route,
        workspace=WorkspaceContract(
            project_root=str(project_root),
            portfolio_subproject=str(portfolio_subproject),
            config_path=str(config_path),
        ),
        target=target,
        scope=scope,
        reference=reference_contract,
        browser_policy=browser_policy,
        delivery=delivery,
        evidence=EvidenceContract(
            required_facts=tuple(required_facts),
            available_facts=available_facts,
            unavailable_facts=unavailable_facts,
        ),
        acceptance=acceptance_contract,
        stop_conditions=tuple(stop_conditions),
        corrections=correction_values,
    )
    contract_payload = contract.to_dict()
    issues = list(validate_task_contract(contract))
    question_payload = question_decision.question.to_dict() if question_decision.question else None
    if question_payload:
        status = "needs_input"
    elif question_decision.discovery_required:
        status = "needs_discovery"
    elif mode in WRITE_MODES and not target.object_ids and not target.workbook_id:
        status = "needs_discovery"
    else:
        status = "ready"
    ignored_historical = sorted(
        key
        for key in ("workbook_id", "dashboard_id", "chart_id", "object_ids", "saved_revision", "published_revision")
        if _present(historical.get(key))
    )
    return {
        "ok": not issues,
        "status": "invalid" if issues else status,
        "ready": not issues and status == "ready",
        "contract": contract_payload,
        "task_contract_hash": contract.contract_hash,
        "question": question_payload,
        "discovery_required": list(question_decision.discovery_required),
        "issues": issues,
        "source_trace": {
            "target_fields": target_trace,
            "ignored_historical_target_fields": ignored_historical,
            "precedence": list(contract.source_precedence),
        },
    }


def _compile_mode(
    raw_request: str,
    normalized: NormalizedUserRequest,
    correction: NormalizedUserRequest | None,
) -> TaskMode:
    text = "\n".join((raw_request, correction.raw_text if correction else "")).lower()
    if re.search(r"\bpublish(?:\s+from\s+saved)?\s+only\b|только\s+опубли", text):
        return "publish_only"
    if any(term in text for term in ("diagnose", "diagnostic", "root cause", "диагност", "причин")):
        return "diagnose"
    intent = correction.task_intent if correction and correction.task_intent != "unknown" else normalized.task_intent
    if intent == "review":
        return "review"
    if intent == "plan" or normalized.publish_override in {"plan_only", "dry_run"}:
        return "plan"
    if intent == "redesign":
        return "redesign"
    if intent == "implement":
        return "create"
    if intent in {"fix", "enhance", "update"}:
        return "update"
    return "review"


def _compile_target(
    normalized: NormalizedUserRequest,
    *,
    correction_request: NormalizedUserRequest | None,
    current_live: dict[str, Any],
    portfolio_source: dict[str, Any],
    workspace_policy: dict[str, Any],
    current_task_journal: dict[str, Any],
) -> tuple[TargetContract, dict[str, str]]:
    direct = _request_target(correction_request) if correction_request and correction_request.target_known else {}
    raw_direct = _request_target(normalized)
    sources = (
        ("current_user_correction", direct),
        ("current_user_request", raw_direct),
        ("current_live_readback", _target_mapping(current_live)),
        ("current_portfolio_source", _target_mapping(portfolio_source)),
        ("active_workspace_policy", _target_mapping(workspace_policy)),
        ("current_task_journal", _target_mapping(current_task_journal)),
    )
    values: dict[str, Any] = {}
    trace: dict[str, str] = {}
    for key in (
        "workbook_id",
        "dashboard_id",
        "chart_id",
        "saved_revision",
        "published_revision",
        "technology",
    ):
        for source_name, source in sources:
            if _present(source.get(key)):
                values[key] = source[key]
                trace[key] = source_name
                break
    object_ids = _unique(
        [
            str(values.get("dashboard_id") or ""),
            str(values.get("chart_id") or ""),
            *[str(item) for item in _first_list(sources, "object_ids")],
        ]
    )
    object_types = _unique(
        [
            "dashboard" if values.get("dashboard_id") else "",
            "editor_chart" if values.get("chart_id") else "",
            *[str(item) for item in _first_list(sources, "object_types")],
        ]
    )
    return (
        TargetContract(
            workbook_id=str(values.get("workbook_id") or ""),
            dashboard_id=str(values.get("dashboard_id") or ""),
            object_ids=tuple(object_ids),
            object_types=tuple(object_types),
            saved_revision=str(values.get("saved_revision") or ""),
            published_revision=str(values.get("published_revision") or ""),
            technology=str(values.get("technology") or ""),
        ),
        trace,
    )


def _compile_route(
    normalized: NormalizedUserRequest,
    correction: NormalizedUserRequest | None,
    *,
    mode: TaskMode,
    target: TargetContract,
) -> str:
    requested = correction.route_intent if correction and correction.route_intent != "unspecified" else normalized.route_intent
    if requested == "ql_explicit":
        return "ql_explicit"
    aliases = {
        "js": "editor_advanced",
        "advanced_editor": "editor_advanced",
        "native_table": "wizard_native",
        "native_pivot": "wizard_native",
        "wizard_map_native": "wizard_native",
    }
    if requested != "unspecified":
        return normalize_route(aliases.get(requested, requested))
    current_route = normalize_route(str(target.technology or ""))
    if current_route in CANONICAL_ROUTES:
        return current_route
    if mode in {"review", "diagnose"}:
        return "read_only"
    if mode == "plan":
        return "unresolved"
    if mode == "create":
        return "wizard_native"
    return "unresolved"


def _compile_scope(
    target: TargetContract,
    current_live: dict[str, Any],
    overrides: dict[str, Any],
    correction_contract: dict[str, list[str]],
) -> ScopeContract:
    live_tabs = current_live.get("tabs") or (current_live.get("scope") or {}).get("allowed_tabs") or []
    forbidden = _unique(
        [
            *[str(item) for item in overrides.get("forbidden_changes") or ()],
            *correction_contract["forbidden_changes"],
        ]
    )
    return ScopeContract(
        allowed_objects=tuple(_unique([*(overrides.get("allowed_objects") or ()), *target.object_ids])),
        allowed_tabs=tuple(_unique(overrides.get("allowed_tabs") or live_tabs)),
        allowed_semantic_slots=tuple(_unique(overrides.get("allowed_semantic_slots") or ())),
        forbidden_changes=tuple(forbidden),
    )


def _compile_reference(
    raw_request: str,
    corrections: tuple[str, ...],
    *,
    reference: dict[str, Any],
    portfolio_source: dict[str, Any],
    current_live: dict[str, Any],
) -> ReferenceContract:
    text = "\n".join((raw_request, *corrections)).lower()
    exact = any(term in text for term in ("exact", "точно", "один в один", "сохрани этот js", "preserve this js"))
    locator = str(reference.get("locator") or "")
    kind = str(reference.get("kind") or "")
    source_hash = str(reference.get("source_hash") or reference.get("hash") or "")
    if not locator and _present(portfolio_source.get("reference_locator")):
        locator = str(portfolio_source["reference_locator"])
        kind = kind or "portfolio_object"
        source_hash = source_hash or str(portfolio_source.get("reference_hash") or "")
    if not locator and _present(current_live.get("reference_locator")):
        locator = str(current_live["reference_locator"])
        kind = kind or "live_object"
        source_hash = source_hash or str(current_live.get("reference_hash") or "")
    if locator and not kind:
        kind = "portfolio_object" if "portfolio" in locator.lower() else "live_object"
    if kind not in {"portfolio_object", "live_object", "cookbook_recipe", "none"}:
        kind = "none"
    return ReferenceContract(kind=kind, locator=locator, required_exact_style=exact, source_hash=source_hash)


def _compile_delivery(
    normalized: NormalizedUserRequest,
    correction: NormalizedUserRequest | None,
    mode: TaskMode,
) -> DeliveryContract:
    effective = correction if correction and correction.publish_override != "none" else normalized
    destructive = bool(normalized.destructive_actions or (correction.destructive_actions if correction else ()))
    if mode in {"review", "diagnose", "plan"}:
        return DeliveryContract(destructive=destructive)
    if mode == "publish_only":
        return DeliveryContract(save=False, publish=True, destructive=destructive)
    publish = effective.publish_override not in {"draft", "save_only", "no_publish", "plan_only", "dry_run"}
    return DeliveryContract(save=True, publish=publish, destructive=destructive)


def _compile_acceptance(
    acceptance: list[dict[str, Any] | str] | tuple[dict[str, Any] | str, ...],
    correction_contract: dict[str, list[str]],
) -> tuple[AcceptanceCriterion, ...]:
    criteria: list[AcceptanceCriterion] = []
    for item in acceptance:
        if isinstance(item, str) and item.strip():
            criteria.append(AcceptanceCriterion(kind="business", statement=item.strip()))
        elif isinstance(item, dict) and str(item.get("statement") or "").strip():
            criteria.append(
                AcceptanceCriterion(
                    kind=str(item.get("kind") or "business"),
                    statement=str(item["statement"]).strip(),
                    source=str(item.get("source") or "current_user_request"),
                    hard=bool(item.get("hard", True)),
                )
            )
    for statement in correction_contract["acceptance_statements"]:
        criteria.append(
            AcceptanceCriterion(
                kind="constraint",
                statement=statement,
                source="current_user_correction",
                hard=True,
            )
        )
    deduped: dict[tuple[str, str], AcceptanceCriterion] = {}
    for item in criteria:
        deduped[(item.kind, item.statement)] = item
    return tuple(deduped.values())


def _required_discoverable_facts(mode: TaskMode, target: TargetContract, route: str) -> list[str]:
    required = ["target_ids", "object_type"]
    if mode == "create":
        required = ["workbook_id"]
    elif mode in {"update", "redesign"}:
        required.extend(("technology", "layout", "tabs", "saved_revision"))
    elif mode == "publish_only":
        required.append("saved_revision")
    if route.startswith("editor_"):
        required.append("tabs")
    return _unique(required)


def _compile_discovered_facts(
    supplied: dict[str, Any],
    current_live: dict[str, Any],
    target: TargetContract,
    reference: ReferenceContract,
    browser_policy: Any,
) -> dict[str, Any]:
    result = dict(current_live.get("discovered_facts") or {})
    result.update({key: value for key, value in supplied.items() if _present(value)})
    result.setdefault("workbook_id", target.workbook_id)
    result.setdefault("dashboard_id", target.dashboard_id)
    result.setdefault("target_ids", list(target.object_ids))
    result.setdefault("object_type", list(target.object_types))
    result.setdefault("technology", target.technology)
    result.setdefault("layout", current_live.get("layout"))
    result.setdefault("tabs", current_live.get("tabs"))
    result.setdefault("saved_revision", target.saved_revision)
    result.setdefault("published_revision", target.published_revision)
    result.setdefault("reference_hash", reference.source_hash)
    result.setdefault("browser_availability", browser_policy.mode != "forbidden")
    result.setdefault("auth_state", current_live.get("auth_state"))
    return result


def _stop_conditions(
    mode: TaskMode,
    target: TargetContract,
    delivery: DeliveryContract,
    question_decision: dict[str, Any],
) -> list[str]:
    conditions = ["target_or_revision_changed", "task_contract_hash_mismatch"]
    if question_decision.get("question"):
        conditions.append("user_answer_required")
    if question_decision.get("discovery_required"):
        conditions.append("read_discoverable_facts_before_continuing")
    if mode in WRITE_MODES and not (target.object_ids or target.workbook_id):
        conditions.append("target_not_discovered")
    if delivery.destructive:
        conditions.append("destructive_scope_confirmation_required")
    return _unique(conditions)


def _request_target(request: NormalizedUserRequest | None) -> dict[str, Any]:
    if request is None:
        return {}
    object_ids = _unique((request.target_dashboard_id, request.target_chart_id))
    object_types = _unique(
        (
            "dashboard" if request.target_dashboard_id else "",
            "editor_chart" if request.target_chart_id else "",
        )
    )
    return {
        "workbook_id": request.target_workbook_id,
        "dashboard_id": request.target_dashboard_id,
        "chart_id": request.target_chart_id,
        "object_ids": object_ids,
        "object_types": object_types,
    }


def _target_mapping(value: dict[str, Any]) -> dict[str, Any]:
    target = value.get("target") if isinstance(value.get("target"), dict) else {}
    return {
        "workbook_id": value.get("workbook_id") or target.get("workbook_id"),
        "dashboard_id": value.get("dashboard_id") or target.get("dashboard_id"),
        "chart_id": value.get("chart_id") or target.get("chart_id"),
        "object_ids": value.get("object_ids") or target.get("object_ids") or (),
        "object_types": value.get("object_types") or target.get("object_types") or (),
        "saved_revision": value.get("saved_revision") or target.get("saved_revision"),
        "published_revision": value.get("published_revision") or target.get("published_revision"),
        "technology": value.get("technology") or target.get("technology"),
    }


def _first_list(sources: tuple[tuple[str, dict[str, Any]], ...], key: str) -> list[Any]:
    for _, source in sources:
        value = source.get(key)
        if isinstance(value, (list, tuple)) and value:
            return list(value)
    return []


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or ():
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result


def _present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return value is not None and value is not False
