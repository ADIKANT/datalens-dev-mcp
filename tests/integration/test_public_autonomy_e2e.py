from __future__ import annotations

import tempfile
from pathlib import Path

from tests.fixtures.public_autonomy_api.fake_api import PublicAutonomyApi
from tests.integration.public_autonomy_jsonrpc_support import public_call, public_server, semantic_context


def test_public_jsonrpc_completes_save_publish_and_verify_without_hidden_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        api = PublicAutonomyApi()
        with public_server(root, api) as server:
            started = public_call(
                server,
                1,
                "dl_task_start",
                {
                    "request": "Update dashboard https://datalens.example/dash_demo, save and publish without browser",
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
    assert verified["highest_proof_level"] == "publish_readback"
    assert api.write_count == 2
    methods = [method for method, _ in api.calls]
    assert methods.count("getDatasetData") == 2
    assert methods.count("getDataset") == 3
    first_write = methods.index("updateEditorChart")
    assert methods[first_write - 2 : first_write] == ["getEditorChart", "getDataset"]


def test_public_jsonrpc_publishes_multi_object_batch_under_one_target_lock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        api = PublicAutonomyApi(second_chart=True)
        changes = [
            *semantic_context()["semantic_changes"],
            {"target_id": "chart_demo_2", "slot_id": "series_label", "value": "Margin"},
        ]
        with public_server(root, api) as server:
            started = public_call(
                server,
                1,
                "dl_task_start",
                {
                    "request": "Update dashboard https://datalens.example/dash_demo, save and publish without browser",
                    "project_root": str(root),
                    "context": {"semantic_changes": changes},
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
    assert verified["highest_proof_level"] == "publish_readback"
    assert api.write_count == 4
    writes = [payload for method, payload in api.calls if method == "updateEditorChart"]
    assert [payload["entry"]["entryId"] for payload in writes] == [
        "chart_demo",
        "chart_demo_2",
        "chart_demo",
        "chart_demo_2",
    ]
    assert [payload["mode"] for payload in writes] == ["save", "save", "publish", "publish"]
