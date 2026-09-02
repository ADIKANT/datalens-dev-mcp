from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.public_autonomy_api.fake_api import PublicAutonomyApi
from tests.integration.public_autonomy_jsonrpc_support import (
    public_call,
    public_confirmation_arguments,
    public_server,
    public_task_root,
    semantic_context,
)


def test_missing_target_blocks_before_any_write(tmp_path: Path) -> None:
    result, api, _ = _start(PublicAutonomyApi(missing_dashboard=True), tmp_path)
    assert result["state"] == "BLOCKED"
    assert api.write_count == 0
    assert [method for method, _ in api.calls] == ["getDashboard"]


def test_stale_target_revision_blocks_entire_batch_before_write(tmp_path: Path) -> None:
    result, api, _ = _start(PublicAutonomyApi(stale_chart_after_reads=1), tmp_path)
    assert result["state"] == "BLOCKED"
    assert api.write_count == 0
    assert "revision/hash mismatch" in json.dumps(result).lower()


def test_permission_failure_does_not_refresh_or_retry(tmp_path: Path) -> None:
    result, api, _ = _start(PublicAutonomyApi(fail_read_method="getDashboard", failure_kind="403"), tmp_path)
    assert result["state"] == "BLOCKED"
    assert api.write_count == 0
    assert [method for method, _ in api.calls] == ["getDashboard"]


def test_experimental_dataset_endpoint_failure_is_explicit_static_fallback(tmp_path: Path) -> None:
    result, api, artifacts = _start(PublicAutonomyApi(dataset_behavior="unavailable"), tmp_path)
    assert result["state"] == "BLOCKED"
    receipt = artifacts["data_proof"]
    assert receipt["proof_level"] == "source_static"
    assert receipt["fallback_kind"].startswith("dataset_schema_only")
    assert receipt["live_data_verified"] is False
    assert receipt["raw_rows_inline"] is False
    assert [method for method, _ in api.calls].count("getDatasetData") == 2


def test_unexpected_empty_data_runs_diagnostics_and_does_not_claim_success(tmp_path: Path) -> None:
    result, _, artifacts = _start(PublicAutonomyApi(dataset_behavior="empty"), tmp_path)
    assert result["state"] == "BLOCKED"
    receipt = artifacts["data_proof"]
    assert receipt["status"] != "passed"
    assert receipt["unexpected_empty_diagnostics"]
    assert receipt["raw_rows_inline"] is False


def _start(api: PublicAutonomyApi, root: Path) -> tuple[dict, PublicAutonomyApi, dict]:
    with public_server(root, api) as server:
        result = public_call(
            server,
            1,
            "dl_task_start",
            {
                "request": "Update https://datalens.example/dash_demo, preserve content, save and publish",
                "project_root": str(root),
                "context": semantic_context(),
                "run_until": "completed",
            },
        )
        if result.get("state") == "PLAN_VALIDATED":
            result = public_call(
                server,
                2,
                "dl_task_resume",
                public_confirmation_arguments(result),
            )
        task_root = public_task_root(result["task_id"])
        proof_path = task_root / "evidence" / "data-proof-receipt.json"
        artifacts = {"data_proof": json.loads(proof_path.read_text(encoding="utf-8")) if proof_path.is_file() else {}}
    return result, api, artifacts
