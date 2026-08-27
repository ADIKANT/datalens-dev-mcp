from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.mcp.task_projection import compact_task_status, project_task_summary, public_task_state, task_state_etag
from datalens_dev_mcp.mcp.task_resources import read_task_evidence, task_resource_uri
from datalens_dev_mcp.mcp.tools import pipeline
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.build_identity import BuildIdentityResolver
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal
from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.pipeline.execution_authorization import (
    resolve_execution_authorization,
    validate_execution_authorization,
)
from datalens_dev_mcp.pipeline.task_completion import TaskCompletionEvaluator
from datalens_dev_mcp.pipeline.task_service_factory import create_autonomous_task_service
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding


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
    compiled = compile_task_contract(
        compile_request,
        project_root=str(Path(project_root).resolve()),
        reference={
            "kind": "live_object" if reference_locator else "none",
            "locator": reference_locator,
        },
        current_live={
            key: task_context[key]
            for key in ("workbook_id", "dashboard_id", "chart_id", "object_ids", "object_types")
            if key in task_context
        },
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
    if compiled.get("status") in {"invalid", "needs_input", "needs_discovery"}:
        discovery = compiled.get("status") == "needs_discovery"
        blocker = {
            "reason": "server-owned target discovery is required" if discovery else "task contract requires user input",
            "code": "BLOCKED_DISCOVERY" if discovery else "BLOCKED_INPUT",
            "question": None if discovery else compiled.get("question"),
            "missing_facts": compiled.get("discovery_required") or [],
            "compile_receipt": compile_receipt,
        }
        with journal.locked(owner="task-compile-blocker"):
            state, _ = journal.replay()
            state = journal.append_transition(
                state,
                transition="TASK_DISCOVERY_REQUIRED" if discovery else "TASK_INPUT_REQUIRED",
                input_value={"issues": compiled.get("issues") or []},
                receipt_uri=compile_receipt,
                status="blocked",
                idempotency_key=canonical_hash({
                    "task_id": journal.task_id,
                    "transition": "TASK_DISCOVERY_REQUIRED" if discovery else "TASK_INPUT_REQUIRED",
                }),
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
    )
    plan = _load_task_plan(journal)
    if plan and state.current_state == "VALIDATED":
        result.update({"plan_hash": plan.get("plan_hash"), "plan_resource_uri": task_resource_uri(task_id, "plans/plan.json")})
    return result


def dl_task_status(task_id: str, project_root: str = ".") -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    state, corrupt_tail = journal.replay()
    result = compact_task_status(contract, state, resource_uri=task_resource_uri(task_id))
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
    validation = pipeline.dl_validate_project(str(root))
    artifacts = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "artifacts").rglob("*")
        if path.is_file()
    )[:limit] if (root / "artifacts").is_dir() else []
    return {
        "ok": bool(validation.get("ok", True)),
        "task_id": task_id,
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
            **compact_task_status(contract, state, resource_uri=task_resource_uri(task_id)),
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
    plan = _load_task_plan(journal)
    if not plan or plan.get("plan_hash") != plan_hash:
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
    if existing and existing.get("contract_hash") == contract.get("contract_hash"):
        return existing
    safe_apply = pipeline.dl_create_safe_apply_plan(
        project_root=str(journal.project_root),
        delivery_intent_text=_delivery_intent_text(contract),
        target_known=bool((contract.get("target") or {}).get("object_ids")),
        target_workbook_id=str((contract.get("target") or {}).get("workbook_id") or ""),
        target_dashboard_id=str((contract.get("target") or {}).get("dashboard_id") or ""),
        target_chart_id=str(((contract.get("target") or {}).get("object_ids") or [""])[0]),
        task_contract_hash=str(contract.get("contract_hash") or ""),
    )
    safe_path = journal.root / "plans" / "safe-apply-plan.json"
    write_json(safe_path, safe_apply)
    payload = {
        "schema_id": "datalens_task_plan",
        "task_id": journal.task_id,
        "contract_hash": contract.get("contract_hash"),
        "state_etag": task_state_etag(state),
        "route": contract.get("route"),
        "delivery": contract.get("delivery") or {},
        "scope": contract.get("scope") or {},
        "safe_apply_plan_path": str(safe_path),
        "safe_apply_plan_sha256": canonical_hash(safe_apply),
        "safe_apply_action_count": len(safe_apply.get("actions") or []),
        "destructive_token_required": bool((contract.get("delivery") or {}).get("destructive")),
    }
    payload["plan_hash"] = canonical_hash(payload)
    write_json(journal.root / "plans" / "plan.json", payload)
    return payload


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
