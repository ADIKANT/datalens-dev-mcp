from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.target_binding import target_binding_hash
from datalens_dev_mcp.pipeline.task_data_proof_service import TaskDataProofService
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from datalens_dev_mcp.pipeline.task_qa_service import TaskQaService, _api_first_diagnostics_summary
from datalens_dev_mcp.runtime_resources import resource_json
from tests.integration.public_proof_support import execute_public_proof_workflow, plan_ready_task

DATA_IMPACTING_CHANGE = [
    {
        "target_id": "chart_demo",
        "slot_id": "series_label",
        "dataset_id": "dataset_demo",
        "field_guid": "guid_value",
        "change_kind": "filter_change",
        "value": {"operator": "GT", "value": 0},
    }
]


def test_public_workflow_uses_a_fresh_typed_probe_after_planning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, client, _started = plan_ready_task(
            Path(tmp), publish=True, semantic_changes=DATA_IMPACTING_CHANGE
        )
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
        journal, contract, client, _ = plan_ready_task(
            Path(tmp), publish=True, semantic_changes=DATA_IMPACTING_CHANGE
        )
        client.dataset_behavior = "fail"
        receipt = TaskDataProofService(journal, contract, client=client).execute()

    assert receipt["status"] == "insufficient_evidence"
    assert receipt["proof_level"] == "source_static"
    assert receipt["fallback_kind"].startswith("dataset_schema_only")
    assert receipt["live_data_verified"] is False


def test_unexpected_empty_final_probe_blocks_but_expected_empty_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(
            root, publish=True, semantic_changes=DATA_IMPACTING_CHANGE
        )
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
            semantic_changes=DATA_IMPACTING_CHANGE,
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


def test_data_diagnostics_are_impact_driven_when_browser_is_forbidden() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, client, _ = plan_ready_task(
            Path(tmp),
            publish=True,
            browser="forbidden",
            semantic_changes=[
                {
                    "target_id": "chart_demo",
                    "slot_id": "series_label",
                    "dataset_id": "dataset_demo",
                    "field_guid": "guid_value",
                    "change_kind": "filter_change",
                    "value": {"operator": "GT", "value": 0},
                }
            ],
        )
        receipt = TaskDataProofService(journal, contract, client=client).execute()
        impact_journal = journal

    decision = contract["data_diagnostics"]
    assert decision["required"] is True
    assert "filter_or_parameter_change" in decision["reason_classes"]
    assert decision["validate_dataset"] is True
    assert decision["assertion_probe"] is True
    assert receipt["api_first_diagnostics"]["status"] == "passed"
    assert [method for method, _payload in client.calls].count("validateDataset") == 1

    with tempfile.TemporaryDirectory() as tmp:
        layout_journal, layout_contract, layout_client, _ = plan_ready_task(
            Path(tmp),
            publish=True,
            browser="final_visual_acceptance",
            semantic_changes=[
                {"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"}
            ],
        )
        layout_receipt = TaskDataProofService(
            layout_journal,
            layout_contract,
            client=layout_client,
        ).execute()

    assert layout_contract["browser_policy"]["purpose"] == "final_visual_acceptance"
    assert layout_contract["data_diagnostics"]["required"] is False
    assert layout_receipt["status"] == "passed"
    assert layout_receipt["fallback_kind"] == "not_applicable"
    assert layout_receipt["api_first_diagnostics"]["decision"]["required"] is False
    assert [method for method, _payload in layout_client.calls].count("validateDataset") == 0
    assert [method for method, _payload in layout_client.calls].count("getDatasetData") == 0

    impact_summary = _api_first_diagnostics_summary(
        impact_journal,
        contract,
        data_receipt=receipt,
        saved={"status": "success"},
        published={"status": "success"},
    )
    assert impact_summary["required"] is True
    assert impact_summary["decision"]["required"] is True

    layout_summary = _api_first_diagnostics_summary(
        layout_journal,
        layout_contract,
        data_receipt=layout_receipt,
        saved={"status": "success"},
        published={"status": "success"},
    )
    assert layout_summary["required"] is False
    assert layout_summary["status"] == "passed"

    not_required_receipt = deepcopy(layout_receipt)
    not_required_receipt["status"] = "not_required"
    not_required_receipt["api_first_diagnostics"]["status"] = "not_required"
    boundary = TaskQaService(layout_journal, layout_contract, client=layout_client)._browser_evidence(
        layout_contract["browser_policy"],
        saved={"status": "success"},
        published={"status": "success"},
        data_receipt=not_required_receipt,
        plan_issues=[],
    )
    assert boundary["status"] == "awaiting_visual_acceptance"
    assert boundary["reason"] == "browser_adapter_unavailable"


def test_direct_editor_source_uses_saved_definition_readback_without_dataset_probe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, client, _ = plan_ready_task(
            Path(tmp), publish=True, semantic_changes=DATA_IMPACTING_CHANGE
        )
        graph = read_json(journal.target_graph_path, {})
        graph["nodes"] = [
            node for node in graph.get("nodes") or [] if node.get("object_type") != "dataset"
        ]
        write_json(journal.target_graph_path, graph)
        TaskDatasetContextService(journal, contract, client=client).persist_direct_editor_source(
            reason="synthetic direct Editor source boundary"
        )
        before = len(client.calls)
        receipt = TaskDataProofService(journal, contract, client=client).execute()
        proof_calls = [method for method, _payload in client.calls[before:]]

    assert receipt["status"] == "passed"
    assert receipt["proof_mode"] == "direct_editor_source"
    assert receipt["api_first_diagnostics"]["status"] == "passed"
    assert "getEditorChart" in proof_calls
    assert "getDataset" not in proof_calls
    assert "validateDataset" not in proof_calls
    assert "getDatasetData" not in proof_calls
