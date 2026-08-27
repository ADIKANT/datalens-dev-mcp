from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.mcp.task_projection import (
    compact_task_status,
    project_task_summary,
    public_task_state,
    task_state_etag,
)
from datalens_dev_mcp.mcp.task_resources import read_task_evidence, task_resource_uri
from datalens_dev_mcp.mcp.tools import pipeline
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.build_identity import BuildIdentityResolver
from datalens_dev_mcp.pipeline.execution_authorization import (
    resolve_execution_authorization,
    validate_execution_authorization,
)
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal
from datalens_dev_mcp.pipeline.public_plan_builder import PublicPlanBuilder
from datalens_dev_mcp.pipeline.reference_style_service import ReferenceStyleService
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract
from datalens_dev_mcp.pipeline.task_completion import TaskCompletionEvaluator
from datalens_dev_mcp.pipeline.task_service_factory import create_autonomous_task_service
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

RUN_UNTIL_VALUES = frozenset({"blocked", "plan_ready", "completed"})


def dl_task_start(
    request: str,
    project_root: str = ".",
    context: dict[str, Any] | None = None,
    run_until: str = "plan_ready",
) -> dict[str, Any]:
    boundary = _run_until(run_until)
    task_context = dict(context or {})
    target_url = str(task_context.get("target_url") or "")
    compile_request = request + (f"\nTarget: {target_url}" if target_url and target_url not in request else "")
    reference_locator = str(task_context.get("reference_locator") or "")
    reference_kind = "portfolio_object" if reference_locator and task_context.get("portfolio_root") else "live_object"
    semantic_changes = [item for item in task_context.get("semantic_changes") or [] if isinstance(item, dict)]
    acceptance = list(task_context.get("acceptance") or [])
    acceptance.extend(
        {
            "kind": "semantic_change",
            "statement": json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "source": "current_user_request",
            "hard": True,
        }
        for item in semantic_changes
    )
    scope_overrides = dict(task_context.get("scope") or {})
    if semantic_changes:
        scope_overrides["allowed_objects"] = list(dict.fromkeys([
            *list(scope_overrides.get("allowed_objects") or []),
            *[str(item.get("target_id") or item.get("object_id") or "") for item in semantic_changes],
        ]))
        scope_overrides["allowed_tabs"] = list(dict.fromkeys([
            *list(scope_overrides.get("allowed_tabs") or []),
            *[str(item.get("tab") or "") for item in semantic_changes],
        ]))
        scope_overrides["allowed_semantic_slots"] = list(dict.fromkeys([
            *list(scope_overrides.get("allowed_semantic_slots") or []),
            *[str(item.get("slot_id") or "") for item in semantic_changes],
        ]))
    compiled = compile_task_contract(
        compile_request,
        project_root=str(Path(project_root).resolve()),
        reference={
            "kind": reference_kind if reference_locator else "none",
            "locator": reference_locator,
        },
        current_live={
            key: task_context[key]
            for key in ("workbook_id", "dashboard_id", "chart_id", "object_ids", "object_types")
            if key in task_context
        },
        scope_overrides=scope_overrides,
        acceptance=acceptance,
    )
    contract = dict(compiled["contract"])
    journal = ProjectJournal(project_root, str(contract["task_id"]))
    build_identity = BuildIdentityResolver().resolve()
    target_binding = resolve_contract_target_binding(contract)
    grant = resolve_execution_authorization(contract)
    state, compile_receipt, _ = journal.initialize_task(
        contract,
        build_identity=build_identity,
        target_binding=target_binding,
        compile_receipt={
            "schema_id": "datalens_task_compile_receipt",
            "status": compiled.get("status"),
            "issues": compiled.get("issues") or [],
            "discovery_required": compiled.get("discovery_required") or [],
            "question": compiled.get("question"),
            "contract_hash": contract.get("contract_hash"),
            "build_identity_hash": build_identity.get("identity_hash"),
            "target_binding_hash": target_binding.get("binding_hash"),
        },
        execution_grant=grant,
    )
    before = state.last_event_id
    if compiled.get("status") in {"invalid", "needs_input"}:
        return _block_task(
            journal,
            contract,
            before=before,
            code="BLOCKED_INPUT",
            reason="task contract requires user input",
            question=compiled.get("question"),
            missing_facts=compiled.get("discovery_required") or [],
            receipt_uri=compile_receipt,
            transition="TASK_INPUT_REQUIRED",
            issues=compiled.get("issues") or [],
        )
    if compiled.get("status") == "needs_discovery":
        try:
            discovery = TargetDiscoveryService(
                max_objects=int(task_context.get("max_discovery_objects") or 50)
            ).discover(
                contract,
                request_text=compile_request,
                target_url=target_url,
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary becomes typed blocked evidence.
            discovery = {
                "status": "blocked",
                "reason": f"live target discovery failed: {exc.__class__.__name__}",
                "missing_facts": compiled.get("discovery_required") or [],
                "question": None,
            }
        if discovery.get("status") != "success":
            receipt = journal.write_receipt(
                f"target-discovery-blocked-{canonical_hash(discovery)[:16]}",
                discovery,
            )
            return _block_task(
                journal,
                contract,
                before=before,
                code="BLOCKED_DISCOVERY",
                reason=str(discovery.get("reason") or "server-owned target discovery is incomplete"),
                question=discovery.get("question"),
                missing_facts=discovery.get("missing_facts") or compiled.get("discovery_required") or [],
                receipt_uri=receipt,
                transition="TASK_DISCOVERY_REQUIRED",
                issues=compiled.get("issues") or [],
            )
        style = ReferenceStyleService().bind(
            contract,
            target_graph=dict(discovery["target_graph"]),
            baselines=dict(discovery.get("baselines") or {}),
            portfolio_root=str(task_context.get("portfolio_root") or ""),
        )
        if style.get("status") != "success":
            receipt = journal.write_receipt(
                f"style-binding-blocked-{canonical_hash(style)[:16]}", style,
            )
            return _block_task(
                journal,
                contract,
                before=before,
                code="BLOCKED_STYLE_BINDING",
                reason=str(style.get("reason") or "exact style binding is unavailable"),
                question=None,
                missing_facts=["reference_binding", "style_binding"],
                receipt_uri=receipt,
                transition="TASK_STYLE_BINDING_REQUIRED",
                issues=[],
            )
        journal.bind_discovery(
            contract,
            target_binding=dict(discovery["target_binding"]),
            target_graph=dict(discovery["target_graph"]),
            reference_binding=dict(style["reference_binding"]),
            style_binding=dict(style["style_binding"]),
            baselines=dict(discovery.get("baselines") or {}),
            discovery_receipt={
                "schema_id": "datalens_target_discovery_receipt",
                "status": "success",
                "observed_at": discovery.get("observed_at"),
                "provider_calls": discovery.get("provider_calls") or [],
                "technology": discovery.get("technology"),
                "tab_count": discovery.get("tab_count", 0),
                "dataset_count": discovery.get("dataset_count", 0),
                "field_count": discovery.get("field_count", 0),
            },
        )
    state = _advance(journal, contract, boundary=boundary, execution_grant=grant)
    plan = _ensure_task_plan(journal, contract, state) if state.current_state == "VALIDATED" else {}
    if boundary == "completed" and state.current_state == "VALIDATED":
        state = _advance(journal, contract, boundary="completed", execution_grant=grant)
    result = project_task_summary(
        contract=contract,
        state=state,
        events_path=journal.events_path,
        resource_uri=task_resource_uri(journal.task_id),
        performed_after=before,
        **_projection_bindings(journal),
    )
    if plan:
        result.update({"plan_hash": plan["plan_hash"], "plan_resource_uri": task_resource_uri(journal.task_id, "plans/plan.json")})
    return result


def dl_task_resume(
    task_id: str,
    project_root: str = ".",
    expected_state: str = "",
    expected_hash: str = "",
    run_until: str = "completed",
    transition_budget: int = 20,
) -> dict[str, Any]:
    boundary = _run_until(run_until)
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    grant = _load_authorization(journal, contract)
    state, _ = journal.replay()
    _assert_expected_state(state, expected_state=expected_state, expected_hash=expected_hash)
    before = state.last_event_id
    if state.current_state == "VALIDATED":
        _ensure_task_plan(journal, contract, state)
    state = _advance(
        journal, contract, boundary=boundary, transition_budget=transition_budget,
        execution_grant=grant,
    )
    result = project_task_summary(
        contract=contract,
        state=state,
        events_path=journal.events_path,
        resource_uri=task_resource_uri(task_id),
        performed_after=before,
        **_projection_bindings(journal),
    )
    plan = _load_task_plan(journal)
    if plan and state.current_state == "VALIDATED":
        result.update({"plan_hash": plan.get("plan_hash"), "plan_resource_uri": task_resource_uri(task_id, "plans/plan.json")})
    return result


def dl_task_status(task_id: str, project_root: str = ".") -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    state, corrupt_tail = journal.replay()
    result = compact_task_status(
        contract, state, resource_uri=task_resource_uri(task_id), **_projection_bindings(journal)
    )
    result["journal_recovered"] = corrupt_tail
    return result


def dl_inspect(
    project_root: str = ".",
    task_id: str = "",
    target_url: str = "",
    max_nodes: int = 50,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    limit = min(200, max(1, int(max_nodes or 50)))
    if task_id:
        journal = ProjectJournal(root, task_id)
        graph = read_json(journal.target_graph_path, {}) or {}
        if graph:
            result = _live_graph_projection(graph, task_id=task_id)
            profile = read_json(journal.root / "data" / "context-profile.json", {}) or {}
            if profile:
                result["data_context"] = _context_profile_projection(profile, task_id=task_id)
            return result
    if target_url:
        inspect_request = f"Inspect DataLens target {target_url}"
        compiled = compile_task_contract(inspect_request, project_root=str(root))
        discovered = TargetDiscoveryService(max_objects=limit).discover(
            dict(compiled["contract"]),
            request_text=inspect_request,
            target_url=target_url,
        )
        if discovered.get("status") != "success":
            return {
                "ok": False,
                "graph_kind": "live_target_graph",
                "reason": discovered.get("reason"),
                "question": discovered.get("question"),
            }
        graph = dict(discovered["target_graph"])
        path = root / "artifacts" / "inspections" / f"target-graph-{graph['graph_hash'][:20]}.json"
        write_json(path, graph)
        result = _live_graph_projection(graph, task_id="")
        result["artifact_path"] = str(path)
        return result
    validation = pipeline.dl_validate_project(str(root))
    artifacts = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "artifacts").rglob("*")
        if path.is_file()
    )[:limit] if (root / "artifacts").is_dir() else []
    return {
        "ok": bool(validation.get("ok", True)),
        "task_id": task_id,
        "graph_kind": "local_project_graph",
        "target_url_present": bool(target_url),
        "project_validation": {
            "status": validation.get("status"),
            "issue_count": len(validation.get("issues") or []),
        },
        "graph": {
            "node_count": len(artifacts),
            "nodes": artifacts,
            "bounded": True,
        },
        "resource_uri": task_resource_uri(task_id) if task_id else "datalens://project/requirements",
    }


