from __future__ import annotations

from collections.abc import Callable
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.effective_visual_contract import resolve_effective_visual_contract
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.public_plan_builder import PublicPlanBuilder
from datalens_dev_mcp.pipeline.semantic_change_planner import SemanticChangePlanner
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt


def task_planning_stage_services(
    journal: ProjectJournal,
    contract: dict[str, Any],
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    context_service = TaskDatasetContextService(journal, contract)
    builder = PublicPlanBuilder(journal, contract)

    def plan_data_proof(context: dict[str, Any]) -> dict[str, Any]:
        if str(contract.get("task_kind") or "") == "cleanup_run_owned_objects":
            ownership = read_json(journal.root / "inputs" / "cleanup-ownership.json", {}) or {}
            return _receipt(
                context,
                status="success",
                output_hashes={"ownership": str(ownership.get("ownership_hash") or "")},
                observed=[f"run-owned cleanup object count={len(ownership.get('objects') or [])}"],
                reason="cleanup is bound to an exact ownership receipt; data diagnostics are not applicable",
            )
        if str(contract.get("mode") or "") == "create":
            bundle = read_json(journal.root / "inputs" / "create-bundle.json", {}) or {}
            if not bundle.get("bundle_hash"):
                return _receipt(
                    context,
                    status="blocked",
                    missing=["typed_create_manifest"],
                    reason="create task requires a persisted typed create manifest",
                )
            return _receipt(
                context,
                status="success",
                output_hashes={"create_bundle": str(bundle.get("bundle_hash") or "")},
                observed=[f"create object count={len(bundle.get('objects') or [])}"],
                reason="create dependencies are declared and data probes are deferred to resolved stages",
            )
        if str(contract.get("operation_kind") or "") == "verify_existing_effect":
            required_reads = set((contract.get("verification") or {}).get("required_live_reads") or [])
            if "data_assertions" in required_reads:
                return context_service.stage_handler(context)
            return _receipt(
                context,
                status="success",
                output_hashes={
                    "target_binding": str((read_json(journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
                    "target_graph": str((read_json(journal.target_graph_path, {}) or {}).get("graph_hash") or ""),
                },
                observed=["verification data probe not applicable"],
                reason="existing-effect verification uses fresh object/revision/relation reads",
            )
        diagnostics = (
            contract.get("data_diagnostics")
            if isinstance(contract.get("data_diagnostics"), dict)
            else {}
        )
        if diagnostics.get("required") is not True:
            target = read_json(journal.target_binding_path, {}) or {}
            graph = read_json(journal.target_graph_path, {}) or {}
            not_applicable = context_service.persist_not_applicable(
                reason="typed data/change impact decision does not require diagnostics"
            )
            profile = dict(not_applicable.get("profile") or {})
            query_plan = dict(not_applicable.get("query_plan") or {})
            return _receipt(
                context,
                status="success",
                output_hashes={
                    "target_binding": str(target.get("binding_hash") or ""),
                    "target_graph": str(graph.get("graph_hash") or ""),
                    "dataset_context_profile": str(profile.get("profile_hash") or ""),
                    "dataset_query_set": str(query_plan.get("query_set_hash") or ""),
                    "dataset_schema": str(profile.get("schema_hash") or ""),
                },
                observed=["data diagnostics required=False", "dataset probe not applicable"],
                reason="data proof is not required by the typed data/change impact decision",
            )
        return context_service.stage_handler(context)

    def plan_semantic_change(context: dict[str, Any]) -> dict[str, Any]:
        if str(contract.get("task_kind") or "") == "cleanup_run_owned_objects":
            ownership = read_json(journal.root / "inputs" / "cleanup-ownership.json", {}) or {}
            try:
                plan = builder.build_run_owned_cleanup(ownership=ownership)
            except ValueError as exc:
                return _receipt(context, status="blocked", missing=["run_owned_cleanup_plan"], reason=str(exc))
            return _receipt(
                context,
                status="success",
                output_hashes={"public_plan": str(plan.get("plan_hash") or "")},
                observed=[f"cleanup object count={plan.get('safe_apply_action_count', 0)}"],
                reason="exact run-owned objects are bound to official delete and absence-readback routes",
            )
        if str(contract.get("mode") or "") == "create":
            bundle = read_json(journal.root / "inputs" / "create-bundle.json", {}) or {}
            try:
                plan = builder.build_create(create_bundle=bundle)
            except ValueError as exc:
                return _receipt(
                    context,
                    status="blocked",
                    missing=["create_object_materialization"],
                    reason=str(exc),
                )
            return _receipt(
                context,
                status="success",
                output_hashes={
                    "create_bundle": str(bundle.get("bundle_hash") or ""),
                    "public_plan": str(plan.get("plan_hash") or ""),
                },
                observed=[f"safe apply action count={plan.get('safe_apply_action_count', 0)}"],
                reason="typed create manifest is materialized as an immutable Safe Apply template",
            )
        operation_kind = str(contract.get("operation_kind") or "")
        if operation_kind in {"inspect", "verify_existing_effect"}:
            plan = (
                builder.build_read_only_review()
                if operation_kind == "inspect"
                else builder.build_verification()
            )
            return _receipt(
                context,
                status="success",
                output_hashes={"public_plan": str(plan.get("plan_hash") or "")},
                observed=["safe apply action count=0", f"operation kind={operation_kind}"],
                reason=(
                    "zero-mutation read-only review plan is materialized"
                    if operation_kind == "inspect"
                    else "zero-mutation existing-effect verification plan is materialized"
                ),
            )
        graph = read_json(journal.target_graph_path, {}) or {}
        style_binding = read_json(journal.style_binding_path, {}) or {}
        baselines = {
            path.name: read_json(path, {}) or {}
            for path in sorted((journal.root / "snapshots").glob("baseline-*.json"))
        }
        effective_result = resolve_effective_visual_contract(
            contract,
            target_graph=graph,
            baselines=baselines,
            style_binding=style_binding,
            decision_context=dict(style_binding.get("decision_context") or {}),
        )
        if effective_result.get("status") != "success":
            return _receipt(
                context,
                status="blocked",
                missing=["effective_visual_contract"],
                reason=str(effective_result.get("reason") or "effective visual contract is invalid"),
            )
        effective_visual_contract = {
            key: value for key, value in effective_result.items() if key != "status"
        }
        semantic = SemanticChangePlanner().plan(
            contract,
            target_graph=graph,
            baselines=baselines,
            binding_hashes={
                "target_binding_hash": str((read_json(journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
                "style_binding_hash": str(style_binding.get("binding_hash") or ""),
                "effective_visual_contract_hash": str(effective_visual_contract.get("contract_hash") or ""),
                "dataset_context_profile_hash": str((read_json(context_service.profile_path, {}) or {}).get("profile_hash") or ""),
            },
            effective_visual_contract=effective_visual_contract,
        )
        if not semantic.get("ok"):
            return _receipt(
                context,
                status="blocked",
                missing=[str(semantic.get("status") or "semantic_plan")],
                reason=str(semantic.get("status") or "semantic planning blocked") + ": " + "; ".join(semantic.get("issues") or []),
            )
        if semantic.get("status") == "already_satisfied_no_write":
            plan = builder.build_already_satisfied(semantic_result=semantic)
            return _receipt(
                context,
                status="success",
                output_hashes={"public_plan": str(plan.get("plan_hash") or "")},
                observed=[
                    f"matched semantic assertion count={len(semantic.get('matched_assertions') or [])}",
                    "safe apply action count=0",
                ],
                reason="fresh live state already satisfies every typed semantic action",
            )
        profile = read_json(context_service.profile_path, {}) or {}
        plan = builder.build(semantic_result=semantic, context_profile=profile)
        return _receipt(
            context,
            status="success",
            output_hashes={
                "semantic_patch_plan": str(semantic["semantic_patch_plan"].get("plan_hash") or ""),
                "public_plan": str(plan.get("plan_hash") or ""),
                "style_binding": str(plan.get("style_binding_hash") or ""),
            },
            observed=[
                f"semantic target count={len((semantic.get('semantic_patch_plan') or {}).get('targets') or [])}",
                f"safe apply action count={plan.get('safe_apply_action_count', 0)}",
            ],
            reason="semantic patch and safe apply actions are materialized and preflighted",
        )

    def validate_plan(context: dict[str, Any]) -> dict[str, Any]:
        issues = list(builder.validate_current())
        plan = read_json(journal.root / "plans" / "plan.json", {}) or {}
        read_only = str(contract.get("operation_kind") or "") in {"inspect", "verify_existing_effect"}
        already_satisfied = plan.get("plan_kind") == "already_satisfied_no_write"
        if read_only and int(plan.get("safe_apply_action_count") or 0) != 0:
            issues.append("read-only public plan must have zero actions")
        elif not read_only and not already_satisfied and int(plan.get("safe_apply_action_count") or 0) < 1:
            issues.append("public plan action set is empty")
        return _receipt(
            context,
            status="blocked" if issues else "success",
            missing=["immutable_public_plan"] if issues else [],
            output_hashes={"public_plan": str(plan.get("plan_hash") or "")},
            reason="; ".join(issues) if issues else "immutable public plan and every bound artifact are valid",
        )

    def _receipt(
        context: dict[str, Any],
        *,
        status: str,
        reason: str,
        missing: list[str] | None = None,
        output_hashes: dict[str, str] | None = None,
        observed: list[str] | None = None,
    ) -> dict[str, Any]:
        return build_stage_receipt(
            task_id=journal.task_id,
            contract_hash=str(contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status=status,
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            output_hashes=output_hashes or {},
            hard_requirements=["bounded_dataset_context", "semantic_patch_plan", "full_batch_preflight", "immutable_public_plan"],
            missing_requirements=missing or [],
            reason=reason,
            observed_facts=observed or [],
        )

    return {
        "plan_data_proof": plan_data_proof,
        "plan_semantic_change": plan_semantic_change,
        "validate_plan": validate_plan,
    }
