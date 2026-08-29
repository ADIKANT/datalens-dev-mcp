from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError
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
from datalens_dev_mcp.pipeline.create_manifest import (
    CreateManifestError,
    load_create_bundle,
    validate_create_bundle,
)
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
from datalens_dev_mcp.pipeline.task_contract import task_contract_hash, validate_task_contract
from datalens_dev_mcp.pipeline.task_service_factory import create_autonomous_task_service
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

RUN_UNTIL_VALUES = frozenset({"blocked", "plan_ready", "completed"})
AMENDMENT_RELATIONSHIPS = frozenset(
    {
        "continue",
        "clarify",
        "correct_wrong_route",
        "correct_wrong_result",
        "extend_scope",
        "restrict_scope",
        "authorize_operation",
        "replace_goal",
        "start_new_workflow",
    }
)


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
        scope_overrides["allowed_objects"] = list(
            dict.fromkeys(
                [
                    *list(scope_overrides.get("allowed_objects") or []),
                    *[str(item.get("target_id") or item.get("object_id") or "") for item in semantic_changes],
                ]
            )
        )
        scope_overrides["allowed_tabs"] = list(
            dict.fromkeys(
                [
                    *list(scope_overrides.get("allowed_tabs") or []),
                    *[str(item.get("tab") or "") for item in semantic_changes],
                ]
            )
        )
        scope_overrides["allowed_semantic_slots"] = list(
            dict.fromkeys(
                [
                    *list(scope_overrides.get("allowed_semantic_slots") or []),
                    *[str(item.get("slot_id") or "") for item in semantic_changes],
                ]
            )
        )
    preliminary = compile_task_contract(
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
    create_bundle: dict[str, Any] = {}
    create_manifest = str(task_context.get("create_manifest") or "").strip()
    if create_manifest:
        if str((preliminary.get("contract") or {}).get("mode") or "") != "create":
            raise CreateManifestError("create_manifest is valid only for a create request")
        create_bundle = load_create_bundle(
            project_root,
            create_manifest,
            workbook_id=str(task_context.get("workbook_id") or ""),
            direct_ql_requested=str((preliminary.get("contract") or {}).get("route") or "") == "ql_explicit",
        )
        task_context["workbook_id"] = str(create_bundle["workbook_id"])
        acceptance.append(
            {
                "kind": "create_manifest",
                "statement": json.dumps(
                    {
                        "bundle_hash": create_bundle["bundle_hash"],
                        "manifest_hash": create_bundle["manifest_hash"],
                        "object_count": create_bundle["object_count"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "source": "current_user_request",
                "hard": True,
            }
        )
        preliminary = compile_task_contract(
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
    compiled = preliminary
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
    if create_bundle:
        create_bundle_path = journal.root / "inputs" / "create-bundle.json"
        existing_bundle = read_json(create_bundle_path, {}) or {}
        if existing_bundle and existing_bundle != create_bundle:
            raise JournalIdentityError("CREATE_MANIFEST_CONFLICT: persisted create bundle changed")
        if validate_create_bundle(create_bundle):
            raise JournalIdentityError("CREATE_MANIFEST_INVALID: create bundle failed validation")
        if not existing_bundle:
            write_json(create_bundle_path, create_bundle)
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
    typed_target = contract.get("target") or {}
    requires_live_discovery = bool(
        typed_target.get("workbook_id")
        or typed_target.get("dashboard_id")
        or typed_target.get("chart_id")
        or typed_target.get("object_ids")
    )
    if compiled.get("status") == "needs_discovery" or bool(create_bundle) or requires_live_discovery:
        compiled_target_url = str((compiled.get("source_trace") or {}).get("target_url") or "")
        try:
            discovery = TargetDiscoveryService(
                max_objects=int(task_context.get("max_discovery_objects") or 50)
            ).discover(
                contract,
                request_text=compile_request,
                target_url=target_url or compiled_target_url,
            )
        except DataLensApiError as exc:
            status = int(exc.http_status) if isinstance(exc.http_status, int) else None
            if status in {401, 403}:
                category = "authorization_or_access_denied"
            elif status == 404:
                category = "target_not_found"
            elif exc.transport_category or exc.failure_family:
                category = "transport_failure"
            else:
                category = "provider_failure"
            discovery = {
                "status": "blocked",
                "reason": f"live target discovery provider read failed: {category}",
                "missing_facts": compiled.get("discovery_required") or [],
                "question": None,
                "provider_calls": [
                    {
                        "method": str(getattr(exc, "provider_method", "target_discovery") or "target_discovery"),
                        "status": "failed",
                        "effect": "read",
                        "failure_category": category,
                        "http_status": status,
                        "response_received": exc.response_received,
                    }
                ],
            }
        except Exception as exc:  # noqa: BLE001
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
                f"style-binding-blocked-{canonical_hash(style)[:16]}",
                style,
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
        result.update(
            {"plan_hash": plan["plan_hash"], "plan_resource_uri": task_resource_uri(journal.task_id, "plans/plan.json")}
        )
    return result


def dl_task_resume(
    task_id: str,
    project_root: str = ".",
    expected_state: str = "",
    expected_hash: str = "",
    run_until: str = "completed",
    transition_budget: int = 20,
    expected_contract_revision: int = 0,
    user_turn: dict[str, Any] | None = None,
) -> dict[str, Any]:
    boundary = _run_until(run_until)
    journal = ProjectJournal(project_root, task_id)
    amendment_result: dict[str, Any] = {}
    if user_turn is not None:
        amendment_result = _amend_task(
            journal,
            user_turn=user_turn,
            expected_contract_revision=expected_contract_revision,
            expected_state=expected_state,
            expected_hash=expected_hash,
        )
        expected_state = ""
        expected_hash = ""
    contract = journal.load_contract()
    grant = _load_authorization(journal, contract)
    state, _ = journal.replay()
    _assert_expected_state(state, expected_state=expected_state, expected_hash=expected_hash)
    before = state.last_event_id
    if state.current_state == "VALIDATED":
        _ensure_task_plan(journal, contract, state)
    state = _advance(
        journal,
        contract,
        boundary=boundary,
        transition_budget=transition_budget,
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
    result.update(_contract_revision_projection(contract))
    if amendment_result:
        result["amendment"] = amendment_result
    plan = _load_task_plan(journal)
    if plan and state.current_state == "VALIDATED":
        result.update(
            {"plan_hash": plan.get("plan_hash"), "plan_resource_uri": task_resource_uri(task_id, "plans/plan.json")}
        )
    return result


def dl_task_status(task_id: str, project_root: str = ".") -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    state, corrupt_tail = journal.replay()
    result = compact_task_status(
        contract, state, resource_uri=task_resource_uri(task_id), **_projection_bindings(journal)
    )
    result["journal_recovered"] = corrupt_tail
    result.update(_contract_revision_projection(contract))
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
    from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

    launcher_parity = dl_runtime_status(project_root=str(root)).get("launcher_parity") or {}
    artifacts = (
        sorted(path.relative_to(root).as_posix() for path in (root / "artifacts").rglob("*") if path.is_file())[:limit]
        if (root / "artifacts").is_dir()
        else []
    )
    return {
        "ok": bool(validation.get("ok", True)),
        "task_id": task_id,
        "graph_kind": "local_project_graph",
        "target_url_present": bool(target_url),
        "project_validation": {
            "status": validation.get("status"),
            "issue_count": len(validation.get("issues") or []),
        },
        "runtime_identity": {"launcher_parity": launcher_parity},
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
            journal,
            contract,
            boundary="plan_ready",
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
        "operation_kind": str(contract.get("operation_kind") or "inspect"),
        "effect": contract.get("effect") or {},
        "verification": contract.get("verification") or {},
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
    stop_after: str = "completed",
) -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    _assert_current_identity(journal, contract)
    state, _ = journal.replay()
    if stop_after not in {"saved", "completed"}:
        raise ValueError("stop_after must be saved or completed")
    delivery_states = {"VALIDATED", "SAVED", "SAVED_READBACK", "PUBLISHED", "PUBLISHED_READBACK", "RECONCILING"}
    if state.current_state not in delivery_states:
        raise ValueError(
            f"dl_execute requires a resumable delivery state, current state is {public_task_state(state.current_state)}"
        )
    plan = _ensure_task_plan(journal, contract, state)
    if plan.get("plan_hash") != plan_hash:
        raise ValueError("plan_hash does not match the immutable task plan")
    if (contract.get("delivery") or {}).get("destructive"):
        expected = _destructive_token(task_id, plan_hash)
        if destructive_token != expected:
            raise ValueError("destructive task requires the exact task-bound destructive token")
    before = state.last_event_id
    state = _advance(
        journal,
        contract,
        boundary=stop_after,
        destructive_token=destructive_token,
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


def _amend_task(
    journal: ProjectJournal,
    *,
    user_turn: dict[str, Any],
    expected_contract_revision: int,
    expected_state: str,
    expected_hash: str,
) -> dict[str, Any]:
    request = str(user_turn.get("request") or "").strip()
    relationship = str(user_turn.get("relationship_to_previous") or "").strip()
    source_event_id = str(user_turn.get("source_event_id") or "").strip()
    context = user_turn.get("context") if isinstance(user_turn.get("context"), dict) else {}
    unknown = sorted(set(user_turn) - {"source_event_id", "request", "relationship_to_previous", "context"})
    if unknown:
        raise ValueError("user_turn contains unknown fields: " + ", ".join(unknown))
    if not request:
        raise ValueError("user_turn.request must not be empty")
    if relationship not in AMENDMENT_RELATIONSHIPS:
        raise ValueError("user_turn.relationship_to_previous is required and unsupported")
    if relationship in {"replace_goal", "start_new_workflow"}:
        raise JournalIdentityError("NEW_TASK_REQUIRED: replacement goals and new workflows must use dl_task_start")
    if int(expected_contract_revision or 0) < 1:
        raise JournalIdentityError(
            "EXPECTED_CONTRACT_REVISION_REQUIRED: amendment requires an explicit current contract revision"
        )

    old = journal.load_contract()
    current_revision = int(old.get("contract_revision") or 1)
    source_turn_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
    revision_index = read_json(journal.contract_revisions_path, {}) or {}
    delivered = next(
        (
            item
            for item in revision_index.get("amendments") or []
            if str(item.get("source_event_id") or "") == source_event_id
            and str(item.get("source_turn_hash") or "") == source_turn_hash
        ),
        None,
    )
    if delivered:
        return {
            "status": "duplicate",
            "contract_revision": current_revision,
            "contract_hash": old.get("contract_hash"),
            "source_turn_hash": source_turn_hash,
            "receipt_uri": delivered.get("receipt_uri"),
            "invalidated_artifacts": [],
            "preserved_artifacts": ["current_contract_revision", "task_history"],
        }
    amendment_key = canonical_hash(
        {
            "source_event_id": source_event_id,
            "request_hash": source_turn_hash,
            "parent_contract_hash": old.get("contract_hash"),
        }
    )
    persisted_old_target = deepcopy(old.get("target") or {})
    old_target = deepcopy(persisted_old_target)
    old_target["technology"] = str(old_target.get("technology") or old.get("route") or "")
    old_scope = deepcopy(old.get("scope") or {})
    requested_scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    scope = {**old_scope, **requested_scope}
    acceptance = [deepcopy(item) for item in old.get("acceptance") or []]
    acceptance.extend(deepcopy(item) for item in context.get("acceptance") or [])
    reference = deepcopy(old.get("reference") or {})
    if str(context.get("reference_locator") or "").strip():
        reference["locator"] = str(context["reference_locator"]).strip()
        reference["kind"] = "live_object"
    target_url = str(context.get("target_url") or "").strip()
    compile_request = "Continue the current typed task contract."
    correction_text = request + (f"\nTarget: {target_url}" if target_url and target_url not in request else "")
    compiled = compile_task_contract(
        compile_request,
        project_root=str((old.get("workspace") or {}).get("project_root") or journal.project_root),
        portfolio_subproject=str((old.get("workspace") or {}).get("portfolio_subproject") or ""),
        config_path=str((old.get("workspace") or {}).get("config_path") or ""),
        current_live=old_target,
        current_task_journal=old,
        corrections=[*list(old.get("corrections") or []), correction_text],
        scope_overrides=scope,
        reference=reference,
        acceptance=acceptance,
        task_id=journal.task_id,
        contract_revision=current_revision + 1,
        parent_contract_hash=str(old.get("contract_hash") or ""),
        source_turn_hash=source_turn_hash,
        semantic_delta_hash=source_turn_hash,
        scope_revision=int(old.get("scope_revision") or 1),
        authorization_revision=int(old.get("authorization_revision") or 1),
    )
    if compiled.get("status") in {"invalid", "needs_input"}:
        raise JournalIdentityError(
            "CONTRACT_AMENDMENT_INPUT_REQUIRED: "
            + str((compiled.get("question") or {}).get("question") or compiled.get("issues") or "invalid amendment")
        )
    new_contract = dict(compiled["contract"])
    # The persisted target technology is a fresh-discovery fact.  Supplying
    # the existing route above lets an unspecified follow-up preserve its
    # technology choice, but must not manufacture a target change that would
    # force live rediscovery in an otherwise semantic-only amendment.
    if isinstance(new_contract.get("target"), dict):
        new_contract["target"]["technology"] = str(persisted_old_target.get("technology") or "")
    browser_policy = str(context.get("browser_policy") or "").strip()
    if browser_policy:
        if browser_policy not in {"forbidden", "optional", "required"}:
            raise ValueError("user_turn.context.browser_policy must be forbidden, optional, or required")
        new_contract["browser_policy"] = {"mode": browser_policy, "source": "explicit_user"}

    semantic_fields = (
        "mode",
        "operation_kind",
        "effect",
        "verification",
        "route",
        "target",
        "scope",
        "reference",
        "browser_policy",
        "delivery",
        "evidence",
        "acceptance",
        "stop_conditions",
    )
    delta = {
        key: {"before": old.get(key), "after": new_contract.get(key)}
        for key in semantic_fields
        if old.get(key) != new_contract.get(key)
    }
    if not delta:
        return {
            "status": "no_semantic_change",
            "contract_revision": current_revision,
            "source_turn_hash": source_turn_hash,
            "invalidated_artifacts": ["summary/presentation"],
            "preserved_artifacts": ["discovery", "bindings", "plan", "receipts"],
        }
    if relationship == "restrict_scope" and not _scope_is_narrower(old_scope, new_contract.get("scope") or {}):
        raise JournalIdentityError("AMENDMENT_RELATION_CONFLICT: restrict_scope broadened the persisted scope")
    if relationship == "authorize_operation" and "delivery" not in delta:
        raise JournalIdentityError(
            "AMENDMENT_RELATION_CONFLICT: authorize_operation did not change delivery authorization"
        )
    if relationship in {"continue", "clarify"} and "target" in delta:
        raise JournalIdentityError(
            "AMENDMENT_RELATION_CONFLICT: a target change requires an explicit correction or scope relation"
        )

    semantic_delta_hash = canonical_hash(delta)
    new_contract["semantic_delta_hash"] = semantic_delta_hash
    new_contract["scope_revision"] = int(old.get("scope_revision") or 1) + (1 if "scope" in delta else 0)
    new_contract["authorization_revision"] = int(old.get("authorization_revision") or 1) + (
        1 if "delivery" in delta else 0
    )
    new_contract["contract_hash"] = task_contract_hash(new_contract)
    issues = validate_task_contract(new_contract)
    if issues:
        raise JournalIdentityError("CONTRACT_AMENDMENT_INVALID: " + "; ".join(issues))

    impact = _amendment_impact(delta, journal)
    build_identity = BuildIdentityResolver().resolve()
    persisted_build = read_json(journal.build_identity_path, {}) or {}
    if persisted_build.get("identity_hash") != build_identity.get("identity_hash"):
        raise JournalIdentityError(
            "SOURCE_IDENTITY_CONFLICT: server build/source tree changed; amendment requires an exact compatible build"
        )

    discovery_values: dict[str, Any] = {}
    if "target" in delta or "reference" in delta or impact["requires_fresh_discovery"]:
        try:
            discovered = TargetDiscoveryService(max_objects=int(context.get("max_discovery_objects") or 50)).discover(
                new_contract, request_text=correction_text, target_url=target_url
            )
        except Exception as exc:
            raise JournalIdentityError(f"CONTRACT_AMENDMENT_DISCOVERY_BLOCKED: {exc.__class__.__name__}") from exc
        if discovered.get("status") != "success":
            raise JournalIdentityError(
                "CONTRACT_AMENDMENT_DISCOVERY_BLOCKED: "
                + str(discovered.get("reason") or "fresh target discovery is incomplete")
            )
        style = ReferenceStyleService().bind(
            new_contract,
            target_graph=dict(discovered["target_graph"]),
            baselines=dict(discovered.get("baselines") or {}),
            portfolio_root=str(context.get("portfolio_root") or ""),
        )
        if style.get("status") != "success":
            raise JournalIdentityError(
                "CONTRACT_AMENDMENT_STYLE_BLOCKED: " + str(style.get("reason") or "style binding is incomplete")
            )
        discovery_values = {
            "target_binding": dict(discovered["target_binding"]),
            "target_graph": dict(discovered["target_graph"]),
            "reference_binding": dict(style["reference_binding"]),
            "style_binding": dict(style["style_binding"]),
            "discovery": {
                "schema_id": "datalens_target_discovery_receipt",
                "status": "success",
                "observed_at": discovered.get("observed_at"),
                "provider_calls": discovered.get("provider_calls") or [],
                "technology": discovered.get("technology"),
                "tab_count": discovered.get("tab_count", 0),
                "dataset_count": discovered.get("dataset_count", 0),
                "field_count": discovered.get("field_count", 0),
                "target_binding_hash": discovered["target_binding"].get("binding_hash"),
                "target_graph_hash": discovered["target_graph"].get("graph_hash"),
                "reference_binding_hash": style["reference_binding"].get("binding_hash"),
                "style_binding_hash": style["style_binding"].get("binding_hash"),
            },
            "baselines": dict(discovered.get("baselines") or {}),
        }
    grant = resolve_execution_authorization(new_contract)
    state, record, created = journal.install_contract_amendment(
        expected_contract_revision=int(expected_contract_revision),
        expected_state=expected_state,
        expected_hash=expected_hash,
        amendment_key=amendment_key,
        amendment={
            "source_event_id": source_event_id,
            "relationship_to_previous": relationship,
            "semantic_delta": sorted(delta),
        },
        new_contract=new_contract,
        execution_grant=grant,
        next_state=impact["next_state"],
        next_transition=impact["next_transition"],
        invalidated_artifacts=impact["invalidated"],
        preserved_artifacts=impact["preserved"],
        build_identity=build_identity,
        **discovery_values,
    )
    return {
        "status": "accepted" if created else "duplicate",
        "contract_revision": int(new_contract.get("contract_revision") or current_revision),
        "scope_revision": int(new_contract.get("scope_revision") or 1),
        "authorization_revision": int(new_contract.get("authorization_revision") or 1),
        "parent_contract_hash": old.get("contract_hash"),
        "contract_hash": new_contract.get("contract_hash"),
        "source_turn_hash": source_turn_hash,
        "semantic_delta_hash": semantic_delta_hash,
        "semantic_delta": sorted(delta),
        "invalidated_artifacts": impact["invalidated"],
        "preserved_artifacts": impact["preserved"],
        "receipt_uri": record.get("receipt_uri"),
        "state_after_amendment": public_task_state(state.current_state),
    }


def _scope_is_narrower(before: dict[str, Any], after: dict[str, Any]) -> bool:
    for key in ("allowed_objects", "allowed_tabs", "allowed_semantic_slots"):
        old_values = set(before.get(key) or [])
        new_values = set(after.get(key) or [])
        if old_values and not new_values.issubset(old_values):
            return False
    return set(before.get("forbidden_changes") or []).issubset(set(after.get("forbidden_changes") or []))


def _amendment_impact(delta: dict[str, Any], journal: ProjectJournal) -> dict[str, Any]:
    state, _ = journal.replay()
    after_save = state.current_state in {"SAVED", "SAVED_READBACK", "PUBLISHED", "PUBLISHED_READBACK", "QA_COMPLETED"}
    changed = set(delta)
    if "target" in changed:
        next_state, next_transition = "RESOLVED", "RESOLVED -> BASELINE_READ"
        invalidated = ["target_binding", "reference_binding", "style_binding", "data_profile", "plan", "delivery", "qa"]
        preserved = ["build_identity", "task_history", "prior_contract_revisions"]
    elif "reference" in changed:
        next_state, next_transition = "BASELINE_READ", "BASELINE_READ -> REFERENCE_BOUND"
        invalidated = ["style_binding", "plan", "delivery", "qa"]
        preserved = ["target_binding", "target_graph", "data_profile", "task_history"]
    elif "evidence" in changed:
        next_state, next_transition = "ROUTE_BOUND", "ROUTE_BOUND -> DATA_PROOF_PLANNED"
        invalidated = ["data_profile", "plan", "delivery", "qa"]
        preserved = ["target_binding", "reference_binding", "style_binding", "task_history"]
    else:
        next_state, next_transition = "DATA_PROOF_PLANNED", "DATA_PROOF_PLANNED -> SEMANTIC_PLAN_READY"
        invalidated = ["semantic_plan", "public_plan", "delivery", "qa"]
        preserved = [
            "target_binding",
            "target_graph",
            "reference_binding",
            "style_binding",
            "data_profile",
            "task_history",
        ]
    if after_save:
        # A semantic follow-up after save must plan against the newly-saved
        # revision, not the discovery snapshot from before the prior write.
        # Force a fresh provider discovery and replay the baseline/binding
        # stages before materializing the amended plan.
        next_state, next_transition = "RESOLVED", "RESOLVED -> BASELINE_READ"
        invalidated.extend(
            [
                "target_binding",
                "target_graph",
                "reference_binding",
                "style_binding",
                "data_profile",
                "semantic_plan",
                "public_plan",
                "publish_plan",
                "publish_authorization",
                "qa",
            ]
        )
        preserved = [
            item
            for item in preserved
            if item not in {"target_binding", "target_graph", "reference_binding", "style_binding", "data_profile"}
        ]
        preserved.extend(["saved_state_receipt", "saved_readback_receipt"])
    return {
        "next_state": next_state,
        "next_transition": next_transition,
        "invalidated": list(dict.fromkeys(invalidated)),
        "preserved": list(dict.fromkeys(preserved)),
        "requires_fresh_discovery": after_save,
    }


def _contract_revision_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_revision": int(contract.get("contract_revision") or 1),
        "scope_revision": int(contract.get("scope_revision") or 1),
        "authorization_revision": int(contract.get("authorization_revision") or 1),
        "contract_hash": str(contract.get("contract_hash") or ""),
    }


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
    stop_states = {"VALIDATED"} if boundary == "plan_ready" else {"SAVED"} if boundary == "saved" else None
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
                "canonical_direct_url": item.get("canonical_direct_url"),
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