def dl_plan(task_id: str, project_root: str = ".") -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    _assert_current_identity(journal, contract)
    state, _ = journal.replay()
    if state.current_state not in {"VALIDATED", "COMPLETED"}:
        state = _advance(
            journal, contract, boundary="plan_ready",
            execution_grant=_load_authorization(journal, contract),
        )
    if state.current_state != "VALIDATED":
        return {
            **compact_task_status(
                contract, state, resource_uri=task_resource_uri(task_id), **_projection_bindings(journal)
            ),
            "ok": False,
            "reason": "task did not reach PLAN_VALIDATED",
        }
    plan = _ensure_task_plan(journal, contract, state)
    return {
        "ok": True,
        "task_id": task_id,
        "state": "PLAN_VALIDATED",
        "plan_hash": plan["plan_hash"],
        "plan_resource_uri": task_resource_uri(task_id, "plans/plan.json"),
        "safe_apply_ready": bool(plan.get("safe_apply_action_count")),
        "safe_apply_action_count": plan.get("safe_apply_action_count", 0),
        "dataset_context_profile_hash": plan.get("dataset_context_profile_hash"),
        "query_set_hash": plan.get("query_set_hash"),
        "dataset_schema_hash": plan.get("dataset_schema_hash"),
        "context_limitations": plan.get("context_limitations") or [],
        "next_action": "dl_execute" if (contract.get("delivery") or {}).get("save") else "dl_verify",
    }


