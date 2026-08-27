from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import datalens_dev_mcp.pipeline.task_planning_stage_services as planning_services
from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.completion_evidence import CompletionEvidenceService
from datalens_dev_mcp.pipeline.delivery_transaction_service import DeliveryTransactionService
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
from datalens_dev_mcp.pipeline.task_completion import completion_stage_service
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from datalens_dev_mcp.pipeline.task_qa_service import TaskQaService
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine
from tests.integration.test_public_dataset_context_workflow import PlanningClient


class ProofClient(PlanningClient):
    def __init__(self) -> None:
        super().__init__()
        self.saved_entries: dict[str, dict] = {}
        self.published_entries: dict[str, dict] = {}
        self.dataset_behavior = "normal"

    def rpc_readonly(self, method: str, payload: dict) -> dict:
        if method == "getDatasetData" and self.dataset_behavior != "normal":
            self.calls.append((method, deepcopy(payload)))
            if self.dataset_behavior == "fail":
                raise ConnectionError("synthetic getDatasetData unavailable")
            if self.dataset_behavior == "empty":
                return {
                    "schema": [
                        {"guid": "guid_date", "name": "event_date", "type": "date"},
                        {"guid": "guid_value", "name": "value", "type": "float"},
                    ],
                    "rows": [],
                }
        return super().rpc_readonly(method, payload)

    def rpc_exclusive_read(self, method: str, payload: dict) -> dict:
        self.calls.append((method, deepcopy(payload)))
        object_id = str(payload.get("chartId") or payload.get("dashboardId") or "")
        entries = self.published_entries if payload.get("branch") == "published" else self.saved_entries
        return {"entry": deepcopy(entries.get(object_id) or {})}


class ProofExecutor:
    def __init__(self) -> None:
        self.plans: list[dict] = []

    def __call__(self, plan: dict) -> dict:
        self.plans.append(deepcopy(plan))
        return {
            "ok": True,
            "status": "completed",
            "confirmed_write_action_indices": list(range(len(plan.get("actions") or []))),
            "actions": [
                {"status": "completed", "write_outcome": "confirmed_write", "revisions": {"write": "r-proof"}}
                for _ in plan.get("actions") or []
            ],
        }


def plan_ready_task(
    root: Path,
    *,
    publish: bool = True,
    browser: str = "forbidden",
    extra_acceptance: list[dict] | None = None,
):
    client = ProofClient()
    discovery = TargetDiscoveryService(client)

    def context_factory(journal, contract):
        return TaskDatasetContextService(journal, contract, client=client)

    delivery_text = "save and publish" if publish else "save only"
    browser_text = "without browser" if browser == "forbidden" else "browser is required"
    with (
        patch.object(tasks, "TargetDiscoveryService", return_value=discovery),
        patch.object(planning_services, "TaskDatasetContextService", side_effect=context_factory),
    ):
        result = tasks.dl_task_start(
            f"Update dashboard https://datalens.example/dash_demo, {delivery_text}; {browser_text}",
            project_root=str(root),
            context={
                "acceptance": list(extra_acceptance or []),
                "semantic_changes": [
                    {"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"}
                ]
            },
            run_until="plan_ready",
        )
    journal = tasks.ProjectJournal(root, result["task_id"])
    contract = journal.load_contract()
    safe_plan = read_json(journal.root / "plans" / "safe-apply-plan.json", {}) or {}
    for action in safe_plan.get("actions") or []:
        payload = deepcopy(action.get("payload") or {})
        entry = deepcopy(payload.get("entry") or payload)
        object_id = str(action.get("object_id") or entry.get("entryId") or "")
        entry["entryId"] = object_id
        entry["revId"] = "r-proof"
        entry["savedId"] = f"saved-{object_id}"
        client.saved_entries[object_id] = deepcopy(entry)
        client.published_entries[object_id] = deepcopy(entry)
    return journal, contract, client, result


def execute_public_proof_workflow(
    journal,
    contract,
    client: ProofClient,
    *,
    browser_adapter=None,
):
    executor = ProofExecutor()
    delivery = DeliveryTransactionService(journal, contract, client=client, executor=executor)
    qa = TaskQaService(journal, contract, client=client, browser_adapter=browser_adapter)
    handlers = {
        "safe_apply_save": delivery.execute_save_stage,
        "read_saved_state": delivery.read_saved_stage,
        "publish_from_saved": delivery.execute_publish_from_saved_stage,
        "read_published_state": delivery.read_published_stage,
        "reconcile_ambiguous_write": delivery.reconcile_ambiguous_write,
        "run_qa": qa.stage_handler,
        "verify_read_only_result": qa.stage_handler,
        **completion_stage_service(journal, contract),
    }
    engine = WorkflowEngine(
        journal,
        contract,
        handlers=handlers,
        build_identity=read_json(journal.build_identity_path, {}),
        target_binding=read_json(journal.target_binding_path, {}),
        style_binding_hash=str((read_json(journal.style_binding_path, {}) or {}).get("binding_hash") or ""),
        require_typed_receipts=True,
    )
    return engine.resume(), executor, CompletionEvidenceService(journal, contract)
