from __future__ import annotations

from typing import Any, Callable

from datalens_dev_mcp.pipeline.execution_authorization import authorizes_write
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt


class AutonomousTaskService:
    """Fail-closed application boundary for public task stages."""

    def __init__(
        self,
        journal: ProjectJournal,
        contract: dict[str, Any],
        *,
        execution_grant: dict[str, Any],
        build_identity_hash: str,
        target_binding_hash: str,
        stage_services: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
    ) -> None:
        self.journal = journal
        self.contract = contract
        self.execution_grant = execution_grant
        self.build_identity_hash = build_identity_hash
        self.target_binding_hash = target_binding_hash
        self.stage_services = dict(stage_services or {})

    def handlers(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        names = (
            "read_baseline", "bind_reference", "bind_route", "plan_data_proof",
            "plan_semantic_change", "validate_plan", "safe_apply_save",
            "read_saved_state", "publish_from_saved", "read_published_state",
            "run_qa", "verify_read_only_result", "verify_completion",
            "reconcile_ambiguous_write",
        )
        return {name: self._handler(name) for name in names}

    def _handler(self, name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def run(context: dict[str, Any]) -> dict[str, Any]:
            if name == "safe_apply_save" and not authorizes_write(self.execution_grant):
                return self._blocked(context, "write is not authorized by the persisted user request", "execution_authorization")
            if name == "publish_from_saved" and not authorizes_write(self.execution_grant, publish=True):
                return self._blocked(context, "publish is not authorized by the persisted user request", "execution_authorization")
            service = self.stage_services.get(name)
            if service is None:
                capability = "target_discovery" if name == "read_baseline" else name
                return self._blocked(context, "required stage service is not configured", capability)
            result = service(context)
            if result.get("schema_id") == "datalens_task_stage_receipt":
                return result
            return self._blocked(context, "stage service did not return a typed receipt", name)
        return run

    def _blocked(self, context: dict[str, Any], reason: str, capability: str) -> dict[str, Any]:
        receipt = build_stage_receipt(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status="blocked",
            build_identity_hash=self.build_identity_hash,
            target_binding_hash=self.target_binding_hash,
            hard_requirements=[capability],
            missing_requirements=[capability],
            reason=reason,
        )
        receipt["missing_capability"] = capability
        return receipt
