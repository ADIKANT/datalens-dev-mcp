from __future__ import annotations

import tempfile
from unittest.mock import patch

from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
from tests.unit.test_target_discovery import DiscoveryClient


def test_exact_published_prompt_completes_from_saved_published_and_relation_reads_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient()
        with patch.object(tasks, "TargetDiscoveryService", return_value=TargetDiscoveryService(client)):
            result = tasks.dl_task_start(
                "Я уже опубликовал dashboard https://datalens.example/dash_demo — проверь.",
                project_root=tmp,
                run_until="completed",
            )
        journal = tasks.ProjectJournal(tmp, result["task_id"])
        receipt = read_json(journal.root / "evidence" / "existing-effect-verification.json", {})
        plan = read_json(journal.root / "plans" / "plan.json", {})

    assert result["state"] == "COMPLETED"
    assert result["operation_kind"] == "verify_existing_effect"
    assert result["effect"]["kind"] == "published"
    assert result["not_performed"] == ["save", "publish"]
    assert receipt["outcome"] == "verified"
    assert receipt["missing_live_reads"] == []
    assert receipt["write_attempted"] == 0
    assert receipt["write_executed"] == 0
    assert plan["safe_apply_action_count"] == 0
    assert [payload["branch"] for method, payload in client.calls if method == "getDashboard"] == [
        "saved", "published"
    ]
    assert all(method.startswith("get") for method, _ in client.calls)


def test_adjacent_generic_applied_changes_prompt_is_honestly_blocked_without_effect_spec() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient()
        with patch.object(tasks, "TargetDiscoveryService", return_value=TargetDiscoveryService(client)):
            result = tasks.dl_task_start(
                "Посмотри, применились ли правки в dashboard https://datalens.example/dash_demo.",
                project_root=tmp,
                run_until="completed",
            )
        journal = tasks.ProjectJournal(tmp, result["task_id"])
        receipt = read_json(journal.root / "evidence" / "existing-effect-verification.json", {})

    assert result["state"] == "BLOCKED"
    assert result["operation_kind"] == "verify_existing_effect"
    assert receipt["outcome"] == "indeterminate"
    assert "runtime_assertions_if_applicable" in receipt["missing_live_reads"]
    assert receipt["write_executed"] == 0
    assert all(method.startswith("get") for method, _ in client.calls)
