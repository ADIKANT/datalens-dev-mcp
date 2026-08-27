from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.delivery_stage_receipts import (
    build_delivery_receipt,
    validate_delivery_receipt,
)
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.safe_apply import (
    build_safe_apply_readback_evidence,
    create_publish_safe_apply_plan,
    create_safe_apply_plan,
    execute_safe_apply,
)
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.pipeline.write_reconciliation import reconcile_objects
from datalens_dev_mcp.validators.redaction import sanitize_value


class DeliveryTransactionService:
    def __init__(
        self,
        journal: ProjectJournal,
        contract: dict[str, Any],
        *,
        client: Any | None = None,
        executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.journal = journal
        self.contract = contract
        if client is None:
            from datalens_dev_mcp.api.client import DataLensApiClient
            from datalens_dev_mcp.config import DataLensConfig

            client = DataLensApiClient(DataLensConfig.from_env())
        self.client = client
        self.executor = executor or (lambda plan: execute_safe_apply(plan, client=self.client))

    def execute_save_stage(self, context: dict[str, Any]) -> dict[str, Any]:
        public_plan = read_json(self.journal.root / "plans" / "plan.json", {}) or {}
        safe_plan = read_json(self.journal.root / "plans" / "safe-apply-plan.json", {}) or {}
        plan_hash = str(public_plan.get("plan_hash") or "")
        if not plan_hash or not safe_plan.get("actions"):
            return self._blocked(context, "immutable save plan is missing", "save_plan")
        existing = self._existing_delivery_receipt(
            self.journal.save_stage_receipt_path,
            "datalens_save_stage_receipt",
        )
        if existing:
            if existing.get("plan_hash") != plan_hash:
                return self._blocked(context, "save receipt belongs to another plan", "save_receipt_binding")
            return self._stage_receipt(context, existing, proof_level="controlled_live_write")
        attempt_path = self.journal.delivery_root / "save-stage-attempt.json"
        if attempt_path.is_file():
            receipt = self._uncertain_write_receipt(
                schema_id="datalens_save_stage_receipt",
                phase="save",
                plan_hash=plan_hash,
                actions=list(safe_plan.get("actions") or []),
                reason="save attempt exists without a final receipt",
            )
            write_json(self.journal.save_stage_receipt_path, receipt)
            return self._stage_receipt(context, receipt, proof_level="controlled_live_write")
        execution_plan = _without_readback(safe_plan)
        write_json(
            attempt_path,
            _attempt_marker("save", plan_hash=plan_hash, execution_plan_hash=canonical_hash(execution_plan)),
        )
        try:
            result = self.executor(execution_plan)
        except Exception as exc:  # noqa: BLE001 - a dispatched write is conservatively uncertain.
            receipt = self._uncertain_write_receipt(
                schema_id="datalens_save_stage_receipt",
                phase="save",
                plan_hash=plan_hash,
                actions=list(safe_plan.get("actions") or []),
                reason=f"save executor raised {exc.__class__.__name__}",
            )
        else:
            receipt = self._write_result_receipt(
                schema_id="datalens_save_stage_receipt",
                phase="save",
                binding_name="plan_hash",
                binding_hash=plan_hash,
                actions=list(safe_plan.get("actions") or []),
                result=result,
            )
        write_json(self.journal.save_stage_receipt_path, receipt)
        return self._stage_receipt(context, receipt, proof_level="controlled_live_write")

    def read_saved_stage(self, context: dict[str, Any]) -> dict[str, Any]:
        save_receipt = self._existing_delivery_receipt(
            self.journal.save_stage_receipt_path,
            "datalens_save_stage_receipt",
        )
        if not save_receipt or save_receipt.get("status") != "success":
            return self._blocked(context, "journal state requires a successful save receipt", "save_receipt")
        existing = self._existing_delivery_receipt(
            self.journal.saved_readback_receipt_path,
            "datalens_saved_readback_receipt",
        )
        if existing:
            if existing.get("save_receipt_hash") != save_receipt.get("receipt_hash"):
                return self._blocked(context, "saved readback receipt is stale", "saved_readback_binding")
            if not self._saved_source_matches(existing):
                return self._blocked(context, "saved readback source artifact is missing or stale", "saved_readback_source")
            return self._stage_receipt(context, existing, proof_level="save_readback")
        safe_plan = read_json(self.journal.root / "plans" / "safe-apply-plan.json", {}) or {}
        receipt = self._readback_receipt(
            schema_id="datalens_saved_readback_receipt",
            branch="saved",
            binding_name="save_receipt_hash",
            binding_hash=str(save_receipt.get("receipt_hash") or ""),
            actions=list(safe_plan.get("actions") or []),
            require_publish_source=bool((self.contract.get("delivery") or {}).get("publish")),
        )
        write_json(self.journal.saved_readback_receipt_path, receipt)
        return self._stage_receipt(context, receipt, proof_level="save_readback")

    def execute_publish_from_saved_stage(self, context: dict[str, Any]) -> dict[str, Any]:
        saved_receipt = self._existing_delivery_receipt(
            self.journal.saved_readback_receipt_path,
            "datalens_saved_readback_receipt",
        )
        if not saved_receipt or saved_receipt.get("status") != "success":
            return self._blocked(context, "publish requires a verified saved readback", "saved_readback")
        if not self._saved_source_matches(saved_receipt):
            return self._blocked(context, "publish source artifact is missing or stale", "saved_readback_source")
        existing = self._existing_delivery_receipt(
            self.journal.publish_stage_receipt_path,
            "datalens_publish_stage_receipt",
        )
        if existing:
            if existing.get("saved_readback_hash") != saved_receipt.get("receipt_hash"):
                return self._blocked(context, "publish receipt is stale", "publish_receipt_binding")
            return self._stage_receipt(context, existing, proof_level="controlled_live_write")
        attempt_path = self.journal.delivery_root / "publish-stage-attempt.json"
        public_publish_plan_path = self.journal.root / "plans" / "publish-safe-apply-plan.json"
        persisted_plan = read_json(self.journal.publish_execution_plan_path, {}) or {}
        publish_plan, publish_plan_hash = _verified_publish_plan(
            persisted_plan,
            saved_readback_hash=str(saved_receipt.get("receipt_hash") or ""),
        )
        if not publish_plan:
            if attempt_path.is_file():
                return self._blocked(
                    context,
                    "publish attempt exists but its immutable publish plan is missing or invalid",
                    "publish_plan_recovery",
                )
            publish_plan = self._build_publish_plan(saved_receipt)
            if not publish_plan.get("ok"):
                return self._blocked(
                    context,
                    str((publish_plan.get("error") or {}).get("message") or "publish plan could not be generated"),
                    "publish_plan",
                )
            publish_plan_hash = canonical_hash(publish_plan)
            publish_plan["delivery_plan_hash"] = publish_plan_hash
            write_json(self.journal.publish_execution_plan_path, publish_plan)
            write_json(public_publish_plan_path, sanitize_value(publish_plan))
        if attempt_path.is_file():
            receipt = self._uncertain_write_receipt(
                schema_id="datalens_publish_stage_receipt",
                phase="publish",
                plan_hash=publish_plan_hash,
                actions=list(publish_plan.get("actions") or []),
                reason="publish attempt exists without a final receipt",
                binding_name="saved_readback_hash",
                binding_hash=str(saved_receipt.get("receipt_hash") or ""),
            )
            write_json(self.journal.publish_stage_receipt_path, receipt)
            return self._stage_receipt(context, receipt, proof_level="controlled_live_write")
        execution_plan = _without_readback(publish_plan)
        write_json(
            attempt_path,
            _attempt_marker("publish", plan_hash=publish_plan_hash, execution_plan_hash=canonical_hash(execution_plan)),
        )
        try:
            result = self.executor(execution_plan)
        except Exception as exc:  # noqa: BLE001 - a dispatched write is conservatively uncertain.
            receipt = self._uncertain_write_receipt(
                schema_id="datalens_publish_stage_receipt",
                phase="publish",
                plan_hash=publish_plan_hash,
                actions=list(publish_plan.get("actions") or []),
                reason=f"publish executor raised {exc.__class__.__name__}",
                binding_name="saved_readback_hash",
                binding_hash=str(saved_receipt.get("receipt_hash") or ""),
            )
        else:
            receipt = self._write_result_receipt(
                schema_id="datalens_publish_stage_receipt",
                phase="publish",
                binding_name="saved_readback_hash",
                binding_hash=str(saved_receipt.get("receipt_hash") or ""),
                actions=list(publish_plan.get("actions") or []),
                result=result,
                publish_plan_hash=publish_plan_hash,
            )
        write_json(self.journal.publish_stage_receipt_path, receipt)
        return self._stage_receipt(context, receipt, proof_level="controlled_live_write")

    def read_published_stage(self, context: dict[str, Any]) -> dict[str, Any]:
        publish_receipt = self._existing_delivery_receipt(
            self.journal.publish_stage_receipt_path,
            "datalens_publish_stage_receipt",
        )
        if not publish_receipt or publish_receipt.get("status") != "success":
            return self._blocked(context, "journal state requires a successful publish receipt", "publish_receipt")
        existing = self._existing_delivery_receipt(
            self.journal.published_readback_receipt_path,
            "datalens_published_readback_receipt",
        )
        if existing:
            if existing.get("publish_receipt_hash") != publish_receipt.get("receipt_hash"):
                return self._blocked(context, "published readback receipt is stale", "published_readback_binding")
            return self._stage_receipt(context, existing, proof_level="publish_readback")
        publish_plan = read_json(self.journal.publish_execution_plan_path, {}) or {}
        receipt = self._readback_receipt(
            schema_id="datalens_published_readback_receipt",
            branch="published",
            binding_name="publish_receipt_hash",
            binding_hash=str(publish_receipt.get("receipt_hash") or ""),
            actions=list(publish_plan.get("actions") or []),
            require_publish_source=False,
        )
        write_json(self.journal.published_readback_receipt_path, receipt)
        return self._stage_receipt(context, receipt, proof_level="publish_readback")

    def reconcile_ambiguous_write(self, context: dict[str, Any]) -> dict[str, Any]:
        phase = str(((context.get("state") or {}).get("reconciliation") or {}).get("phase") or "save")
        if phase == "publish":
            actions = list((read_json(self.journal.publish_execution_plan_path, {}) or {}).get("actions") or [])
            binding_receipt = self._existing_delivery_receipt(
                self.journal.publish_stage_receipt_path,
                "datalens_publish_stage_receipt",
            ) or {}
            schema_id = "datalens_published_readback_receipt"
            branch = "published"
            binding_name = "publish_receipt_hash"
            output_path = self.journal.published_readback_receipt_path
        else:
            actions = list((read_json(self.journal.root / "plans" / "safe-apply-plan.json", {}) or {}).get("actions") or [])
            binding_receipt = self._existing_delivery_receipt(
                self.journal.save_stage_receipt_path,
                "datalens_save_stage_receipt",
            ) or {}
            schema_id = "datalens_saved_readback_receipt"
            branch = "saved"
            binding_name = "save_receipt_hash"
            output_path = self.journal.saved_readback_receipt_path
        evidence_by_id: dict[str, dict[str, Any]] = {}

        def read_expected(expected: dict[str, Any]) -> dict[str, Any]:
            evidence = self._read_action(expected, branch=branch)
            evidence_by_id[str(expected.get("object_id") or _action_object_id(expected))] = evidence
            return evidence

        normalized_actions = []
        for action in actions:
            normalized = dict(action)
            normalized["object_id"] = _action_object_id(action)
            normalized_actions.append(normalized)
        reconciled = reconcile_objects(normalized_actions, read_object=read_expected)
        receipt = self._readback_receipt_from_evidence(
            schema_id=schema_id,
            branch=branch,
            binding_name=binding_name,
            binding_hash=str(binding_receipt.get("receipt_hash") or ""),
            actions=actions,
            evidence_by_id=evidence_by_id,
            reconciliation=True,
        )
        write_json(output_path, receipt)
        proof_level = "publish_readback" if branch == "published" else "save_readback"
        stage = self._stage_receipt(context, receipt, proof_level=proof_level)
        stage["reconciliation_status"] = reconciled["status"]
        stage["write_replayed"] = False
        return stage

    def _readback_receipt(
        self,
        *,
        schema_id: str,
        branch: str,
        binding_name: str,
        binding_hash: str,
        actions: list[dict[str, Any]],
        require_publish_source: bool,
    ) -> dict[str, Any]:
        evidence_by_id = {
            _action_object_id(action): self._read_action(action, branch=branch)
            for action in actions
        }
        return self._readback_receipt_from_evidence(
            schema_id=schema_id,
            branch=branch,
            binding_name=binding_name,
            binding_hash=binding_hash,
            actions=actions,
            evidence_by_id=evidence_by_id,
            require_publish_source=require_publish_source,
        )

    def _readback_receipt_from_evidence(
        self,
        *,
        schema_id: str,
        branch: str,
        binding_name: str,
        binding_hash: str,
        actions: list[dict[str, Any]],
        evidence_by_id: dict[str, dict[str, Any]],
        require_publish_source: bool = False,
        reconciliation: bool = False,
    ) -> dict[str, Any]:
        objects: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        for action in actions:
            object_id = _action_object_id(action)
            evidence = evidence_by_id.get(object_id) or {}
            entry = dict(evidence.get("entry") or {})
            complete = bool(
                evidence.get("content_equivalent")
                and evidence.get("revision")
                and isinstance(entry.get("data"), dict)
                and (not require_publish_source or evidence.get("saved_id"))
            )
            if complete:
                entries.append(entry)
            objects.append(
                {
                    "object_id": object_id,
                    "object_type": str(action.get("object_type") or ""),
                    "revision": str(evidence.get("revision") or ""),
                    "saved_id": str(evidence.get("saved_id") or ""),
                    "payload_hash": str(evidence.get("payload_hash") or ""),
                    "semantic_match": bool(evidence.get("content_equivalent")),
                    "complete": complete,
                    "diff_paths": list(evidence.get("diff_paths") or []),
                }
            )
        all_match = bool(objects) and all(item["complete"] for item in objects)
        values: dict[str, Any] = {
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            binding_name: binding_hash,
            "branch": branch,
            "objects": objects,
            "provider_calls": [
                {
                    "method": str(action.get("readback_method") or action.get("fresh_read_method") or ""),
                    "request_hash": canonical_hash(_read_payload(action, branch)),
                    "response_hash": str((evidence_by_id.get(_action_object_id(action)) or {}).get("payload_hash") or ""),
                    "status": "success",
                }
                for action in actions
            ],
            "all_objects_match": all_match,
            "reconciliation": reconciliation,
            "status": "success" if all_match else "mismatch",
        }
        if branch == "saved":
            source = {"branch": "saved", "entries": entries}
            source_path = self.journal.delivery_root / "private" / "saved-readback-source.json"
            # This artifact is deliberately private: publish must preserve the exact
            # verified saved payload, including unknown fields, rather than a projection.
            write_json(source_path, source)
            values["source_artifact_uri"] = source_path.relative_to(self.journal.root).as_posix()
            values["source_artifact_hash"] = canonical_hash(source)
        return build_delivery_receipt(schema_id, **values)

    def _read_action(self, action: dict[str, Any], *, branch: str) -> dict[str, Any]:
        method = str(action.get("readback_method") or action.get("fresh_read_method") or "")
        payload = _read_payload(action, branch)
        response = self._exclusive_read(method, payload)
        return build_safe_apply_readback_evidence(
            method=str(action.get("method") or ""),
            object_id=_action_object_id(action),
            expected_payload=dict(action.get("payload") or {}),
            readback=response,
        )

    def _exclusive_read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not method:
            raise ValueError("delivery readback method is missing")
        if hasattr(self.client, "rpc_exclusive_read"):
            return self.client.rpc_exclusive_read(method, payload)
        return self.client.rpc_readonly(method, payload)

    def _build_publish_plan(self, saved_receipt: dict[str, Any]) -> dict[str, Any]:
        source_path = self.journal.root / str(saved_receipt.get("source_artifact_uri") or "")
        actions: list[dict[str, Any]] = []
        for item in saved_receipt.get("objects") or []:
            built = create_publish_safe_apply_plan(
                project_root=str(self.journal.project_root),
                target=str(item.get("object_type") or "object"),
                object_type=str(item.get("object_type") or ""),
                object_id=str(item.get("object_id") or ""),
                saved_readback_path=str(source_path),
                approved=True,
                readback_mode="none",
                user_request_text=_delivery_intent(self.contract),
            )
            if not built.get("ok"):
                return built
            for action in built.get("actions") or []:
                combined_action = dict(action)
                # Each publish action is first derived from its own exact saved
                # readback entry.  The final transaction, however, is locked to
                # the complete action set.  Drop the singleton lock so
                # create_safe_apply_plan binds every action to that common set.
                combined_action.pop("target_lock_hash", None)
                actions.append(combined_action)
        plan = create_safe_apply_plan(
            project_root=str(self.journal.project_root),
            actions=actions,
            approved=True,
            approval_note="authorized by immutable public task contract",
            user_request_text=_delivery_intent(self.contract),
            task_contract_hash=str(self.contract.get("contract_hash") or ""),
        )
        plan["ok"] = True
        plan["status"] = "publish_plan_created"
        plan["saved_readback_hash"] = saved_receipt.get("receipt_hash")
        return plan

    def _write_result_receipt(
        self,
        *,
        schema_id: str,
        phase: str,
        binding_name: str,
        binding_hash: str,
        actions: list[dict[str, Any]],
        result: dict[str, Any],
        publish_plan_hash: str = "",
    ) -> dict[str, Any]:
        result_actions = list(result.get("actions") or result.get("results") or [])
        write_count = len(result.get("confirmed_write_action_indices") or [])
        if not write_count:
            write_count = sum(item.get("write_outcome") == "confirmed_write" for item in result_actions)
        status = _execution_status(result, result_actions)
        values = {
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            binding_name: binding_hash,
            "action_ids": _action_ids(actions, binding_hash),
            "provider_request_hashes": [canonical_hash(dict(item.get("payload") or {})) for item in actions],
            "expected_pre_write_revisions": [str(item.get("expected_revision") or "") for item in actions],
            "returned_revisions": [str((item.get("revisions") or {}).get("write") or "") for item in result_actions],
            "object_statuses": _object_statuses(actions, result_actions),
            "write_count": write_count,
            "ambiguity_state": "none" if status == "success" else status,
            "status": status,
            "safe_apply_result_hash": canonical_hash(sanitize_value(result)),
        }
        if phase == "publish":
            values["publish_plan_hash"] = publish_plan_hash
        if status != "success":
            reason = _execution_reason(result_actions)
            if reason:
                values["reason"] = reason
        return build_delivery_receipt(schema_id, **values)

    def _uncertain_write_receipt(
        self,
        *,
        schema_id: str,
        phase: str,
        plan_hash: str,
        actions: list[dict[str, Any]],
        reason: str,
        binding_name: str = "plan_hash",
        binding_hash: str = "",
    ) -> dict[str, Any]:
        values = {
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            binding_name: binding_hash or plan_hash,
            "action_ids": _action_ids(actions, binding_hash or plan_hash),
            "provider_request_hashes": [canonical_hash(dict(item.get("payload") or {})) for item in actions],
            "expected_pre_write_revisions": [str(item.get("expected_revision") or "") for item in actions],
            "returned_revisions": [],
            "object_statuses": [
                {"object_id": _action_object_id(item), "status": "unknown"}
                for item in actions
            ],
            "write_count": 0,
            "ambiguity_state": "write_outcome_unknown",
            "status": "ambiguous",
            "reason": reason,
        }
        if phase == "publish":
            values["publish_plan_hash"] = plan_hash
        return build_delivery_receipt(schema_id, **values)

    def _saved_source_matches(self, receipt: dict[str, Any]) -> bool:
        uri = str(receipt.get("source_artifact_uri") or "")
        path = (self.journal.root / uri).resolve()
        return bool(
            uri
            and path.is_relative_to(self.journal.root)
            and path.is_file()
            and canonical_hash(read_json(path, {}) or {}) == receipt.get("source_artifact_hash")
        )

    def _existing_delivery_receipt(self, path: Path, schema_id: str) -> dict[str, Any]:
        receipt = read_json(path, {}) or {}
        if not receipt:
            return {}
        issues = validate_delivery_receipt(
            receipt,
            schema_id=schema_id,
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
        )
        return {} if issues else receipt

    def _stage_receipt(
        self,
        context: dict[str, Any],
        delivery_receipt: dict[str, Any],
        *,
        proof_level: str,
    ) -> dict[str, Any]:
        status = str(delivery_receipt.get("status") or "failed")
        stage_status = {
            "success": "success",
            "ambiguous": "ambiguous",
            "conflict": "conflict",
        }.get(status, "blocked")
        missing = [] if stage_status == "success" else [delivery_receipt.get("schema_id")]
        path = _receipt_path(self.journal, str(delivery_receipt.get("schema_id") or ""))
        receipt = build_stage_receipt(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status=stage_status,
            proof_level=proof_level,
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            output_hashes={str(delivery_receipt.get("schema_id") or "delivery"): str(delivery_receipt.get("receipt_hash") or "")},
            provider_calls=list(delivery_receipt.get("provider_calls") or []),
            hard_requirements=[str(delivery_receipt.get("schema_id") or "delivery_receipt")],
            missing_requirements=[str(item) for item in missing if item],
            reason=str(delivery_receipt.get("reason") or status),
            observed_facts=[
                f"delivery receipt={delivery_receipt.get('schema_id')}",
                f"object count={len(delivery_receipt.get('objects') or delivery_receipt.get('object_statuses') or [])}",
                f"write count={delivery_receipt.get('write_count', 0)}",
            ],
        )
        receipt["artifact_uri"] = self.journal.receipt_uri(path.relative_to(self.journal.root).as_posix())
        receipt["artifact_sha256"] = delivery_receipt.get("receipt_hash")
        receipt["object_statuses"] = list(delivery_receipt.get("object_statuses") or delivery_receipt.get("objects") or [])
        receipt["expected_revision"] = next(iter(delivery_receipt.get("expected_pre_write_revisions") or []), "")
        return receipt

    def _blocked(self, context: dict[str, Any], reason: str, requirement: str) -> dict[str, Any]:
        return build_stage_receipt(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status="blocked",
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            hard_requirements=[requirement],
            missing_requirements=[requirement],
            reason=reason,
        )


def delivery_stage_services(
    journal: ProjectJournal,
    contract: dict[str, Any],
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    service = DeliveryTransactionService(journal, contract)
    return {
        "safe_apply_save": service.execute_save_stage,
        "read_saved_state": service.read_saved_stage,
        "publish_from_saved": service.execute_publish_from_saved_stage,
        "read_published_state": service.read_published_stage,
        "reconcile_ambiguous_write": service.reconcile_ambiguous_write,
    }


def _without_readback(plan: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(plan)
    result.pop("delivery_plan_hash", None)
    for action in result.get("actions") or []:
        action["readback_mode"] = "none"
        action["readback_required"] = False
        action["readback_justification"] = "readback executes as the next separately journaled typed stage"
    return result


def _verified_publish_plan(
    plan: dict[str, Any],
    *,
    saved_readback_hash: str,
) -> tuple[dict[str, Any], str]:
    if not plan or plan.get("saved_readback_hash") != saved_readback_hash or not plan.get("actions"):
        return {}, ""
    expected_hash = str(plan.get("delivery_plan_hash") or "")
    hash_input = deepcopy(plan)
    hash_input.pop("delivery_plan_hash", None)
    if not expected_hash or canonical_hash(hash_input) != expected_hash:
        return {}, ""
    return plan, expected_hash


def _execution_status(result: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    if result.get("ok") is True and str(result.get("status") or "") in {"completed", "success", "ok"}:
        return "success"
    errors = [item.get("error") or {} for item in actions if isinstance(item, dict)]
    if str(result.get("status") or "") == "partial" or any(
        item.get("write_outcome") == "unknown" or item.get("reconciliation_required") for item in errors
    ):
        return "ambiguous"
    if any(item.get("category") in {"stale_revision", "conflict_no_write"} for item in errors):
        return "conflict"
    return "blocked" if str(result.get("status") or "") == "blocked" else "failed"


def _action_ids(actions: list[dict[str, Any]], binding_hash: str) -> list[str]:
    return [
        canonical_hash(
            {
                "binding_hash": binding_hash,
                "index": index,
                "method": item.get("method"),
                "object_id": _action_object_id(item),
            }
        )
        for index, item in enumerate(actions)
    ]


def _object_statuses(actions: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "object_id": _action_object_id(action),
            "status": str((results[index] if index < len(results) else {}).get("status") or "not_attempted"),
            "write_outcome": str((results[index] if index < len(results) else {}).get("write_outcome") or ""),
        }
        for index, action in enumerate(actions)
    ]


def _execution_reason(actions: list[dict[str, Any]]) -> str:
    for action in actions:
        error = action.get("error") if isinstance(action.get("error"), dict) else {}
        category = str(error.get("category") or "").strip()
        message = str(error.get("message") or "").strip()
        if category or message:
            return ": ".join(item for item in (category, message[:300]) if item)
    return ""


def _action_object_id(action: dict[str, Any]) -> str:
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    fresh = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    return str(
        action.get("object_id")
        or entry.get("entryId")
        or payload.get("entryId")
        or fresh.get("dashboardId")
        or fresh.get("chartId")
        or fresh.get("entryId")
        or ""
    )


def _read_payload(action: dict[str, Any], branch: str) -> dict[str, Any]:
    payload = deepcopy(action.get("readback_payload") or action.get("fresh_read_payload") or {})
    payload["branch"] = branch
    return payload


def _attempt_marker(phase: str, *, plan_hash: str, execution_plan_hash: str) -> dict[str, Any]:
    payload = {
        "schema_id": "datalens_delivery_write_attempt",
        "phase": phase,
        "plan_hash": plan_hash,
        "execution_plan_hash": execution_plan_hash,
        "status": "started",
    }
    payload["attempt_hash"] = canonical_hash(payload)
    return payload


def _receipt_path(journal: ProjectJournal, schema_id: str) -> Path:
    return {
        "datalens_save_stage_receipt": journal.save_stage_receipt_path,
        "datalens_saved_readback_receipt": journal.saved_readback_receipt_path,
        "datalens_publish_stage_receipt": journal.publish_stage_receipt_path,
        "datalens_published_readback_receipt": journal.published_readback_receipt_path,
    }[schema_id]


def _delivery_intent(contract: dict[str, Any]) -> str:
    delivery = contract.get("delivery") or {}
    return "implement update and publish" if delivery.get("publish") else "implement update and save"