def dl_execute(
    task_id: str,
    plan_hash: str,
    project_root: str = ".",
    destructive_token: str = "",
) -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    _assert_current_identity(journal, contract)
    state, _ = journal.replay()
    if state.current_state != "VALIDATED":
        raise ValueError(f"dl_execute requires PLAN_VALIDATED, current state is {public_task_state(state.current_state)}")
    plan = _ensure_task_plan(journal, contract, state)
    if plan.get("plan_hash") != plan_hash:
        raise ValueError("plan_hash does not match the immutable task plan")
    if (contract.get("delivery") or {}).get("destructive"):
        expected = _destructive_token(task_id, plan_hash)
        if destructive_token != expected:
            raise ValueError("destructive task requires the exact task-bound destructive token")
    before = state.last_event_id
    state = _advance(
        journal, contract, boundary="completed", destructive_token=destructive_token,
        execution_grant=_load_authorization(journal, contract),
    )
    return project_task_summary(
        contract=contract,
        state=state,
        events_path=journal.events_path,
        resource_uri=task_resource_uri(task_id),
        performed_after=before,
        **_projection_bindings(journal),
    )


def dl_verify(task_id: str, proof_target: str = "completion", project_root: str = ".") -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    state, _ = journal.replay()
    evaluated = TaskCompletionEvaluator().evaluate(journal, contract, proof_target=proof_target)
    return {
        **evaluated,
        "task_id": task_id,
        "state": public_task_state(state.current_state),
        "proof_target": proof_target,
        "risk": state.blocker or None,
        "resource_uri": task_resource_uri(task_id, "checkpoint"),
    }


