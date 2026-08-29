from __future__ import annotations

import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.target_binding import target_binding_hash
from datalens_dev_mcp.pipeline.task_data_proof_service import TaskDataProofService
from datalens_dev_mcp.runtime_resources import resource_json
from tests.integration.public_proof_support import execute_public_proof_workflow, plan_ready_task


def test_public_workflow_uses_a_fresh_typed_probe_after_planning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, client, _started = plan_ready_task(Path(tmp), publish=True)
        planning_profile = read_json(journal.root / "data" / "context-profile.json", {})
        state, executor, _completion = execute_public_proof_workflow(journal, contract, client)
        data_receipt = read_json(journal.root / "evidence" / "data-proof-receipt.json", {})
        final_planning_profile = read_json(journal.root / "data" / "context-profile.json", {})

    assert state.current_state == "COMPLETED"
    assert len(executor.plans) == 2
    assert [method for method, _payload in client.calls].count("getDatasetData") == 2
    assert data_receipt["fresh"] is True
    assert data_receipt["proof_level"] == "live_read_only_api"
    assert data_receipt["live_data_verified"] is True
    assert data_receipt["raw_rows_inline"] is False
    assert final_planning_profile == planning_profile
    assert not list(
        Draft202012Validator(resource_json("schemas/task-data-proof-receipt.schema.json")).iter_errors(data_receipt)
    )


def test_exact_limit_sample_does_not_promote_population_uniqueness() -> None:
    from datalens_dev_mcp.pipeline.data_assertions import evaluate_data_assertions

    result = evaluate_data_assertions(
        assertions=[{"kind": "unique_key", "fields": ["id"]}],
        schema=[{"guid": "id", "type": "integer"}],
        rows=[{"id": 1}, {"id": 2}],
        paging={"complete": False},
    )
    assert result["status"] == "insufficient_evidence"


def test_final_provider_failure_is_static_fallback_not_live_proof() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, client, _ = plan_ready_task(Path(tmp), publish=True)
        client.dataset_behavior = "fail"
        receipt = TaskDataProofService(journal, contract, client=client).execute()

    assert receipt["status"] == "insufficient_evidence"
    assert receipt["proof_level"] == "source_static"
    assert receipt["fallback_kind"].startswith("dataset_schema_only")
    assert receipt["live_data_verified"] is False


def test_unexpected_empty_final_probe_blocks_but_expected_empty_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(root, publish=True)
        client.dataset_behavior = "empty"
        blocked, _executor, _ = execute_public_proof_workflow(journal, contract, client)
        unexpected = read_json(journal.root / "evidence" / "data-proof-receipt.json", {})
    assert blocked.current_state == "BLOCKED"
    assert unexpected["status"] == "failed"
    assert unexpected["unexpected_empty_diagnostics"]
    assert [method for method, _payload in client.calls].count("getDatasetData") == 3
    assert unexpected["unexpected_empty_diagnostics"][0]["check"] == "unfiltered_dataset_probe"
    assert unexpected["unexpected_empty_diagnostics"][0]["mode"] == "diagnostic_probe"
    assert unexpected["unexpected_empty_diagnostics"][0]["status"] == "still_empty"
    assert unexpected["unexpected_empty_diagnostics"][0]["raw_rows_inline"] is False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(
            root,
            publish=True,
            extra_acceptance=[{"kind": "expected_empty", "statement": "{}", "hard": True}],
        )
        client.dataset_behavior = "empty"
        completed, _executor, _ = execute_public_proof_workflow(journal, contract, client)
        expected = read_json(journal.root / "evidence" / "data-proof-receipt.json", {})
    assert completed.current_state == "COMPLETED"
    assert expected["status"] == "passed"
    assert expected["unexpected_empty_diagnostics"] == []
    assert [method for method, _payload in client.calls].count("getDatasetData") == 2


def test_target_binding_change_blocks_fresh_probe_before_provider_call() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, client, _ = plan_ready_task(Path(tmp), publish=True)
        before = [method for method, _ in client.calls].count("getDatasetData")
        binding = read_json(journal.target_binding_path, {})
        binding["saved_revision"] = "changed-after-plan"
        binding["binding_hash"] = target_binding_hash(binding)
        write_json(journal.target_binding_path, binding)
        receipt = TaskDataProofService(journal, contract, client=client).execute()
        after = [method for method, _ in client.calls].count("getDatasetData")

    assert receipt["status"] == "blocked"
    assert receipt["fallback_kind"] == "stale_planning_binding"
    assert before == after
