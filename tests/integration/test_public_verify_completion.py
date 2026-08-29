from __future__ import annotations

import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from datalens_dev_mcp.mcp.tools.tasks import dl_verify
from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.task_qa_service import _acceptance_coverage
from datalens_dev_mcp.runtime_resources import resource_json
from tests.integration.public_proof_support import execute_public_proof_workflow, plan_ready_task


def test_dl_verify_is_stable_across_restart_and_reads_typed_completion_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _started = plan_ready_task(root, publish=True)
        state, _executor, _completion = execute_public_proof_workflow(journal, contract, client)
        first = dl_verify(journal.task_id, project_root=str(root))
        second = dl_verify(journal.task_id, project_root=str(root))
        data_plan = read_json(journal.root / "plans" / "task-data-proof-plan.json", {})
        qa_receipt = read_json(journal.root / "evidence" / "qa-receipt.json", {})
        completion_receipt = read_json(journal.root / "evidence" / "completion-evidence.json", {})

    assert state.current_state == "COMPLETED"
    assert first == second
    assert first["ok"] is True
    assert first["highest_proof_level"] == "publish_readback"
    assert first["missing_evidence"] == []
    assert first["completion_receipt_uri"].endswith("/evidence/completion-evidence.json")
    for schema_name, payload in (
        ("task-data-proof-plan.schema.json", data_plan),
        ("task-qa-receipt.schema.json", qa_receipt),
        ("completion-evidence.schema.json", completion_receipt),
    ):
        assert not list(Draft202012Validator(resource_json(f"schemas/{schema_name}")).iter_errors(payload))


def test_missing_hard_acceptance_evidence_blocks_completion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(
            root,
            publish=True,
            extra_acceptance=[
                {
                    "kind": "business",
                    "statement": "A business outcome with no executable evidence contract",
                    "hard": True,
                }
            ],
        )
        state, _executor, _completion = execute_public_proof_workflow(journal, contract, client)
        qa = read_json(journal.root / "evidence" / "qa-receipt.json", {})

    assert state.current_state == "BLOCKED"
    assert qa["acceptance_coverage"]["ok"] is False
    assert qa["acceptance_coverage"]["missing_evidence"] == ["hard_acceptance:0"]


def test_compiler_owned_amendment_constraint_uses_amended_runtime_evidence() -> None:
    contract = {
        "contract_revision": 2,
        "parent_contract_hash": "a" * 64,
        "semantic_delta_hash": "b" * 64,
        "delivery": {"save": True, "publish": True},
        "acceptance": [
            {
                "kind": "constraint",
                "statement": "Keep the target and apply the corrected value.",
                "source": "current_user_correction",
                "hard": True,
            }
        ],
    }
    covered = _acceptance_coverage(
        contract,
        data_receipt={},
        runtime_ok=True,
        saved={"status": "success"},
        published={"status": "success"},
    )
    unbound = _acceptance_coverage(
        {**contract, "contract_revision": 1, "parent_contract_hash": "", "semantic_delta_hash": ""},
        data_receipt={},
        runtime_ok=True,
        saved={"status": "success"},
        published={"status": "success"},
    )

    assert covered["ok"] is True
    assert covered["criteria"][0]["evidence_kind"] == "amended_contract_runtime"
    assert unbound["ok"] is False