def dl_evidence(
    task_id: str,
    project_root: str = ".",
    resource_uri: str = "",
    section: str = "",
    offset: int = 0,
    limit: int = 4_000,
) -> dict[str, Any]:
    return read_task_evidence(
        project_root=project_root,
        task_id=task_id,
        resource_uri=resource_uri,
        section=section,
        offset=offset,
        limit=limit,
    )


def _advance(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    boundary: str,
    transition_budget: int = 20,
    destructive_token: str = "",
    execution_grant: dict[str, Any] | None = None,
):
    resolved_grant = execution_grant or _load_authorization(journal, contract)
    build_identity, target_binding = _assert_current_identity(journal, contract)
    service = create_autonomous_task_service(
        journal,
        contract,
        execution_grant=resolved_grant,
        build_identity_hash=str(build_identity.get("identity_hash") or ""),
        target_binding_hash=str(target_binding.get("binding_hash") or ""),
    )
    engine = WorkflowEngine(
        journal,
        contract,
        handlers=service.handlers(),
        build_identity=build_identity,
        target_binding=target_binding,
        style_binding_hash=str((read_json(journal.style_binding_path, {}) or {}).get("binding_hash") or ""),
        require_typed_receipts=True,
    )
    stop_states = {"VALIDATED"} if boundary == "plan_ready" else None
    return engine.resume(max_transitions=max(1, min(100, int(transition_budget))), stop_states=stop_states)


