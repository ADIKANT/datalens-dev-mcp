from __future__ import annotations

from datalens_dev_mcp.pipeline.object_action_mapper import map_materialized_action, semantic_fresh_read_spec
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan


def _patch_plan(object_id: str, object_type: str) -> dict:
    return {
        "schema_id": "semantic_patch_plan",
        "task_id": "task_demo",
        "targets": [{"object_id": object_id, "object_type": object_type, "sections": [{}]}],
        "plan_hash": "a" * 64,
    }


def test_editor_action_uses_projected_api_payload_and_fresh_saved_read() -> None:
    action = map_materialized_action(
        object_id="chart_demo",
        object_type="editor_chart",
        workbook_id="book_demo",
        saved_revision="r3",
        materialized_payload={
            "entryId": "chart_demo",
            "revId": "r3",
            "data": {"meta": "{}", "sources": "module.exports={};", "prepare": "module.exports={};"},
        },
        semantic_patch_plan=_patch_plan("chart_demo", "editor_chart"),
    )
    assert action["method"] == "updateEditorChart"
    assert action["payload"]["mode"] == "save"
    assert action["payload"]["entry"]["entryId"] == "chart_demo"
    assert action["fresh_read_payload"] == {"chartId": "chart_demo", "branch": "saved"}


def test_dashboard_action_never_uses_dashboard_id_as_target_chart_id() -> None:
    action = map_materialized_action(
        object_id="dash_demo",
        object_type="dashboard",
        workbook_id="book_demo",
        saved_revision="r7",
        materialized_payload={
            "entryId": "dash_demo",
            "revId": "r7",
            "meta": {},
            "data": {"tabs": []},
        },
        semantic_patch_plan=_patch_plan("dash_demo", "dashboard"),
    )
    plan = create_safe_apply_plan(project_root="/tmp/synthetic", actions=[action], approved=True)
    assert action["method"] == "updateDashboard"
    assert plan["target_lock"]["target_dashboard_id"] == "dash_demo"
    assert plan["target_lock"]["target_chart_id"] == ""


def test_semantic_dependency_reads_preserve_real_branch_contracts() -> None:
    chart = semantic_fresh_read_spec(
        object_id="chart_demo",
        object_type="editor_chart",
        workbook_id="book_demo",
    )
    dataset = semantic_fresh_read_spec(
        object_id="dataset_demo",
        object_type="dataset",
        workbook_id="book_demo",
    )
    assert chart == {
        "method": "getEditorChart",
        "payload": {"chartId": "chart_demo", "branch": "saved"},
        "object_type": "editor_chart",
    }
    assert dataset == {
        "method": "getDataset",
        "payload": {"datasetId": "dataset_demo", "workbookId": "book_demo"},
        "object_type": "dataset",
    }
    assert "branch" not in dataset["payload"]
