from __future__ import annotations

import tempfile
from pathlib import Path

from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.task_completion import TaskCompletionEvaluator
from tests.integration.public_proof_support import execute_public_proof_workflow, plan_ready_task


def test_completion_receipt_becomes_invalid_when_bound_evidence_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(root, publish=True)
        state, _executor, service = execute_public_proof_workflow(journal, contract, client)
        assert state.current_state == "COMPLETED"
        write_json(journal.published_readback_receipt_path, {"schema_id": "tampered"})
        assert service.read_verified() == {}
        result = TaskCompletionEvaluator().evaluate(journal, contract, proof_target="live")

    assert result["ok"] is False
    assert result["missing_evidence"] == ["valid completion evidence receipt"]
