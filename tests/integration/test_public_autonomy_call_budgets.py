from __future__ import annotations

from pathlib import Path
import tempfile

from tests.fixtures.public_autonomy_api.fake_api import PublicAutonomyApi
from tests.integration.public_autonomy_jsonrpc_support import public_call, public_server, semantic_context


def test_write_workflow_completes_in_two_high_level_public_calls() -> None:
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
            verified = public_call(
                server,
                2,
                "dl_verify",
                {"task_id": started["task_id"], "project_root": str(root)},
            )

    assert started["state"] == "COMPLETED"
    assert verified["ok"] is True
    assert api.write_count == 2
    assert [method for method, _ in api.calls].count("getDatasetData") == 1


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
            saved = public_call(
                server,
                2,
                "dl_execute",
                {
                    "task_id": started["task_id"],
                    "plan_hash": started["plan_hash"],
                    "project_root": str(root),
                    "stop_after": "saved",
                },
            )
            restarted = type(server)(project_root=str(root))
            completed = public_call(
                restarted,
                3,
                "dl_task_resume",
                {"task_id": started["task_id"], "project_root": str(root), "run_until": "completed"},
            )
            verified = public_call(
                restarted,
                4,
                "dl_verify",
                {"task_id": started["task_id"], "project_root": str(root)},
            )

    assert saved["state"] == "SAVED"
    assert completed["state"] == "COMPLETED"
    assert verified["ok"] is True
    assert api.write_count == 2