def _assert_current_identity(
    journal: ProjectJournal,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    build_identity = BuildIdentityResolver().resolve()
    target_binding = read_json(journal.target_binding_path, default={}) or {}
    journal.assert_write_resume_ready(
        contract,
        build_identity=build_identity,
        target_binding=target_binding,
    )
    return build_identity, target_binding


def _block_task(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    before: int,
    code: str,
    reason: str,
    question: Any,
    missing_facts: list[str],
    receipt_uri: str,
    transition: str,
    issues: list[Any],
) -> dict[str, Any]:
    blocker = {
        "reason": reason,
        "code": code,
        "question": question,
        "missing_facts": list(missing_facts),
        "receipt": receipt_uri,
    }
    with journal.locked(owner="task-blocker"):
        state, _ = journal.replay()
        state = journal.append_transition(
            state,
            transition=transition,
            input_value={"issues": issues},
            receipt_uri=receipt_uri,
            status="blocked",
            idempotency_key=canonical_hash({"task_id": journal.task_id, "transition": transition}),
            next_state="BLOCKED",
            next_transition="",
            blocker=blocker,
        )
    return project_task_summary(
        contract=contract,
        state=state,
        events_path=journal.events_path,
        resource_uri=task_resource_uri(journal.task_id),
        performed_after=before,
        **_projection_bindings(journal),
    )


def _live_graph_projection(graph: dict[str, Any], *, task_id: str) -> dict[str, Any]:
    nodes = list(graph.get("nodes") or [])
    return {
        "ok": True,
        "task_id": task_id,
        "graph_kind": "live_target_graph",
        "graph_hash": graph.get("graph_hash"),
        "node_count": len(nodes),
        "edge_count": len(graph.get("edges") or []),
        "nodes": [
            {
                "object_type": item.get("object_type"),
                "object_id": item.get("object_id"),
                "technology": item.get("technology"),
                "saved_revision": item.get("saved_revision"),
                "field_count": len(item.get("field_catalog") or []),
            }
            for item in nodes[:50]
        ],
        "limitations": graph.get("limitations") or [],
        "bounded": True,
        "resource_uri": task_resource_uri(task_id, "target-graph") if task_id else "datalens://inspect/target-graph",
    }


def _projection_bindings(journal: ProjectJournal) -> dict[str, dict[str, Any]]:
    return {
        "target_binding": read_json(journal.target_binding_path, {}) or {},
        "style_binding": read_json(journal.style_binding_path, {}) or {},
    }


def _context_profile_projection(profile: dict[str, Any], *, task_id: str) -> dict[str, Any]:
    return {
        "dataset_context_profile_hash": profile.get("profile_hash"),
        "query_set_hash": profile.get("query_set_hash"),
        "dataset_schema_hash": profile.get("schema_hash"),
        "proof_level": profile.get("proof_level"),
        "dataset_data_semantics": profile.get("dataset_data_semantics"),
        "field_count": len(profile.get("fields") or []),
        "sample_scope": profile.get("sample_scope") or {},
        "selector_candidate_count": len(profile.get("selector_candidates") or []),
        "raw_rows_inline": False,
        "resource_uri": task_resource_uri(task_id, "data/context-profile.json"),
    }


def _authorization_path(journal: ProjectJournal) -> Path:
    return journal.execution_authorization_path


def _load_authorization(journal: ProjectJournal, contract: dict[str, Any]) -> dict[str, Any]:
    value = read_json(_authorization_path(journal), default={}) or {}
    issues = validate_execution_authorization(value, contract)
    if issues:
        raise JournalIdentityError("; ".join(issues))
    return value


def _ensure_task_plan(journal: ProjectJournal, contract: dict[str, Any], state) -> dict[str, Any]:
    existing = _load_task_plan(journal)
    if not existing or existing.get("contract_hash") != contract.get("contract_hash"):
        raise JournalIdentityError("validated workflow is missing its immutable public plan")
    issues = PublicPlanBuilder(journal, contract).validate_current()
    if issues:
        raise JournalIdentityError("PUBLIC_PLAN_INVALID: " + "; ".join(issues))
    return existing


def _load_task_plan(journal: ProjectJournal) -> dict[str, Any]:
    return read_json(journal.root / "plans" / "plan.json", default={}) or {}


def _delivery_intent_text(contract: dict[str, Any]) -> str:
    delivery = contract.get("delivery") or {}
    if not delivery.get("save"):
        return "plan only"
    if delivery.get("publish"):
        return "implement update and publish"
    return "implement update save only"


def _assert_expected_state(state, *, expected_state: str, expected_hash: str) -> None:
    if expected_state and public_task_state(state.current_state) != expected_state:
        raise JournalIdentityError("expected task state does not match persisted state")
    if expected_hash and task_state_etag(state) != expected_hash:
        raise JournalIdentityError("expected task hash does not match persisted state")


def _run_until(value: str) -> str:
    normalized = str(value or "plan_ready").strip().lower()
    if normalized not in RUN_UNTIL_VALUES:
        raise ValueError(f"run_until must be one of: {', '.join(sorted(RUN_UNTIL_VALUES))}")
    return normalized


def _destructive_token(task_id: str, plan_hash: str) -> str:
    return f"DELETE:{task_id}:{plan_hash[:12]}"
