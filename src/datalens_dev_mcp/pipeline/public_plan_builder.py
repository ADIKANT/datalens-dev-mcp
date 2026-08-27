from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.dataset_context_profile import (
    derive_dataset_plan_context,
    validate_dataset_context_profile,
)
from datalens_dev_mcp.pipeline.create_manifest import (
    create_safe_apply_template,
    validate_create_bundle,
)
from datalens_dev_mcp.pipeline.object_action_mapper import map_materialized_action, semantic_fresh_read_spec
from datalens_dev_mcp.pipeline.plan_binding import (
    build_dataset_context_binding,
    build_plan_binding,
    validate_binding,
)
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.validators.redaction import sanitize_value


class PublicPlanBuilder:
    def __init__(self, journal: ProjectJournal, contract: dict[str, Any]) -> None:
        self.journal = journal
        self.contract = contract

    def build(
        self,
        *,
        semantic_result: dict[str, Any],
        context_profile: dict[str, Any],
    ) -> dict[str, Any]:
        plan_root = self.journal.root / "plans"
        context_profile = sanitize_value(context_profile)
        write_json(self.journal.root / "data" / "context-profile.json", context_profile)
        context_decisions = derive_dataset_plan_context(context_profile, self.contract)
        if not context_decisions["ok"]:
            raise ValueError("dataset context cannot satisfy semantic plan: " + "; ".join(context_decisions["issues"]))
        patch_plan = sanitize_value(dict(semantic_result["semantic_patch_plan"]))
        materialized = {
            object_id: sanitize_value(payload)
            for object_id, payload in dict(semantic_result["materialized_payloads"]).items()
        }
        write_json(plan_root / "semantic-patch-plan.json", patch_plan)
        materialized_refs: list[dict[str, str]] = []
        for object_id, payload in sorted(materialized.items()):
            digest = portable_artifact_hash(payload, project_root=self.journal.project_root)
            relative = Path("plans") / "materialized-payloads" / f"payload-{digest[:20]}.json"
            write_json(self.journal.root / relative, payload)
            materialized_refs.append(
                {"object_id_hash": canonical_hash(object_id), "artifact_uri": relative.as_posix(), "sha256": digest}
            )
        materialized_refs.sort(key=lambda item: item["artifact_uri"])
        target_graph = read_json(self.journal.target_graph_path, {}) or {}
        nodes = {
            str(item.get("object_id") or ""): item
            for item in target_graph.get("nodes") or []
            if isinstance(item, dict)
        }
        target = self.contract.get("target") or {}
        actions = []
        semantic_fresh_targets = dict(semantic_result.get("fresh_targets") or {})
        semantic_ids = sorted(
            {
                str(object_id)
                for planned_target in patch_plan.get("targets") or []
                for object_id in [
                    planned_target.get("object_id"),
                    *(planned_target.get("dependencies") or []),
                ]
                if str(object_id or "")
            }
        )
        semantic_fresh_reads = {
            semantic_id: semantic_fresh_read_spec(
                object_id=semantic_id,
                object_type=str(
                    (semantic_fresh_targets.get(semantic_id) or {}).get("object_type")
                    or (nodes.get(semantic_id) or {}).get("object_type")
                    or ""
                ),
                workbook_id=str(target.get("workbook_id") or ""),
            )
            for semantic_id in semantic_ids
        }
        for planned_target in patch_plan.get("targets") or []:
            object_id = str(planned_target.get("object_id") or "")
            node = nodes.get(object_id) or {}
            action = map_materialized_action(
                object_id=object_id,
                object_type=str(planned_target.get("object_type") or node.get("object_type") or ""),
                workbook_id=str(target.get("workbook_id") or ""),
                saved_revision=str(planned_target.get("saved_revision") or ""),
                materialized_payload=materialized[object_id],
                baseline_payload=dict((semantic_fresh_targets.get(object_id) or {}).get("payload") or {}),
                semantic_patch_plan=patch_plan,
            )
            action["semantic_fresh_reads"] = semantic_fresh_reads
            actions.append(action)
        execution_auth = read_json(self.journal.execution_authorization_path, {}) or {}
        safe_apply = sanitize_value(create_safe_apply_plan(
            project_root=str(self.journal.project_root),
            actions=actions,
            approved=True,
            approval_note="authorized by immutable public task contract",
            user_request_text=_delivery_intent_text(self.contract),
            task_contract_hash=str(self.contract.get("contract_hash") or ""),
        ))
        write_json(plan_root / "safe-apply-plan.json", safe_apply)
        context_binding = build_dataset_context_binding(context_profile)
        write_json(plan_root / "dataset-context-binding.json", context_binding)
        data_proof_plan = read_json(plan_root / "data-proof-plan.json", {}) or {}
        artifacts = {
            "dataset_context_profile": (
                "data/context-profile.json",
                portable_artifact_hash(context_profile, project_root=self.journal.project_root),
            ),
            "data_proof_plan": (
                "plans/data-proof-plan.json",
                portable_artifact_hash(data_proof_plan, project_root=self.journal.project_root),
            ),
            "dataset_context_binding": (
                "plans/dataset-context-binding.json",
                portable_artifact_hash(context_binding, project_root=self.journal.project_root),
            ),
            "semantic_patch_plan": (
                "plans/semantic-patch-plan.json",
                portable_artifact_hash(patch_plan, project_root=self.journal.project_root),
            ),
            "materialized_payloads": ("plans/materialized-payloads/", canonical_hash(materialized_refs)),
            "safe_apply_plan": ("plans/safe-apply-plan.json", portable_artifact_hash(safe_apply, project_root=self.journal.project_root)),
        }
        build_identity = read_json(self.journal.build_identity_path, {}) or {}
        target_binding = read_json(self.journal.target_binding_path, {}) or {}
        reference_binding = read_json(self.journal.reference_binding_path, {}) or {}
        style_binding = read_json(self.journal.style_binding_path, {}) or {}
        binding = build_plan_binding(
            contract_hash=str(self.contract.get("contract_hash") or ""),
            execution_authorization_hash=str(execution_auth.get("authorization_hash") or ""),
            build_identity_hash=str(build_identity.get("identity_hash") or ""),
            target_binding_hash=str(target_binding.get("binding_hash") or ""),
            reference_binding_hash=str(reference_binding.get("binding_hash") or ""),
            style_binding_hash=str(style_binding.get("binding_hash") or ""),
            dataset_context_binding_hash=str(context_binding.get("binding_hash") or ""),
            semantic_patch_plan_hash=str(patch_plan.get("plan_hash") or ""),
            safe_apply_plan_hash=artifacts["safe_apply_plan"][1],
        )
        write_json(plan_root / "plan-binding.json", binding)
        artifacts["plan_binding"] = (
            "plans/plan-binding.json",
            portable_artifact_hash(binding, project_root=self.journal.project_root),
        )
        payload = {
            "schema_id": "datalens_public_task_plan",
            "plan_version": 1,
            "task_id": self.journal.task_id,
            "contract_hash": self.contract.get("contract_hash"),
            "route": str(style_binding.get("technology") or target_binding.get("technology") or self.contract.get("route") or ""),
            "delivery": self.contract.get("delivery") or {},
            "scope": self.contract.get("scope") or {},
            "acceptance": self.contract.get("acceptance") or [],
            "dataset_context_profile_hash": context_profile.get("profile_hash"),
            "query_set_hash": context_profile.get("query_set_hash"),
            "dataset_schema_hash": context_profile.get("schema_hash"),
            "context_observed_at": context_profile.get("observed_at"),
            "context_limitations": (context_profile.get("sample_scope") or {}).get("limitations") or [],
            "data_context_decisions": context_decisions,
            "plan_binding_hash": binding["binding_hash"],
            "semantic_patch_plan_hash": patch_plan["plan_hash"],
            "style_binding_hash": style_binding.get("binding_hash"),
            "safe_apply_action_count": len(actions),
            "artifacts": [
                {"kind": kind, "artifact_uri": uri, "sha256": digest}
                for kind, (uri, digest) in sorted(artifacts.items())
            ],
            "destructive_token_required": bool((self.contract.get("delivery") or {}).get("destructive")),
        }
        payload = sanitize_value(payload)
        # This is a policy flag, not a credential. The generic redactor treats
        # every key containing "token" as sensitive, so restore its boolean
        # representation after sanitizing the rest of the public artifact.
        payload["destructive_token_required"] = bool((self.contract.get("delivery") or {}).get("destructive"))
        payload["plan_hash"] = public_plan_hash(payload)
        write_json(plan_root / "plan.json", payload)
        return payload

    def build_create(self, *, create_bundle: dict[str, Any]) -> dict[str, Any]:
        issues = validate_create_bundle(create_bundle)
        if issues:
            raise ValueError("create bundle is invalid: " + "; ".join(issues))
        plan_root = self.journal.root / "plans"
        baseline_uri = self.journal.discovery_path.relative_to(self.journal.root).as_posix()
        safe_apply = create_safe_apply_template(
            create_bundle,
            project_root=str(self.journal.project_root),
            task_contract_hash=str(self.contract.get("contract_hash") or ""),
            baseline_artifact=baseline_uri,
        )
        write_json(plan_root / "safe-apply-plan.json", safe_apply)
        execution_auth = read_json(self.journal.execution_authorization_path, {}) or {}
        build_identity = read_json(self.journal.build_identity_path, {}) or {}
        target_binding = read_json(self.journal.target_binding_path, {}) or {}
        reference_binding = read_json(self.journal.reference_binding_path, {}) or {}
        style_binding = read_json(self.journal.style_binding_path, {}) or {}
        safe_apply_hash = portable_artifact_hash(safe_apply, project_root=self.journal.project_root)
        binding = build_plan_binding(
            contract_hash=str(self.contract.get("contract_hash") or ""),
            execution_authorization_hash=str(execution_auth.get("authorization_hash") or ""),
            build_identity_hash=str(build_identity.get("identity_hash") or ""),
            target_binding_hash=str(target_binding.get("binding_hash") or ""),
            reference_binding_hash=str(reference_binding.get("binding_hash") or ""),
            style_binding_hash=str(style_binding.get("binding_hash") or ""),
            create_bundle_hash=str(create_bundle.get("bundle_hash") or ""),
            safe_apply_plan_hash=safe_apply_hash,
        )
        write_json(plan_root / "plan-binding.json", binding)
        artifacts = {
            "create_bundle": (
                "inputs/create-bundle.json",
                portable_artifact_hash(create_bundle, project_root=self.journal.project_root),
            ),
            "safe_apply_plan": ("plans/safe-apply-plan.json", safe_apply_hash),
            "plan_binding": (
                "plans/plan-binding.json",
                portable_artifact_hash(binding, project_root=self.journal.project_root),
            ),
        }
        payload = sanitize_value(
            {
                "schema_id": "datalens_public_task_plan",
                "plan_version": 1,
                "plan_kind": "create_manifest",
                "task_id": self.journal.task_id,
                "contract_hash": self.contract.get("contract_hash"),
                "route": str(self.contract.get("route") or ""),
                "delivery": self.contract.get("delivery") or {},
                "scope": self.contract.get("scope") or {},
                "acceptance": self.contract.get("acceptance") or [],
                "create_bundle_hash": create_bundle.get("bundle_hash"),
                "create_manifest_hash": create_bundle.get("manifest_hash"),
                "plan_binding_hash": binding.get("binding_hash"),
                "style_binding_hash": style_binding.get("binding_hash"),
                "safe_apply_action_count": len(safe_apply.get("actions") or []),
                "artifacts": [
                    {"kind": kind, "artifact_uri": uri, "sha256": digest}
                    for kind, (uri, digest) in sorted(artifacts.items())
                ],
                "destructive_token_required": False,
            }
        )
        payload["destructive_token_required"] = False
        payload["plan_hash"] = public_plan_hash(payload)
        write_json(plan_root / "plan.json", payload)
        return payload

    def validate_current(self) -> tuple[str, ...]:
        plan = read_json(self.journal.root / "plans" / "plan.json", {}) or {}
        issues: list[str] = []
        if plan.get("schema_id") != "datalens_public_task_plan":
            issues.append("public task plan is missing")
            return tuple(issues)
        if plan.get("plan_hash") != public_plan_hash(plan):
            issues.append("public task plan hash mismatch")
        for item in plan.get("artifacts") or []:
            uri = str(item.get("artifact_uri") or "")
            if not uri or uri.endswith("/"):
                if item.get("kind") == "materialized_payloads":
                    refs = [
                        {
                            "object_id_hash": canonical_hash(_materialized_object_id(path)),
                            "artifact_uri": path.relative_to(self.journal.root).as_posix(),
                            "sha256": portable_artifact_hash(read_json(path, {}) or {}, project_root=self.journal.project_root),
                        }
                        for path in sorted((self.journal.root / uri).glob("*.json"))
                    ]
                    actual = canonical_hash(refs)
                else:
                    actual = ""
            else:
                path = (self.journal.root / uri).resolve()
                if self.journal.root not in path.parents or not path.is_file():
                    actual = ""
                else:
                    actual = portable_artifact_hash(read_json(path, {}) or {}, project_root=self.journal.project_root)
            if actual != item.get("sha256"):
                issues.append(f"plan artifact hash mismatch: {item.get('kind')}")
        if plan.get("plan_kind") == "create_manifest":
            return tuple([*issues, *self._validate_create_current(plan)])
        binding = read_json(self.journal.root / "plans" / "plan-binding.json", {}) or {}
        issues.extend(validate_binding(binding, schema_id="datalens_public_plan_binding"))
        context_binding = read_json(self.journal.root / "plans" / "dataset-context-binding.json", {}) or {}
        context_profile = read_json(self.journal.root / "data" / "context-profile.json", {}) or {}
        issues.extend(validate_dataset_context_profile(context_profile))
        expected_context_binding = build_dataset_context_binding(context_profile)
        issues.extend(validate_binding(context_binding, schema_id="dataset_context_binding"))
        if context_binding != expected_context_binding:
            issues.append("dataset context binding is stale")
        safe_apply = read_json(self.journal.root / "plans" / "safe-apply-plan.json", {}) or {}
        if plan.get("plan_binding_hash") != binding.get("binding_hash"):
            issues.append("public plan does not match its plan binding")
        if plan.get("contract_hash") != self.contract.get("contract_hash"):
            issues.append("public plan contract hash is stale")
        if plan.get("style_binding_hash") != binding.get("style_binding_hash"):
            issues.append("public plan style binding hash is stale")
        if plan.get("semantic_patch_plan_hash") != binding.get("semantic_patch_plan_hash"):
            issues.append("public plan semantic patch hash is stale")
        if plan.get("dataset_context_profile_hash") != context_binding.get("dataset_context_profile_hash"):
            issues.append("public plan dataset context profile hash is stale")
        if plan.get("query_set_hash") != context_binding.get("query_set_hash"):
            issues.append("public plan dataset query set hash is stale")
        if plan.get("dataset_schema_hash") != context_binding.get("dataset_schema_hash"):
            issues.append("public plan dataset schema hash is stale")
        if plan.get("context_observed_at") != context_binding.get("context_observed_at"):
            issues.append("public plan context observation timestamp is stale")
        if sorted(plan.get("context_limitations") or []) != context_binding.get("context_limitations"):
            issues.append("public plan context limitations are stale")
        if plan.get("data_context_decisions") != derive_dataset_plan_context(context_profile, self.contract):
            issues.append("public plan data context decisions are stale")
        if int(plan.get("safe_apply_action_count") or 0) != len(safe_apply.get("actions") or []):
            issues.append("public plan safe apply action count mismatch")
        target_binding = read_json(self.journal.target_binding_path, {}) or {}
        style_binding = read_json(self.journal.style_binding_path, {}) or {}
        expected_route = str(
            style_binding.get("technology")
            or target_binding.get("technology")
            or self.contract.get("route")
            or ""
        )
        expected_contract_fields = {
            "task_id": self.journal.task_id,
            "route": expected_route,
            "delivery": self.contract.get("delivery") or {},
            "scope": self.contract.get("scope") or {},
            "acceptance": self.contract.get("acceptance") or [],
            "destructive_token_required": bool((self.contract.get("delivery") or {}).get("destructive")),
        }
        for key, expected in expected_contract_fields.items():
            if plan.get(key) != sanitize_value(expected):
                issues.append(f"public plan contract projection is stale: {key}")
        current = {
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "execution_authorization_hash": str(
                (read_json(self.journal.execution_authorization_path, {}) or {}).get("authorization_hash") or ""
            ),
            "build_identity_hash": str((read_json(self.journal.build_identity_path, {}) or {}).get("identity_hash") or ""),
            "target_binding_hash": str(target_binding.get("binding_hash") or ""),
            "reference_binding_hash": str((read_json(self.journal.reference_binding_path, {}) or {}).get("binding_hash") or ""),
            "style_binding_hash": str(style_binding.get("binding_hash") or ""),
            "dataset_context_binding_hash": str(context_binding.get("binding_hash") or ""),
            "semantic_patch_plan_hash": str(
                (read_json(self.journal.root / "plans" / "semantic-patch-plan.json", {}) or {}).get("plan_hash")
                or ""
            ),
            "safe_apply_plan_hash": portable_artifact_hash(
                safe_apply,
                project_root=self.journal.project_root,
            ),
        }
        for key, expected in current.items():
            if binding.get(key) != expected:
                issues.append(f"plan binding is stale: {key}")
        return tuple(issues)

    def _validate_create_current(self, plan: dict[str, Any]) -> tuple[str, ...]:
        issues: list[str] = []
        bundle = read_json(self.journal.root / "inputs" / "create-bundle.json", {}) or {}
        safe_apply = read_json(self.journal.root / "plans" / "safe-apply-plan.json", {}) or {}
        binding = read_json(self.journal.root / "plans" / "plan-binding.json", {}) or {}
        issues.extend(validate_create_bundle(bundle))
        issues.extend(validate_binding(binding, schema_id="datalens_public_plan_binding"))
        if plan.get("contract_hash") != self.contract.get("contract_hash"):
            issues.append("public create plan contract hash is stale")
        if plan.get("create_bundle_hash") != bundle.get("bundle_hash"):
            issues.append("public create plan bundle hash is stale")
        if plan.get("create_manifest_hash") != bundle.get("manifest_hash"):
            issues.append("public create plan manifest hash is stale")
        if plan.get("plan_binding_hash") != binding.get("binding_hash"):
            issues.append("public create plan binding is stale")
        if int(plan.get("safe_apply_action_count") or 0) != len(safe_apply.get("actions") or []):
            issues.append("public create plan safe apply action count mismatch")
        build_identity = read_json(self.journal.build_identity_path, {}) or {}
        target_binding = read_json(self.journal.target_binding_path, {}) or {}
        reference_binding = read_json(self.journal.reference_binding_path, {}) or {}
        style_binding = read_json(self.journal.style_binding_path, {}) or {}
        execution_auth = read_json(self.journal.execution_authorization_path, {}) or {}
        expected = {
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "execution_authorization_hash": str(execution_auth.get("authorization_hash") or ""),
            "build_identity_hash": str(build_identity.get("identity_hash") or ""),
            "target_binding_hash": str(target_binding.get("binding_hash") or ""),
            "reference_binding_hash": str(reference_binding.get("binding_hash") or ""),
            "style_binding_hash": str(style_binding.get("binding_hash") or ""),
            "create_bundle_hash": str(bundle.get("bundle_hash") or ""),
            "safe_apply_plan_hash": portable_artifact_hash(
                safe_apply,
                project_root=self.journal.project_root,
            ),
        }
        for key, value in expected.items():
            if binding.get(key) != value:
                issues.append(f"public create plan binding is stale: {key}")
        return tuple(issues)


def public_plan_hash(plan: dict[str, Any]) -> str:
    material = dict(plan)
    material.pop("plan_hash", None)
    return canonical_hash(material)


def portable_artifact_hash(value: Any, *, project_root: Path) -> str:
    return canonical_hash(_portable(value, project_root=project_root.resolve()))


def _portable(value: Any, *, project_root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _portable(item, project_root=project_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable(item, project_root=project_root) for item in value]
    if isinstance(value, str) and value.startswith("/"):
        path = Path(value).resolve()
        if path == project_root or project_root in path.parents:
            return path.relative_to(project_root).as_posix() or "."
        return "<external-absolute-path-excluded>"
    return value


def _delivery_intent_text(contract: dict[str, Any]) -> str:
    delivery = contract.get("delivery") or {}
    return "implement update and publish" if delivery.get("publish") else "implement update save only"


def _materialized_object_id(path: Path) -> str:
    payload = read_json(path, {}) or {}
    return str(payload.get("entryId") or (payload.get("entry") or {}).get("entryId") or path.stem)
