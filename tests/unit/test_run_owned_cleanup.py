from __future__ import annotations

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.run_owned_cleanup import execute_run_owned_cleanup
from datalens_dev_mcp.pipeline.task_contract import (
    ConfirmationContract,
    DeliveryContract,
    WorkspaceContract,
    create_task_contract,
)
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


def test_exact_run_owned_wizard_cleanup_uses_official_delete_and_absence_readback(tmp_path) -> None:
    source_task_id = "source_task_1"
    ownership = {
        "schema_id": "datalens_created_object_ownership",
        "task_id": source_task_id,
        "contract_hash": "a" * 64,
        "plan_hash": "b" * 64,
        "save_receipt_hash": "c" * 64,
        "objects": [
            {
                "run_id": "run_1",
                "created_by_task_id": source_task_id,
                "creation_receipt": "d" * 64,
                "parent_workbook": "workbook_1",
                "cleanup_route": "direct_object_delete",
                "inverse_or_recreate_plan": {"strategy": "delete_object_and_verify_absent"},
                "object_id": "wizard_1",
                "object_type": "wizard_chart",
                "workbook_id": "workbook_1",
            }
        ],
    }
    ownership["ownership_hash"] = canonical_hash(ownership)
    cleanup_plan = {
        "schema_id": "datalens_run_owned_cleanup_plan",
        "source_task_id": source_task_id,
        "ownership_hash": ownership["ownership_hash"],
        "objects": ownership["objects"],
        "delete_order": ["wizard_1"],
        "verify_absent": True,
    }
    cleanup_plan["plan_hash"] = canonical_hash(cleanup_plan)
    contract = create_task_contract(
        raw_request="Cleanup the exact run-owned objects",
        task_kind="cleanup_run_owned_objects",
        requested_outcome="cleanup run owned objects",
        mode="update",
        route="run_owned_cleanup",
        operation_kind="mutate",
        workspace=WorkspaceContract(project_root=str(tmp_path)),
        delivery=DeliveryContract(destructive=True),
        confirmation=ConfirmationContract(
            required=True,
            kind="destructive_exact_object",
            reason="exact objects",
        ),
    ).to_dict()
    journal = ProjectJournal(tmp_path, contract["task_id"])
    write_json(journal.root / "inputs" / "cleanup-ownership.json", ownership)
    write_json(journal.root / "plans" / "run-owned-cleanup-plan.json", cleanup_plan)

    class Client:
        def __init__(self) -> None:
            self.read_count = 0
            self.calls: list[tuple[str, dict]] = []

        def rpc_readonly(self, method: str, payload: dict, *, exclusive: bool = False):
            self.calls.append((method, dict(payload)))
            self.read_count += 1
            if self.read_count == 1:
                return {"workbookId": "workbook_1", "chartId": "wizard_1"}
            raise DataLensApiError("not found", http_status=404, failure_family="NOT_FOUND_404")

        def rpc(self, method: str, payload: dict, *, exclusive: bool = False):
            self.calls.append((method, dict(payload)))
            return {}

    client = Client()
    receipt = execute_run_owned_cleanup(journal, contract, client=client)

    assert receipt["all_verified_absent"] is True
    assert client.calls == [
        ("getWizardChart", {"chartId": "wizard_1", "branch": "saved"}),
        ("deleteWizardChart", {"chartId": "wizard_1"}),
        ("getWizardChart", {"chartId": "wizard_1", "branch": "saved"}),
    ]


def test_cleanup_start_does_not_require_generic_dashboard_discovery(tmp_path, monkeypatch) -> None:
    from unittest.mock import patch

    from datalens_dev_mcp.mcp.tools import tasks

    source_task_id = "source_dashboard_task"
    source_journal = ProjectJournal(tmp_path, source_task_id)
    source_journal.delivery_root.mkdir(parents=True, exist_ok=True)
    ownership = {
        "schema_id": "datalens_created_object_ownership",
        "task_id": source_task_id,
        "contract_hash": "a" * 64,
        "plan_hash": "b" * 64,
        "save_receipt_hash": "c" * 64,
        "objects": [
            {
                "run_id": "run_dashboard_1",
                "created_by_task_id": source_task_id,
                "creation_receipt": "d" * 64,
                "parent_workbook": "workbook_1",
                "cleanup_route": "direct_object_delete",
                "inverse_or_recreate_plan": {"strategy": "delete_object_and_verify_absent"},
                "object_id": "dashboard_1",
                "object_type": "dashboard",
                "workbook_id": "workbook_1",
            }
        ],
    }
    ownership["ownership_hash"] = canonical_hash(ownership)
    write_json(source_journal.delivery_root / "created-object-ownership.json", ownership)
    monkeypatch.setenv("DATALENS_MCP_TASKS_DIR", str(source_journal.storage_root))

    with patch.object(tasks.TargetDiscoveryService, "discover") as discover:
        started = tasks.dl_task_start(
            "Cleanup exactly the run-owned objects and verify them absent",
            project_root=str(tmp_path),
            context={"cleanup_task_id": source_task_id},
            run_until="plan_ready",
        )

    discover.assert_not_called()
    assert started["state"] == "PLAN_VALIDATED", started
    assert started["status"] == "needs_confirmation"
    assert started["execution_brief"]["target"]["object_ids"] == ["dashboard_1"]
