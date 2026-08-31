from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.local_config import is_project_live_manifest_payload
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
from datalens_dev_mcp.pipeline.semantic_change_planner import SemanticChangePlanner
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService, compact_object_index
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
PROJECT_MANIFEST_NAMES = (".datalens-mcp.json", "datalens-mcp.project.json")


def dl_task_start(
    request: str,
    project_root: str = ".",
    context: dict[str, Any] | None = None,
    run_until: str = "plan_ready",
) -> dict[str, Any]:
    project_root = _request_project_root(request, project_root)
    boundary = _run_until(run_until)
    task_context = dict(context or {})
    manifest_target = _project_manifest_target_context(project_root)
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
    current_live = {
        **manifest_target,
        **{
            key: task_context[key]
            for key in ("workbook_id", "dashboard_id", "chart_id", "object_ids", "object_types")
            if key in task_context
        },
    }
    preliminary = compile_task_contract(
        compile_request,
        project_root=str(Path(project_root).resolve()),
        reference={
            "kind": reference_kind if reference_locator else "none",
            "locator": reference_locator,
        },
        current_live=current_live,
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
        current_live["workbook_id"] = task_context["workbook_id"]
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
            current_live=current_live,
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
            discovery = _provider_discovery_failure(
                exc,
                missing_facts=compiled.get("discovery_required") or [],
            )
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
                retryable=bool(discovery.get("recovery_action")),
            )
        style = _bind_style_with_reference_discovery(
            contract,
            discovery=discovery,
            context=task_context,
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
    semantic_gate = _semantic_action_gate(journal, contract)
    if semantic_gate:
        current, _ = journal.replay()
        return _project_semantic_action_gate(
            journal,
            contract,
            state=current,
            before=before,
            outcome=semantic_gate,
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
    _attach_object_index(result, journal)
    if plan:
        result.update(
            {"plan_hash": plan["plan_hash"], "plan_resource_uri": task_resource_uri(journal.task_id, "plans/plan.json")}
        )
        result["semantic_state"] = str(plan.get("semantic_state") or "semantic_plan_ready")
        if plan.get("semantic_state") == "already_satisfied_no_write":
            result["state"] = "already_satisfied_no_write"
            result["matched_assertions"] = list(plan.get("matched_assertions") or [])
    return result


def _project_manifest_target_context(project_root: str) -> dict[str, str]:
    root = Path(project_root).resolve()
    manifest: dict[str, Any] = {}
    for name in PROJECT_MANIFEST_NAMES:
        candidate = root / name
        if candidate.is_file():
            value = read_json(candidate, {}) or {}
            manifest = value if isinstance(value, dict) else {}
            break
    if not is_project_live_manifest_payload(manifest):
        return {}
    target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}
    workbooks = {
        str(value).strip()
        for value in (manifest.get("workbook_id"), target.get("workbook_id"))
        if str(value or "").strip()
    }
    dashboard_values: list[Any] = [
        manifest.get("dashboard_id"),
        target.get("dashboard_id"),
    ]
    for value in (manifest.get("dashboard_ids"), target.get("dashboard_ids")):
        if isinstance(value, list):
            dashboard_values.extend(value)
    dashboards = {str(value).strip() for value in dashboard_values if str(value or "").strip()}
    result: dict[str, str] = {}
    if len(workbooks) == 1:
        result["workbook_id"] = next(iter(workbooks))
    if len(dashboards) == 1:
        result["dashboard_id"] = next(iter(dashboards))
    return result


def _request_project_root(request: str, supplied_root: str) -> str:
    """Resolve an explicit child project path without searching sibling projects."""

    root = Path(supplied_root).resolve()
    candidates: list[tuple[int, int, Path]] = []
    path_pattern = re.compile(
        r"(?:'(?P<single>/[^']+)'|\"(?P<double>/[^\"]+)\"|"
        r"(?<![:\w])(?P<bare>/[^'\"\n]+?)(?=\s+-\s+|[,.!?;]|$))"
    )
    for match_index, match in enumerate(path_pattern.finditer(request)):
        raw = str(
            match.group("single") or match.group("double") or match.group("bare") or ""
        ).strip().rstrip(".,;:")
        if not raw.startswith("/"):
            continue
        candidate = Path(raw).resolve()
        if candidate != root and root not in candidate.parents:
            continue
        if not candidate.is_dir():
            continue
        if any((candidate / name).is_file() for name in PROJECT_MANIFEST_NAMES):
            vicinity = request[max(0, match.start() - 180):match.start()].lower()
            score = 0
            if re.search(r"(?:работ\w*\s+.*(?:проект|папк)|рабоч\w*\s+папк|project\s+root|working\s+project)", vicinity):
                score += 100
            if re.search(r"(?:а\s+это\s+дашборд|построен\w*\s+на\s+основе|context|reference)", vicinity):
                score -= 40
            candidates.append((score, match_index, candidate))
    if candidates:
        return str(max(candidates, key=lambda item: (item[0], item[1]))[2])
    return str(root)


def _bind_style_with_reference_discovery(
    contract: dict[str, Any],
    *,
    discovery: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Keep target and exact-reference reads separate while binding one style contract."""

    target_graph = dict(discovery["target_graph"])
    target_baselines = dict(discovery.get("baselines") or {})
    reference = contract.get("reference") if isinstance(contract.get("reference"), dict) else {}
    locator = str(reference.get("locator") or "")
    kind = str(reference.get("kind") or "")
    reference_graph: dict[str, Any] = {}
    reference_baselines: dict[str, dict[str, Any]] = {}
    reference_calls: list[dict[str, Any]] = []
    if locator and kind == "live_object":
        workspace = contract.get("workspace") if isinstance(contract.get("workspace"), dict) else {}
        compiled = compile_task_contract(
            f"Inspect DataLens reference target {locator}",
            project_root=str(workspace.get("project_root") or "."),
        )
        reference_discovery = TargetDiscoveryService(
            max_objects=int(context.get("max_reference_objects") or 12)
        ).discover(
            dict(compiled["contract"]),
            request_text=locator,
            target_url=locator,
        )
        if reference_discovery.get("status") != "success":
            return {
                "status": "blocked",
                "reason": "exact reference discovery is incomplete: "
                + str(reference_discovery.get("reason") or "reference target is unavailable"),
                "reference_discovery": reference_discovery,
            }
        reference_graph = dict(reference_discovery["target_graph"])
        reference_baselines = dict(reference_discovery.get("baselines") or {})
        reference_calls = list(reference_discovery.get("provider_calls") or [])
    result = ReferenceStyleService().bind(
        contract,
        target_graph=target_graph,
        baselines=target_baselines,
        reference_target_graph=reference_graph,
        reference_baselines=reference_baselines,
        portfolio_root=str(context.get("portfolio_root") or ""),
    )
    if reference_calls:
        result["reference_provider_calls"] = reference_calls
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
    if user_turn is None and _discovery_recovery_required(state, journal):
        recovery_source = (
            "BLOCKED_DISCOVERY"
            if _blocked_discovery_is_retryable(state)
            else "INTERRUPTED_OR_INCOMPLETE_DISCOVERY"
        )
        state, blocked_result = _retry_blocked_discovery(
            journal,
            contract,
            state,
            before=before,
            recovery_source=recovery_source,
        )
        if blocked_result is not None:
            return blocked_result
    if state.current_state == "VALIDATED":
        _ensure_task_plan(journal, contract, state)
    semantic_gate = _semantic_action_gate(journal, contract)
    if semantic_gate:
        projected = _project_semantic_action_gate(
            journal,
            contract,
            state=state,
            before=before,
            outcome=semantic_gate,
        )
        if amendment_result:
            projected["amendment"] = amendment_result
        return projected
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
    _attach_object_index(result, journal)
    result.update(_contract_revision_projection(contract))
    if amendment_result:
        result["amendment"] = amendment_result
    plan = _load_task_plan(journal)
    if plan and state.current_state == "VALIDATED":
        result.update(
            {"plan_hash": plan.get("plan_hash"), "plan_resource_uri": task_resource_uri(task_id, "plans/plan.json")}
        )
        result["semantic_state"] = str(plan.get("semantic_state") or "semantic_plan_ready")
        if plan.get("semantic_state") == "already_satisfied_no_write":
            result["state"] = "already_satisfied_no_write"
            result["matched_assertions"] = list(plan.get("matched_assertions") or [])
    return result


def dl_task_status(task_id: str, project_root: str = ".") -> dict[str, Any]:
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    state, corrupt_tail = journal.replay()
    result = compact_task_status(
        contract, state, resource_uri=task_resource_uri(task_id), **_projection_bindings(journal)
    )
    _attach_object_index(result, journal)
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
        "semantic_state": str(plan.get("semantic_state") or "semantic_plan_ready"),
        "matched_assertions": list(plan.get("matched_assertions") or []),
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


def _amendment_current_live_target(
    old_target: dict[str, Any],
    semantic_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    current_live = deepcopy(old_target)
    semantic_target_ids = [
        str(item.get("target_id") or item.get("object_id") or "")
        for item in semantic_changes
        if str(item.get("target_id") or item.get("object_id") or "")
    ]
    if semantic_target_ids:
        current_live["object_ids"] = list(
            dict.fromkeys([*list(current_live.get("object_ids") or []), *semantic_target_ids])
        )
    return current_live


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
    persisted_route = str(old.get("route") or "")
    old_target["technology"] = str(
        old_target.get("technology")
        or (persisted_route if persisted_route in {
            "editor_advanced", "editor_table", "editor_markdown", "editor_js_control",
            "wizard_native", "ql_explicit",
        } else "")
    )
    old_scope = deepcopy(old.get("scope") or {})
    requested_scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    scope = {**old_scope, **requested_scope}
    semantic_changes = [item for item in context.get("semantic_changes") or [] if isinstance(item, dict)]
    if semantic_changes:
        scope["allowed_objects"] = list(
            dict.fromkeys(
                [
                    *list(scope.get("allowed_objects") or []),
                    *[
                        str(item.get("target_id") or item.get("object_id") or "")
                        for item in semantic_changes
                        if str(item.get("target_id") or item.get("object_id") or "")
                    ],
                ]
            )
        )
        scope["allowed_tabs"] = list(
            dict.fromkeys(
                [
                    *list(scope.get("allowed_tabs") or []),
                    *[str(item.get("tab") or "") for item in semantic_changes if str(item.get("tab") or "")],
                ]
            )
        )
        scope["allowed_semantic_slots"] = list(
            dict.fromkeys(
                [
                    *list(scope.get("allowed_semantic_slots") or []),
                    *[
                        str(item.get("slot_id") or "")
                        for item in semantic_changes
                        if str(item.get("slot_id") or "")
                    ],
                ]
            )
        )
    acceptance = [deepcopy(item) for item in old.get("acceptance") or []]
    acceptance.extend(deepcopy(item) for item in context.get("acceptance") or [])
    acceptance.extend(
        {
            "kind": "semantic_change",
            "statement": json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "source": "current_user_correction",
            "hard": True,
        }
        for item in semantic_changes
    )
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
        current_live=_amendment_current_live_target(old_target, semantic_changes),
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
        amended_browser_policy = dict(new_contract.get("browser_policy") or {})
        amended_browser_policy.update(
            {
                "mode": browser_policy,
                "source": "explicit_user",
                "applicability": "not_applicable" if browser_policy == "forbidden" else "applicable",
                "purpose": (
                    "runtime_visual_evidence" if browser_policy == "forbidden" else "final_visual_acceptance"
                ),
                "read_only": True,
                "mutation_allowed": False,
                "earliest_stage": (
                    "qa" if browser_policy == "forbidden" else "published_readback_and_api_diagnostics_complete"
                ),
                "calls_before_earliest_stage_allowed": False,
                "allowed_interactions": (
                    []
                    if browser_policy == "forbidden"
                    else ["activate_tab", "scroll", "hover_visual_detail", "read_only_error_detail"]
                ),
            }
        )
        new_contract["browser_policy"] = amended_browser_policy

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
        "data_diagnostics",
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
        style = _bind_style_with_reference_discovery(
            new_contract,
            discovery=discovered,
            context=context,
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
    elif changed & {"evidence", "data_diagnostics"}:
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
    retryable: bool = False,
) -> dict[str, Any]:
    blocker = {
        "reason": reason,
        "code": code,
        "question": question,
        "missing_facts": list(missing_facts),
        "receipt": receipt_uri,
        "retryable": bool(retryable),
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


def _blocked_discovery_is_retryable(state: Any) -> bool:
    blocker = dict(state.blocker or {})
    if state.current_state != "BLOCKED" or str(blocker.get("code") or "") != "BLOCKED_DISCOVERY":
        return False
    if "retryable" in blocker:
        return bool(blocker.get("retryable"))
    # Compatibility for provider blockers persisted before the typed flag was
    # added. Missing-target and missing-reference discovery boundaries use
    # different reason prefixes and therefore remain idempotently blocked.
    return str(blocker.get("reason") or "").startswith(
        "live target discovery provider read failed:"
    )


def _discovery_recovery_required(state: Any, journal: ProjectJournal) -> bool:
    if _blocked_discovery_is_retryable(state):
        return True
    if state.current_state == "BLOCKED":
        blocker = dict(state.blocker or {})
        details = dict(blocker.get("details") or {})
        missing = {str(value) for value in details.get("missing_requirements") or []}
        return (
            str(blocker.get("reason") or "") == "live target discovery is unavailable"
            and bool(missing & {"live_target_binding", "target_graph"})
        )
    if state.current_state != "RESOLVED":
        return False
    target = read_json(journal.target_binding_path, {}) or {}
    graph = read_json(journal.target_graph_path, {}) or {}
    return target.get("source") != "live_discovery" or not graph.get("graph_hash")


def _provider_discovery_failure(
    exc: DataLensApiError,
    *,
    missing_facts: list[str],
) -> dict[str, Any]:
    status = int(exc.http_status) if isinstance(exc.http_status, int) else None
    failure_family = str(exc.failure_family or "")
    transport_category = str(exc.transport_category or "")
    if status == 401 or failure_family == "AUTH_401_TOKEN_INVALID_OR_EXPIRED":
        category = "credential_recovery_required"
        recovery_action = "run launcher --recover-credentials, then resume the same task"
    elif status == 403 or failure_family == "AUTH_403_PERMISSION_DENIED":
        category = "access_denied"
        recovery_action = "verify target access without changing owner ACL"
    elif status == 404 or failure_family == "NOT_FOUND_404":
        category = "target_not_found"
        recovery_action = "refresh the exact target binding"
    elif transport_category:
        category = transport_category
        recovery_action = "retry the same read after transport health is restored"
    elif failure_family:
        category = failure_family.lower()
        recovery_action = "resolve the classified provider boundary and resume the same task"
    else:
        category = "provider_failure"
        recovery_action = "inspect the bounded provider failure receipt"
    provider_call = {
        "method": str(getattr(exc, "provider_method", "target_discovery") or "target_discovery"),
        "status": "failed",
        "effect": "read",
        "failure_category": category,
        "http_status": status,
        "response_received": exc.response_received,
        "failure_family": failure_family or None,
        "transport_category": transport_category or None,
    }
    return {
        "status": "blocked",
        "reason": f"live target discovery provider read failed: {category}",
        "missing_facts": list(missing_facts),
        "question": None,
        "recovery_action": recovery_action,
        "provider_calls": [provider_call],
    }


def _retry_blocked_discovery(
    journal: ProjectJournal,
    contract: dict[str, Any],
    state,
    *,
    before: int,
    recovery_source: str = "BLOCKED_DISCOVERY",
) -> tuple[Any, dict[str, Any] | None]:
    target_url = str(
        (((contract.get("browser_policy") or {}).get("target") or {}).get("canonical_url")) or ""
    )
    try:
        discovery = TargetDiscoveryService(max_objects=50).discover(
            contract,
            request_text="",
            target_url=target_url,
        )
    except DataLensApiError as exc:
        discovery = _provider_discovery_failure(exc, missing_facts=[])
    except Exception as exc:  # noqa: BLE001
        discovery = {
            "status": "blocked",
            "reason": f"live target discovery failed: {exc.__class__.__name__}",
            "missing_facts": [],
            "question": None,
        }
    if discovery.get("status") != "success":
        receipt = journal.write_receipt(
            f"target-discovery-retry-blocked-{canonical_hash(discovery)[:16]}",
            discovery,
        )
        return state, _block_task(
            journal,
            contract,
            before=before,
            code="BLOCKED_DISCOVERY",
            reason=str(discovery.get("reason") or "server-owned target discovery is incomplete"),
            question=discovery.get("question"),
            missing_facts=discovery.get("missing_facts") or [],
            receipt_uri=receipt,
            transition="TASK_DISCOVERY_RETRY_REQUIRED",
            issues=[],
            retryable=bool(discovery.get("recovery_action")),
        )
    reference = contract.get("reference") or {}
    reference_locator = str(reference.get("locator") or "")
    portfolio_root = ""
    if str(reference.get("kind") or "") == "portfolio_object" and reference_locator:
        portfolio_root = str(Path(reference_locator).resolve().parent)
    style = _bind_style_with_reference_discovery(
        contract,
        discovery=discovery,
        context={"portfolio_root": portfolio_root},
    )
    if style.get("status") != "success":
        receipt = journal.write_receipt(
            f"style-binding-retry-blocked-{canonical_hash(style)[:16]}",
            style,
        )
        return state, _block_task(
            journal,
            contract,
            before=before,
            code="BLOCKED_STYLE_BINDING",
            reason=str(style.get("reason") or "exact style binding is unavailable"),
            question=None,
            missing_facts=["reference_binding", "style_binding"],
            receipt_uri=receipt,
            transition="TASK_STYLE_BINDING_RETRY_REQUIRED",
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
            "recovered_from": recovery_source,
        },
    )
    with journal.locked(owner="task-discovery-retry"):
        current, _ = journal.replay()
        recovered = journal.append_transition(
            current,
            transition="TASK_DISCOVERY_RETRY_SUCCEEDED",
            input_value={"prior_blocker": recovery_source},
            receipt_uri=journal.receipt_uri("discovery.json"),
            status="success",
            idempotency_key=canonical_hash(
                {
                    "task_id": journal.task_id,
                    "transition": "TASK_DISCOVERY_RETRY_SUCCEEDED",
                    "target_binding_hash": discovery["target_binding"].get("binding_hash"),
                }
            ),
            next_state="RESOLVED",
            next_transition="RESOLVED -> BASELINE_READ",
        )
    return recovered, None


def _live_graph_projection(graph: dict[str, Any], *, task_id: str) -> dict[str, Any]:
    nodes = list(graph.get("nodes") or [])
    object_index = compact_object_index(graph, max_objects=50)
    return {
        "ok": True,
        "task_id": task_id,
        "graph_kind": "live_target_graph",
        "graph_hash": graph.get("graph_hash"),
        "node_count": len(nodes),
        "edge_count": len(graph.get("edges") or []),
        "nodes": object_index,
        "object_index": object_index,
        "limitations": graph.get("limitations") or [],
        "bounded": True,
        "resource_uri": task_resource_uri(task_id, "target-graph") if task_id else "datalens://inspect/target-graph",
    }


def _semantic_action_gate(journal: ProjectJournal, contract: dict[str, Any]) -> dict[str, Any]:
    if str(contract.get("operation_kind") or "") != "mutate":
        return {}
    if str(contract.get("mode") or "") not in {"create", "update", "redesign"}:
        return {}
    if _contract_semantic_changes(contract):
        return {}
    create_bundle = read_json(journal.root / "inputs" / "create-bundle.json", {}) or {}
    if str(contract.get("mode") or "") == "create" and create_bundle.get("bundle_hash"):
        return {}
    graph = read_json(journal.target_graph_path, {}) or {}
    if not graph.get("nodes"):
        return {}
    style = read_json(journal.style_binding_path, {}) or {}
    outcome = SemanticChangePlanner().plan(
        contract,
        target_graph=graph,
        baselines={},
        effective_visual_contract=dict(style.get("effective_visual_contract") or {}),
    )
    if outcome.get("status") != "needs_semantic_actions":
        return {}
    return {
        **outcome,
        "route": str(style.get("technology") or contract.get("route") or ""),
        "target_binding_hash": str((read_json(journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
        "style_binding_hash": str(style.get("binding_hash") or ""),
        "resource_uri": task_resource_uri(journal.task_id),
    }


def _project_semantic_action_gate(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    state: Any,
    before: int,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    result = project_task_summary(
        contract=contract,
        state=state,
        events_path=journal.events_path,
        resource_uri=task_resource_uri(journal.task_id),
        performed_after=before,
        **_projection_bindings(journal),
    )
    if result.get("blocked_by") is None:
        result.pop("blocked_by", None)
    result.update(outcome)
    _attach_object_index(result, journal)
    result.update(_contract_revision_projection(contract))
    return result


def _contract_semantic_changes(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in contract.get("acceptance") or []:
        if not isinstance(item, dict) or item.get("kind") != "semantic_change":
            continue
        try:
            value = json.loads(str(item.get("statement") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _projection_bindings(journal: ProjectJournal) -> dict[str, dict[str, Any]]:
    return {
        "target_binding": read_json(journal.target_binding_path, {}) or {},
        "style_binding": read_json(journal.style_binding_path, {}) or {},
    }


def _attach_object_index(result: dict[str, Any], journal: ProjectJournal) -> None:
    graph = read_json(journal.target_graph_path, {}) or {}
    if not graph.get("nodes"):
        return
    result["object_index"] = compact_object_index(graph, max_objects=50)
    result["object_index_resource_uri"] = task_resource_uri(journal.task_id, "target-graph")


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
