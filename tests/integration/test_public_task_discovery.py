from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
from tests.unit.test_target_discovery import DiscoveryClient


def test_public_task_closes_discovery_with_real_mocked_read_receipts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = TargetDiscoveryService(DiscoveryClient())
        with patch.object(tasks, "TargetDiscoveryService", return_value=service):
            result = tasks.dl_task_start(
                "Update dashboard https://datalens.example/dash_demo and save it",
                project_root=tmp,
                run_until="plan_ready",
            )
        journal = tasks.ProjectJournal(tmp, result["task_id"])
        graph = tasks.read_json(journal.target_graph_path, {})
        binding = tasks.read_json(journal.target_binding_path, {})
        style = tasks.read_json(journal.style_binding_path, {})
    assert result["state"] == "needs_semantic_actions"
    assert result["status"] == "needs_semantic_actions"
    assert result["required_next_call"]["tool"] == "dl_task_resume"
    assert result["required_next_call"]["arguments"]["user_turn"]["context"] == {
        "semantic_changes": []
    }
    assert result["object_index"]
    assert "blocked_by" not in result
    assert binding["source"] == "live_discovery"
    assert graph["graph_hash"]
    assert style["binding_hash"]
    assert result["target_binding_hash"] == binding["binding_hash"]
    assert result["style_binding_hash"] == style["binding_hash"]
    assert result["route"] == "editor_advanced"
    dataset = next(item for item in graph["nodes"] if item["object_type"] == "dataset")
    assert len(dataset["field_catalog"]) == 2


def test_public_inspect_returns_live_graph_not_local_artifact_listing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = TargetDiscoveryService(DiscoveryClient())
        with patch.object(tasks, "TargetDiscoveryService", return_value=service):
            result = tasks.dl_inspect(
                project_root=tmp,
                target_url="https://datalens.example/dash_demo",
            )
        assert Path(result["artifact_path"]).is_file()
    assert result["ok"] is True
    assert result["graph_kind"] == "live_target_graph"
    assert result["node_count"] >= 4
    assert all(
        str(item.get("canonical_direct_url") or "").startswith("https://datalens.ru/")
        for item in result["nodes"]
    )


def test_public_read_only_review_materializes_zero_action_plan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient()
        service = TargetDiscoveryService(client)
        with patch.object(tasks, "TargetDiscoveryService", return_value=service):
            result = tasks.dl_task_start(
                "Analyze dashboard https://datalens.example/dash_demo without changes",
                project_root=tmp,
                run_until="plan_ready",
            )
        journal = tasks.ProjectJournal(tmp, result["task_id"])
        plan = tasks.read_json(journal.root / "plans" / "plan.json", {})
        contract = journal.load_contract()

    assert result["state"] == "PLAN_VALIDATED"
    assert contract["operation_kind"] == "inspect"
    assert contract["delivery"] == {"save": False, "publish": False, "destructive": False}
    assert plan["plan_kind"] == "read_only_review"
    assert plan["safe_apply_action_count"] == 0
    assert all(method.startswith("get") for method, _ in client.calls)
