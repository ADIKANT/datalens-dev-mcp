from __future__ import annotations

import json
import tempfile
from pathlib import Path


def test_task_bound_create_ignores_unrelated_project_global_attestation() -> None:
    from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan

    action = {
        "action": "create_dataset",
        "action_type": "create",
        "method": "createDataset",
        "payload": {"workbookId": "workbook_1", "name": "synthetic", "dataset": {"sources": []}},
        "fresh_read_method": "getWorkbookEntries",
        "fresh_read_payload": {"workbookId": "workbook_1"},
        "readback_method": "getDataset",
        "readback_payload": {"workbookId": "workbook_1"},
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifact = root / "artifacts" / "final_payload_attestation.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            json.dumps(
                {
                    "schema_id": "final_payload_attestation",
                    "applicability": "required",
                    "ok": False,
                    "status": "stale_from_another_task",
                }
            ),
            encoding="utf-8",
        )
        legacy = create_safe_apply_plan(project_root=str(root), actions=[action], approved=True)
        task_bound = create_safe_apply_plan(
            project_root=str(root),
            actions=[action],
            approved=True,
            task_contract_hash="a" * 64,
        )

    assert legacy["final_payload_attestation"]["required"] is True
    assert task_bound["final_payload_attestation"] == {
        "required": False,
        "path": "",
        "sha256": "",
        "payload_set_sha256": "",
        "scope": "task_scoped_none",
    }


def test_create_delivery_reads_external_wizard_dataset_without_duplicate_dataset_create() -> None:
    from datalens_dev_mcp.pipeline.artifacts import write_json
    from datalens_dev_mcp.pipeline.delivery_transaction_service import DeliveryTransactionService
    from datalens_dev_mcp.pipeline.project_journal import ProjectJournal

    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def rpc_exclusive_read(self, method: str, payload: dict) -> dict:
            self.calls.append((method, dict(payload)))
            assert method == "getDataset"
            return {
                "datasetId": payload["datasetId"],
                "result_schema": [{"guid": "value_guid", "type": "float"}],
            }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal = ProjectJournal(root, "task_1")
        write_json(
            journal.root / "inputs" / "create-bundle.json",
            {"objects": [{"key": "other", "object_type": "editor_chart"}]},
        )
        client = Client()
        service = DeliveryTransactionService(
            journal,
            {"target": {"workbook_id": "workbook_1"}},
            client=client,
        )
        readbacks = service._dependency_dataset_readbacks(
            {"dependencies": []},
            {},
            resolved_payload={
                "data": {
                    "datasetsIds": ["dataset_existing_1"],
                    "datasetsPartialFields": [
                        [{"datasetId": "dataset_existing_1", "guid": "value_guid"}]
                    ],
                }
            },
        )

    assert len(readbacks) == 1
    assert client.calls == [
        (
            "getDataset",
            {"datasetId": "dataset_existing_1", "workbookId": "workbook_1"},
        )
    ]


def test_minimal_unseeded_wizard_payload_is_rejected_before_write() -> None:
    from datalens_dev_mcp.pipeline.safe_apply import (
        create_safe_apply_plan,
        validate_safe_apply_plan_exhaustive,
    )

    payload = {
        "workbookId": "workbook_1",
        "name": "synthetic_metric",
        "template": "datalens",
        "data": {
            "version": "2",
            "datasetsIds": ["dataset_existing_1"],
            "datasetsPartialFields": [
                {"datasetId": "dataset_existing_1", "guid": "value_guid"}
            ],
            "filters": [],
            "sort": [],
            "visualization": {
                "id": "metric",
                "placeholders": [
                    {
                        "id": "measures",
                        "items": [{"datasetId": "dataset_existing_1", "guid": "value_guid"}],
                    }
                ],
            },
        },
    }
    plan = create_safe_apply_plan(
        project_root="/tmp/synthetic-wizard-incident",
        approved=True,
        actions=[
            {
                "action": "create_wizard_chart",
                "action_type": "create",
                "method": "createWizardChart",
                "payload": payload,
                "fresh_read_method": "getWorkbookEntries",
                "fresh_read_payload": {"workbookId": "workbook_1"},
                "readback_method": "getWizardChart",
                "readback_payload": {"branch": "saved"},
                "dataset_readbacks": [
                    {
                        "datasetId": "dataset_existing_1",
                        "result_schema": [{"guid": "value_guid", "type": "float"}],
                    }
                ],
            }
        ],
    )
    result = validate_safe_apply_plan_exhaustive(plan)

    assert result["ok"] is False
    assert "fresh saved-seed live execution evidence" in "\n".join(result["issues"])
