from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.delivery_transaction_service import DeliveryTransactionService
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


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
                    "run_id": "controlled_run_1",
                    "workbook_id": "workbook_1",
                    "workbook_lifecycle": "disposable_sibling",
                    "objects": [
                        {
                            "key": "dataset_main",
                            "object_type": "dataset",
                            "route": "dataset",
                            "name": "Synthetic dataset",
                            "payload_path": "payloads/dataset.json",
                            "dependencies": [],
                            "lifecycle": "temporary",
                            "cleanup_route": "whole_disposable_workbook_delete",
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
        task_root = ProjectJournal(root, result["task_id"]).root
        plan = json.loads((task_root / "plans" / "plan.json").read_text(encoding="utf-8"))
        binding = json.loads((task_root / "target-binding.json").read_text(encoding="utf-8"))
        assert plan["plan_kind"] == "create_manifest"
        assert plan["safe_apply_action_count"] == 1
        assert binding["workbook_id"] == "workbook_1"
        assert binding["dashboard_id"] == ""
        assert client.calls == [("getWorkbookEntries", {"workbookId": "workbook_1"})]


def test_create_correction_keeps_bundle_and_produces_a_new_confirmable_plan() -> None:
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
        with patch.object(tasks, "TargetDiscoveryService", return_value=TargetDiscoveryService(client)):
            started = tasks.dl_task_start(
                "Create the declared workbook objects, save and publish them without browser",
                project_root=str(root),
                context={"workbook_id": "workbook_1", "create_manifest": "create-manifest.json"},
                run_until="plan_ready",
            )
            corrected = tasks.dl_task_resume(
                started["task_id"],
                project_root=str(root),
                follow_up="Correction: create only the one declared object; keep save and publish.",
                run_until="plan_ready",
            )

        assert corrected["state"] == "PLAN_VALIDATED", corrected
        assert corrected["status"] == "needs_confirmation"
        assert corrected["contract_revision"] == 2
        assert corrected["plan_hash"] != started["plan_hash"]
        assert corrected["confirmation_action"]
        assert ProjectJournal(root, started["task_id"]).load_contract()["mode"] == "create"


def test_public_create_plan_binds_project_profile_exemplar_and_corrections() -> None:
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
        profile = {
            "accepted_layout": ["comparison, source, methodology"],
            "selector_semantics": "empty arrays mean all values",
            "title_hint_policy": "one visible title owner",
            "superseded_decisions": ["duplicated embedded title"],
        }
        exemplar = {
            "exemplar_id": "SYNTHETIC-ALPHA-COMPARISON",
            "object_id": "dataset_main",
            "visual_family": "comparison_matrix",
            "accepted_revision": "revision_alpha_1",
            "adaptation_rule": "replace every source-specific field",
        }
        descriptor = {
            "schema_id": "datalens_project_decision_context",
            "context_version": 1,
            "project_id": "synthetic_alpha",
            "match": {"workbook_ids": ["workbook_1"]},
            "profile": profile,
            "accepted_exemplars": [exemplar],
            "corrections": [
                {
                    "decision_id": "CORRECTION-ONE-TITLE",
                    "status": "active",
                    "statement": "remove the duplicated embedded title",
                    "source_sha256": "a" * 64,
                }
            ],
            "source_hashes": ["b" * 64],
        }
        descriptor_path = root / "decision-context.json"
        descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
        (root / ".datalens-mcp.json").write_text(
            json.dumps(
                {
                    "project_name": "Synthetic Alpha",
                    "workbook_id": "workbook_1",
                    "decision_context": {
                        "descriptor_path": "decision-context.json",
                        "sha256": hashlib.sha256(descriptor_path.read_bytes()).hexdigest(),
                    },
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
        with patch.object(tasks, "TargetDiscoveryService", return_value=TargetDiscoveryService(client)):
            started = tasks.dl_task_start(
                "Create the declared workbook objects and save them without browser",
                project_root=str(root),
                context={"workbook_id": "workbook_1", "create_manifest": "create-manifest.json"},
                run_until="plan_ready",
            )

        task_root = root / ".datalens-mcp" / "tasks" / started["task_id"]
        plan = json.loads((task_root / "plans" / "plan.json").read_text(encoding="utf-8"))
        binding = json.loads((task_root / "plans" / "plan-binding.json").read_text(encoding="utf-8"))
        style = json.loads((task_root / "style-binding.json").read_text(encoding="utf-8"))
        assert plan["project_profile_hash"] == canonical_hash(profile)
        assert plan["accepted_exemplar_hash"] == canonical_hash(exemplar)
        assert plan["decision_context_hash"] == style["decision_context_hash"]
        assert binding["decision_context_hash"] == style["decision_context_hash"]
        assert plan["bounded_project_decisions"]["active_corrections"] == [
            "remove the duplicated embedded title"
        ]


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
                    "run_id": "controlled_run_1",
                    "workbook_id": "workbook_1",
                    "workbook_lifecycle": "disposable_sibling",
                    "objects": [
                        {
                            "key": "dataset_main",
                            "object_type": "dataset",
                            "route": "dataset",
                            "name": "Synthetic dataset",
                            "payload_path": "payloads/dataset.json",
                            "dependencies": [],
                            "lifecycle": "temporary",
                            "cleanup_route": "whole_disposable_workbook_delete",
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
        ownership = json.loads(
            (task_root / "delivery" / "created-object-ownership.json").read_text(encoding="utf-8")
        )
        assert progress["identities"] == {"dataset_main": "dataset_created_1"}
        assert resolved["actions"][0]["object_id"] == "dataset_created_1"
        assert ownership["objects"] == [
            {
                "run_id": "controlled_run_1",
                "created_by_task_id": started["task_id"],
                "creation_receipt": save_receipt["receipt_hash"],
                "parent_workbook": "workbook_1",
                "cleanup_route": "whole_disposable_workbook_delete",
                "inverse_or_recreate_plan": {
                    "strategy": "delete_workbook_and_verify_absent",
                    "workbook_id": "workbook_1",
                },
                "object_id": "dataset_created_1",
                "object_type": "dataset",
                "workbook_id": "workbook_1",
                "canonical_direct_url": "https://datalens.ru/datasets/dataset_created_1",
                "url_source": "route_builder",
            }
        ]


def test_public_create_preflight_block_finalizes_attempt_as_no_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        payloads = root / "payloads"
        payloads.mkdir()
        unsafe_name = "DLM_CANARY_DLM_RECEIPT_20260830T0100Z_9e35686_dashboard"
        (payloads / "dashboard.json").write_text(
            json.dumps(
                {
                    "entry": {
                        "workbookId": "workbook_1",
                        "name": unsafe_name,
                        "scope": "dash",
                        "type": "",
                        "hidden": False,
                        "public": False,
                        "meta": {},
                        "annotation": {"description": "controlled exact blocker"},
                        "data": {
                            "accessDescription": "",
                            "counter": 1,
                            "salt": "0.9e35686",
                            "schemeVersion": 8,
                            "supportDescription": "exact-build negative canary",
                            "settings": {},
                            "tabs": [
                                {
                                    "id": "main",
                                    "title": "Main",
                                    "aliases": {},
                                    "connections": [],
                                    "items": [],
                                    "layout": [],
                                }
                            ],
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
                    "run_id": "controlled_receipt_run",
                    "workbook_id": "workbook_1",
                    "workbook_lifecycle": "disposable_sibling",
                    "objects": [
                        {
                            "key": "dashboard_main",
                            "object_type": "dashboard",
                            "route": "dashboard",
                            "name": unsafe_name,
                            "payload_path": "payloads/dashboard.json",
                            "dependencies": [],
                            "lifecycle": "temporary",
                            "cleanup_route": "whole_disposable_workbook_delete",
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
                "Create the declared run-owned dashboard and save it without browser",
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
        receipt = read_json(task_root / "delivery" / "save-stage-receipt.json", {})
        attempt = read_json(task_root / "delivery" / "private" / "create-000-attempt.json", {})

    assert executed["state"] == "BLOCKED"
    assert client.write_count == 0
    assert receipt["write_count"] == 0
    assert "unsafe DataLens internal names" in receipt["reason"]
    assert attempt["status"] == "blocked_no_write"
    assert attempt["resolved_at"]
    assert attempt["final_receipt_hash"] == receipt["receipt_hash"]


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
            journal = ProjectJournal(root, started["task_id"])
            contract = read_json(task_root / "contract.json", {})
            safe_plan = read_json(task_root / "plans" / "safe-apply-plan.json", {})
            service = DeliveryTransactionService(journal, contract, client=client)
            ambiguous = service._uncertain_write_receipt(
                schema_id="datalens_save_stage_receipt",
                phase="save",
                plan_hash=started["plan_hash"],
                actions=list(safe_plan.get("actions") or []),
                reason="simulated create write outcome unknown",
            )
            write_json(journal.save_stage_receipt_path, ambiguous)
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
