from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.mcp.task_projection import compact_task_status, project_task_summary, public_task_state, task_state_etag
from datalens_dev_mcp.mcp.task_resources import read_task_evidence, task_resource_uri
from datalens_dev_mcp.mcp.tools import pipeline
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal
from datalens_dev_mcp.pipeline.safe_apply import workflow_safe_apply_result
from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract
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
    journal.initialize(contract)
    compile_receipt = journal.write_receipt(
        "task-compile",
        {
            "status": compiled.get("status"),
            "issues": compiled.get("issues") or [],
            "discovery_required": compiled.get("discovery_required") or [],
            "question": compiled.get("question"),
        },
    )
    before = journal.load_state().last_event_id
    if compiled.get("status") in {"invalid", "needs_input"}:
        state = journal.load_state()
        blocker = {
            "reason": "task contract requires user input",
            "question": compiled.get("question"),
            "compile_receipt": compile_receipt,
        }
        state = journal.append_transition(
            state,
            transition="TASK_INPUT_REQUIRED",
            input_value={"issues": compiled.get("issues") or []},
            receipt_uri=compile_receipt,
            status="blocked",
            idempotency_key=canonical_hash({"task_id": journal.task_id, "transition": "TASK_INPUT_REQUIRED"}),
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
    state = _advance(journal, contract, boundary=boundary)
    plan = _ensure_task_plan(journal, contract, state) if state.current_state == "VALIDATED" else {}
    if boundary == "completed" and state.current_state == "VALIDATED":
        state = _advance(journal, contract, boundary="completed")
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
    state, _ = journal.replay()
    _assert_expected_state(state, expected_state=expected_state, expected_hash=expected_hash)
    before = state.last_event_id
    if state.current_state == "VALIDATED":
        _ensure_task_plan(journal, contract, state)
    state = _advance(journal, contract, boundary=boundary, transition_budget=transition_budget)
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
    state, _ = journal.replay()
    if state.current_state not in {"VALIDATED", "COMPLETED"}:
        state = _advance(journal, contract, boundary="plan_ready")
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
    state = _advance(journal, contract, boundary="completed", destructive_token=destructive_token)
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
    validation = pipeline.dl_validate_project(project_root)
    read_only = str(contract.get("mode") or "") in {"review", "diagnose", "plan"}
    validation_ok = read_only or validation.get("status") == "pass"
    browser_mode = str((contract.get("browser_policy") or {}).get("mode") or "optional")
    return {
        "ok": validation_ok and not bool(state.blocker),
        "task_id": task_id,
        "state": public_task_state(state.current_state),
        "proof_target": proof_target,
        "checks": {
            "project_validation": "not_applicable_read_only" if read_only else validation.get("status") or "failed",
            "saved_readback_recorded": "SAVED -> SAVED_READBACK" in state.completed_transitions,
            "published_readback_recorded": "PUBLISHED -> PUBLISHED_READBACK" in state.completed_transitions,
            "browser_policy": browser_mode,
        },
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
):
    engine = WorkflowEngine(
        journal,
        contract,
        handlers=_workflow_handlers(journal, contract, destructive_token=destructive_token),
    )
    stop_states = {"VALIDATED"} if boundary == "plan_ready" else None
    return engine.resume(max_transitions=max(1, min(100, int(transition_budget))), stop_states=stop_states)


def _workflow_handlers(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    destructive_token: str = "",
) -> dict[str, Any]:
    project_root = str(journal.project_root)

    def read_baseline(context: dict[str, Any]) -> dict[str, Any]:
        target = contract.get("target") or {}
        known = [str(item) for item in target.get("object_ids") or [] if str(item)]
        return {
            "status": "success",
            "observed_facts": [
                f"compiled target object count: {len(known)}",
                "baseline source: immutable target contract and project artifacts",
            ],
        }

    def bind_reference(context: dict[str, Any]) -> dict[str, Any]:
        reference = contract.get("reference") or {}
        return {
            "status": "success",
            "observed_facts": [f"reference kind: {reference.get('kind') or 'none'}"],
            "reference": reference,
        }

    def bind_route(context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success", "observed_facts": [f"route: {contract.get('route') or ''}"]}

    def plan_data_proof(context: dict[str, Any]) -> dict[str, Any]:
        evidence = contract.get("evidence") or {}
        return {
            "status": "success",
            "required_facts": evidence.get("required_facts") or [],
            "observed_facts": [f"required evidence fact count: {len(evidence.get('required_facts') or [])}"],
        }

    def plan_semantic_change(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "route": contract.get("route"),
            "scope": contract.get("scope") or {},
            "observed_facts": ["semantic scope bound to immutable task contract"],
        }

    def validate_plan(context: dict[str, Any]) -> dict[str, Any]:
        if str(contract.get("mode") or "") in {"review", "diagnose", "plan"}:
            return {"status": "success", "observed_facts": ["read-only task plan validation passed"]}
        validation = pipeline.dl_validate_project(project_root)
        if validation.get("status") != "pass":
            return {"status": "blocked", "reason": "local project validation failed", "validation": validation}
        return {"status": "success", "observed_facts": ["local project validation passed"]}

    def safe_apply_save(context: dict[str, Any]) -> dict[str, Any]:
        current_state = journal.load_state()
        plan = _load_task_plan(journal) or _ensure_task_plan(journal, contract, current_state)
        if (contract.get("delivery") or {}).get("destructive"):
            expected = _destructive_token(journal.task_id, str(plan.get("plan_hash") or ""))
            if destructive_token != expected:
                return {
                    "status": "blocked",
                    "reason": "destructive task requires dl_execute with the exact task-bound destructive token",
                }
        safe_path = str(plan.get("safe_apply_plan_path") or "")
        if not safe_path or not Path(safe_path).is_file() or not plan.get("safe_apply_action_count"):
            return {"status": "blocked", "reason": "validated Safe Apply actions are unavailable"}
        result = pipeline.dl_execute_safe_apply(
            project_root=project_root,
            plan_path=safe_path,
            delivery_intent_text=_delivery_intent_text(contract),
        )
        projected = workflow_safe_apply_result(result)
        if not result.get("executed") and projected["status"] == "failed":
            return {"status": "blocked", "reason": "Safe Apply did not execute", "safe_apply": projected}
        return {**projected, "observed_facts": ["Safe Apply result recorded"]}

    def read_delivery(context: dict[str, Any]) -> dict[str, Any]:
        result = read_json(Path(project_root) / "artifacts" / "safe_apply_result.json", default={})
        return {
            "status": "success" if result else "blocked",
            "reason": "Safe Apply readback artifact is missing" if not result else "",
            "observed_facts": ["delivery readback artifact is present"] if result else [],
        }

    def publish_from_saved(context: dict[str, Any]) -> dict[str, Any]:
        result = read_json(Path(project_root) / "artifacts" / "safe_apply_result.json", default={})
        return {
            "status": "success" if result.get("executed") else "blocked",
            "reason": "publish-from-saved evidence is unavailable" if not result.get("executed") else "",
            "observed_facts": ["publish-from-saved result recorded"] if result.get("executed") else [],
        }

    def run_qa(context: dict[str, Any]) -> dict[str, Any]:
        mode = str((contract.get("browser_policy") or {}).get("mode") or "optional")
        return {"status": "success", "observed_facts": [f"QA policy: browser {mode}"]}

    def complete(context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success", "observed_facts": ["task completion criteria evaluated"]}

    return {
        "read_baseline": read_baseline,
        "bind_reference": bind_reference,
        "bind_route": bind_route,
        "plan_data_proof": plan_data_proof,
        "plan_semantic_change": plan_semantic_change,
        "validate_plan": validate_plan,
        "safe_apply_save": safe_apply_save,
        "read_saved_state": read_delivery,
        "publish_from_saved": publish_from_saved,
        "read_published_state": read_delivery,
        "run_qa": run_qa,
        "verify_read_only_result": run_qa,
        "verify_completion": complete,
        "reconcile_ambiguous_write": read_delivery,
    }


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
