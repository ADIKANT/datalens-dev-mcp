from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService


class _InventoryClient:
    def __init__(self) -> None:
        self.calls = []

    def rpc_readonly(self, method, payload):
        self.calls.append((method, dict(payload)))
        assert method == "getWorkbookEntries"
        return {"workbookId": payload["workbookId"], "entries": [], "total": 0}


class _CreateDatasetClient(_InventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.created = False
        self.write_count = 0

    def rpc_readonly(self, method, payload):
        self.calls.append((method, dict(payload)))
        if method == "getWorkbookEntries":
            entries = (
                [
                    {
                        "entryId": "dataset_created_1",
                        "scope": "dataset",
                        "displayKey": "Synthetic dataset",
                    }
                ]
                if self.created
                else []
            )
            return {"workbookId": payload["workbookId"], "entries": entries, "total": len(entries)}
        if method == "getDataset":
            return {
                "id": "dataset_created_1",
                "revId": "revision_1",
                "savedId": "revision_1",
                "publishedId": "revision_1",
                "name": "Synthetic dataset",
                "dataset": {"sources": []},
            }
        raise AssertionError(method)

    def rpc_exclusive_read(self, method, payload):
        return self.rpc_readonly(method, payload)

    def rpc(self, method, payload):
        self.calls.append((method, dict(payload)))
        assert method == "createDataset"
        self.created = True
        self.write_count += 1
        return {
            "id": "dataset_created_1",
            "revId": "revision_1",
            "savedId": "revision_1",
            "publishedId": "revision_1",
            "name": "Synthetic dataset",
            "dataset": {"sources": []},
        }


class _CreateChainClient(_CreateDatasetClient):
    def __init__(self) -> None:
        super().__init__()
        self.chart_entry = None

    def rpc_readonly(self, method, payload):
        if method == "getWorkbookEntries":
            self.calls.append((method, dict(payload)))
            entries = []
            if self.created:
                entries.append(
                    {
                        "entryId": "dataset_created_1",
                        "scope": "dataset",
                        "displayKey": "Synthetic dataset",
                    }
                )
            if self.chart_entry:
                entries.append(
                    {
                        "entryId": "chart_created_1",
                        "scope": "editor_chart",
                        "displayKey": "Synthetic chart",
                    }
                )
            return {"workbookId": payload["workbookId"], "entries": entries, "total": len(entries)}
        if method == "getEditorChart":
            self.calls.append((method, dict(payload)))
            return {"entry": dict(self.chart_entry)}
        return super().rpc_readonly(method, payload)

    def rpc(self, method, payload):
        if method == "createEditorChart":
            self.calls.append((method, dict(payload)))
            self.write_count += 1
            self.chart_entry = {
                **dict(payload["entry"]),
                "entryId": "chart_created_1",
                "revId": "revision_chart_1",
                "savedId": "revision_chart_1",
                "publishedId": "revision_chart_1",
            }
            return {"entry": dict(self.chart_entry)}
        return super().rpc(method, payload)


def test_workbook_scoped_create_reaches_immutable_plan_without_dashboard_selection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        payloads = root / "payloads"
        payloads.mkdir()
        (payloads / "dataset.json").write_text(
            json.dumps(
                {
                    "workbookId": "workbook_1",
                    "dataset": {"sources": []},
                    "name": "Synthetic dataset",
                }
            ),
            encoding="utf-8",
        )
        (root / "create-manifest.json").write_text(
            json.dumps(
                {
                    "schema_id": "datalens_public_create_manifest",
                    "manifest_version": 1,
                    "workbook_id": "workbook_1",
                    "objects": [
                        {
                            "key": "dataset_main",
                            "object_type": "dataset",
                            "route": "dataset",
                            "name": "Synthetic dataset",
                            "payload_path": "payloads/dataset.json",
                            "dependencies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        client = _InventoryClient()
        discovery = TargetDiscoveryService(client)
        with patch.object(tasks, "TargetDiscoveryService", return_value=discovery):
            result = tasks.dl_task_start(
                "Create the declared workbook objects and save them without browser",
                project_root=str(root),
                context={
                    "workbook_id": "workbook_1",
                    "create_manifest": "create-manifest.json",
                },
                run_until="plan_ready",
            )

        assert result["state"] == "PLAN_VALIDATED", result
        assert result["plan_hash"]
        task_root = root / ".datalens-mcp" / "tasks" / result["task_id"]
        plan = json.loads((task_root / "plans" / "plan.json").read_text(encoding="utf-8"))
        binding = json.loads((task_root / "target-binding.json").read_text(encoding="utf-8"))
        assert plan["plan_kind"] == "create_manifest"
        assert plan["safe_apply_action_count"] == 1
        assert binding["workbook_id"] == "workbook_1"
        assert binding["dashboard_id"] == ""
        assert client.calls == [("getWorkbookEntries", {"workbookId": "workbook_1"})]


def test_public_create_executes_once_and_persists_resolved_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        payloads = root / "payloads"
        payloads.mkdir()
        (payloads / "dataset.json").write_text(
            json.dumps(
                {
                    "workbookId": "workbook_1",
                    "dataset": {"sources": []},
                    "name": "Synthetic dataset",
                }
            ),
            encoding="utf-8",
        )
        (root / "create-manifest.json").write_text(
            json.dumps(
                {
                    "schema_id": "datalens_public_create_manifest",
                    "manifest_version": 1,
                    "workbook_id": "workbook_1",
                    "objects": [
                        {
                            "key": "dataset_main",
                            "object_type": "dataset",
                            "route": "dataset",
                            "name": "Synthetic dataset",
                            "payload_path": "payloads/dataset.json",
                            "dependencies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        client = _CreateDatasetClient()
        discovery = TargetDiscoveryService(client)
        enabled = {
            "DATALENS_MCP_ENABLE_WRITES": "1",
            "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
            "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
        }
        with (
            patch.object(tasks, "TargetDiscoveryService", return_value=discovery),
            patch("datalens_dev_mcp.api.client.DataLensApiClient", return_value=client),
            patch.dict(os.environ, enabled, clear=False),
        ):
            started = tasks.dl_task_start(
                "Create the declared workbook objects and save them only without browser",
                project_root=str(root),
                context={"workbook_id": "workbook_1", "create_manifest": "create-manifest.json"},
                run_until="plan_ready",
            )
            executed = tasks.dl_execute(
                started["task_id"],
                started["plan_hash"],
                project_root=str(root),
                stop_after="saved",
            )
            task_root = root / ".datalens-mcp" / "tasks" / started["task_id"]
            save_receipt = json.loads(
                (task_root / "delivery" / "save-stage-receipt.json").read_text(encoding="utf-8")
            )

        assert executed["state"] == "SAVED", {"task": executed, "receipt": save_receipt}
        assert client.write_count == 1
        task_root = root / ".datalens-mcp" / "tasks" / started["task_id"]
        progress = json.loads(
            (task_root / "delivery" / "private" / "create-progress.json").read_text(encoding="utf-8")
        )
        resolved = json.loads(
            (task_root / "plans" / "resolved-create-safe-apply-plan.json").read_text(encoding="utf-8")
        )
        assert progress["identities"] == {"dataset_main": "dataset_created_1"}
        assert resolved["actions"][0]["object_id"] == "dataset_created_1"


def test_public_create_resume_reconciles_attempt_without_duplicate_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "payloads").mkdir()
        (root / "payloads" / "dataset.json").write_text(
            json.dumps(
                {
                    "workbookId": "workbook_1",
                    "dataset": {"sources": []},
                    "name": "Synthetic dataset",
                }
            ),
            encoding="utf-8",
        )
        (root / "create-manifest.json").write_text(
            json.dumps(
                {
                    "schema_id": "datalens_public_create_manifest",
                    "manifest_version": 1,
                    "workbook_id": "workbook_1",
                    "objects": [
                        {
                            "key": "dataset_main",
                            "object_type": "dataset",
                            "route": "dataset",
                            "name": "Synthetic dataset",
                            "payload_path": "payloads/dataset.json",
                            "dependencies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        client = _CreateDatasetClient()
        discovery = TargetDiscoveryService(client)
        enabled = {
            "DATALENS_MCP_ENABLE_WRITES": "1",
            "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
            "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
        }
        with (
            patch.object(tasks, "TargetDiscoveryService", return_value=discovery),
            patch("datalens_dev_mcp.api.client.DataLensApiClient", return_value=client),
            patch.dict(os.environ, enabled, clear=False),
        ):
            started = tasks.dl_task_start(
                "Create the declared workbook objects and save them only without browser",
                project_root=str(root),
                context={"workbook_id": "workbook_1", "create_manifest": "create-manifest.json"},
                run_until="plan_ready",
            )
            client.created = True
            task_root = root / ".datalens-mcp" / "tasks" / started["task_id"]
            attempt = task_root / "delivery" / "private" / "create-000-attempt.json"
            attempt.parent.mkdir(parents=True, exist_ok=True)
            attempt.write_text(json.dumps({"status": "started"}), encoding="utf-8")
            executed = tasks.dl_execute(
                started["task_id"],
                started["plan_hash"],
                project_root=str(root),
                stop_after="saved",
            )

        assert executed["state"] == "SAVED", executed
        assert client.write_count == 0
        progress = json.loads(
            (task_root / "delivery" / "private" / "create-progress.json").read_text(encoding="utf-8")
        )
        assert progress["identities"] == {"dataset_main": "dataset_created_1"}


def test_public_create_resolves_dependency_identity_before_dependent_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "payloads").mkdir()
        (root / "payloads" / "dataset.json").write_text(
            json.dumps(
                {
                    "workbookId": "workbook_1",
                    "dataset": {"sources": []},
                    "name": "Synthetic dataset",
                }
            ),
            encoding="utf-8",
        )
        (root / "payloads" / "chart.json").write_text(
            json.dumps(
                {
                    "entry": {
                        "workbookId": "workbook_1",
                        "name": "synthetic_chart",
                        "type": "advanced-chart_node",
                        "data": {
                            "meta": "{}",
                            "params": "{}",
                            "sources": 'module.exports = {datasetId: "${object:dataset_main}"};',
                            "prepare": "module.exports = {};",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        (root / "create-manifest.json").write_text(
            json.dumps(
                {
                    "schema_id": "datalens_public_create_manifest",
                    "manifest_version": 1,
                    "workbook_id": "workbook_1",
                    "objects": [
                        {
                            "key": "dataset_main",
                            "object_type": "dataset",
                            "route": "dataset",
                            "name": "Synthetic dataset",
                            "payload_path": "payloads/dataset.json",
                            "dependencies": [],
                        },
                        {
                            "key": "chart_main",
                            "object_type": "editor_chart",
                            "route": "editor_advanced",
                            "name": "synthetic_chart",
                            "payload_path": "payloads/chart.json",
                            "dependencies": ["dataset_main"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        client = _CreateChainClient()
        discovery = TargetDiscoveryService(client)
        enabled = {
            "DATALENS_MCP_ENABLE_WRITES": "1",
            "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
            "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
        }
        with (
            patch.object(tasks, "TargetDiscoveryService", return_value=discovery),
            patch("datalens_dev_mcp.api.client.DataLensApiClient", return_value=client),
            patch.dict(os.environ, enabled, clear=False),
        ):
            started = tasks.dl_task_start(
                "Create the declared workbook objects and save them only without browser",
                project_root=str(root),
                context={"workbook_id": "workbook_1", "create_manifest": "create-manifest.json"},
                run_until="plan_ready",
            )
            executed = tasks.dl_execute(
                started["task_id"],
                started["plan_hash"],
                project_root=str(root),
                stop_after="saved",
            )

        assert executed["state"] == "SAVED", {"write_count": client.write_count, "calls": client.calls}
        assert client.write_count == 2
        chart_payload = next(payload for method, payload in client.calls if method == "createEditorChart")
        assert "dataset_created_1" in chart_payload["entry"]["data"]["sources"]
        assert "${object:" not in json.dumps(chart_payload)
