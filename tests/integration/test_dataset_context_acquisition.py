from __future__ import annotations

import tempfile
from pathlib import Path

from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService


class DatasetClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    def rpc_readonly(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if self.fail:
            raise ConnectionError("synthetic unavailable")
        return {
            "schema": [
                {"guid": "date_guid", "name": "event_date", "type": "date"},
                {"guid": "metric_guid", "name": "value", "type": "float"},
                {"guid": "key_guid", "name": "row_id", "type": "string"},
            ],
            "rows": [["2026-08-27", 5.5, "row-1"]],
        }


def _journal(root: Path) -> tuple[ProjectJournal, dict]:
    contract = create_task_contract(
        raw_request="Inspect synthetic dataset context",
        mode="diagnose",
        route="read_only",
        workspace=WorkspaceContract(project_root=str(root)),
    ).to_dict()
    journal = ProjectJournal(root, contract["task_id"])
    journal.initialize(contract)
    fields = [
        {"guid": "date_guid", "name": "event_date", "type": "date"},
        {"guid": "metric_guid", "name": "value", "type": "float"},
        {"guid": "key_guid", "name": "row_id", "type": "string", "unique": True},
    ]
    write_json(
        journal.target_graph_path,
        {
            "graph_hash": "a" * 64,
            "nodes": [
                {
                    "object_type": "dataset",
                    "object_id": "dataset_demo",
                    "saved_revision": "r2",
                    "field_catalog": fields,
                    "field_catalog_hash": "b" * 64,
                }
            ],
        },
    )
    return journal, contract


def test_context_acquisition_externalizes_rows_and_deduplicates_identical_probe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract = _journal(Path(tmp))
        client = DatasetClient()
        service = TaskDatasetContextService(journal, contract, client=client)
        first = service.acquire()
        second = service.acquire()
        raw_files = list((journal.root / "data" / "raw").glob("*.json"))
    assert first["ok"] is True
    assert second["cache_hit"] is True
    assert len(client.calls) == 1
    assert len(raw_files) == 1
    assert first["profile"]["raw_rows_inline"] is False
    assert "row-1" not in str(first["profile"])


def test_provider_failure_is_static_fallback_not_empty_dataset_claim() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract = _journal(Path(tmp))
        result = TaskDatasetContextService(journal, contract, client=DatasetClient(fail=True)).acquire()
    assert result["ok"] is True
    assert result["profile"]["proof_level"] == "source_static"
    assert result["profile"]["fallback_kind"].startswith("dataset_schema_only")
    assert "sample_empty" not in result["profile"]["admissible_claims"]
    assert "provider_unavailable" in result["profile"]["admissible_claims"]
    assert "getDatasetData unavailable" in result["profile"]["sample_scope"]["limitations"]
