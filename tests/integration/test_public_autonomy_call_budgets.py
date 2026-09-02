from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.fixtures.public_autonomy_api.fake_api import PublicAutonomyApi
from tests.integration.public_autonomy_jsonrpc_support import (
    public_call,
    public_exchange,
    public_server,
    semantic_context,
)


def test_write_workflow_completes_after_one_confirmation_and_verify() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        api = PublicAutonomyApi()
        with public_server(root, api) as server:
            started = public_call(
                server,
                1,
                "dl_task_start",
                {
                    "request": "Update https://datalens.example/dash_demo without browser, save and publish",
                    "project_root": str(root),
                    "context": semantic_context(),
                    "run_until": "completed",
                },
            )
            rejected = public_call(
                server,
                2,
                "dl_execute",
                {
                    "task_id": started["task_id"],
                    "plan_hash": started["plan_hash"],
                    "project_root": str(root),
                },
            )
            assert api.write_count == 0
            executed = public_call(
                server,
                3,
                "dl_task_resume",
                {
                    "task_id": started["task_id"],
                    "project_root": str(root),
                    "follow_up": "Да, подтверждаю именно неизменный текущий план.",
                    "run_until": "completed",
                },
            )
            duplicate = public_call(
                server,
                4,
                "dl_task_resume",
                {
                    "task_id": started["task_id"],
                    "project_root": str(root),
                    "follow_up": "Повторно подтверждаю именно неизменный текущий план.",
                    "run_until": "completed",
                },
            )
            verified = public_call(
                server,
                5,
                "dl_verify",
                {"task_id": started["task_id"], "project_root": str(root)},
            )

    assert started["state"] == "PLAN_VALIDATED"
    assert started["status"] == "needs_confirmation"
    assert started["next_call"] is None
    confirmation_action = started["confirmation_action"]
    assert confirmation_action["tool"] == "dl_task_resume"
    assert confirmation_action["user_confirmation_field"] == "follow_up"
    assert confirmation_action["fixed_arguments"]["task_id"] == started["task_id"]
    assert "follow_up" not in confirmation_action["fixed_arguments"]
    assert rejected["status"] == "confirmation_required"
    assert executed["state"] == "COMPLETED"
    assert duplicate["state"] == "COMPLETED"
    assert verified["ok"] is True
    assert api.write_count == 2
    assert [method for method, _ in api.calls].count("getDatasetData") == 2


@pytest.mark.parametrize(
    ("follow_up", "expected_revision"),
    [
        ("Why did you choose this plan? Explain it first.", 1),
        ("Почему именно такой план? Сначала объясни.", 1),
        ("продолжай", 1),
        ("Do not change layout; change only the tooltip content.", 2),
        ("layout не меняй, измени только tooltip", 2),
        ("Do not publish; save only.", 2),
    ],
)
def test_pending_confirmation_follow_ups_never_write(
    follow_up: str,
    expected_revision: int,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        api = PublicAutonomyApi()
        with public_server(root, api) as server:
            started = public_call(
                server,
                1,
                "dl_task_start",
                {
                    "request": "Update https://datalens.example/dash_demo without browser, save and publish",
                    "project_root": str(root),
                    "context": semantic_context(),
                    "run_until": "completed",
                },
            )
            resumed = public_call(
                server,
                2,
                "dl_task_resume",
                {
                    "task_id": started["task_id"],
                    "project_root": str(root),
                    "follow_up": follow_up,
                    "run_until": "plan_ready",
                },
            )

            assert api.write_count == 0
            assert resumed["status"] == "needs_confirmation"
            assert (
                resumed["execution_brief"]["confirmation_action"]["fixed_arguments"][
                    "expected_contract_revision"
                ]
                == expected_revision
            )
            if expected_revision == 1:
                assert resumed["plan_hash"] == started["plan_hash"]
            else:
                assert resumed["plan_hash"] != started["plan_hash"]
                stale = public_exchange(
                    server,
                    3,
                    "dl_execute",
                    {
                        "task_id": started["task_id"],
                        "project_root": str(root),
                        "plan_hash": started["plan_hash"],
                    },
                )
                assert stale["ok"] is False
                assert api.write_count == 0


def test_restart_after_save_stays_below_ten_public_calls() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        api = PublicAutonomyApi()
        with public_server(root, api) as server:
            started = public_call(
                server,
                1,
                "dl_task_start",
                {
                    "request": "Update https://datalens.example/dash_demo, save and publish",
                    "project_root": str(root),
                    "context": semantic_context(),
                    "run_until": "plan_ready",
                },
            )
            restarted = type(server)(project_root=str(root))
            completed = public_call(
                restarted,
                2,
                "dl_task_resume",
                {
                    "task_id": started["task_id"],
                    "project_root": str(root),
                    "follow_up": "I explicitly confirm: execute exactly this unchanged plan.",
                    "run_until": "completed",
                },
            )
            verified = public_call(
                restarted,
                3,
                "dl_verify",
                {"task_id": started["task_id"], "project_root": str(root)},
            )

    assert completed["state"] == "COMPLETED"
    assert verified["ok"] is True
    assert api.write_count == 2
