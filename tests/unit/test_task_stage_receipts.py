from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from datalens_dev_mcp.pipeline.task_planning_stage_services import task_planning_stage_services
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt, validate_stage_receipt


class TaskStageReceiptTests(unittest.TestCase):
    def test_typed_receipt_is_bound_to_task_contract_and_transition(self) -> None:
        digest = "a" * 64
        receipt = build_stage_receipt(
            task_id="task-1", contract_hash=digest, transition="RESOLVED -> BASELINE_READ", status="success",
            build_identity_hash="c" * 64,
        )
        self.assertFalse(validate_stage_receipt(
            receipt, task_id="task-1", contract_hash=digest, transition="RESOLVED -> BASELINE_READ"
        ))
        self.assertIn("contract_hash mismatch", " ".join(validate_stage_receipt(
            receipt, task_id="task-1", contract_hash="b" * 64, transition="RESOLVED -> BASELINE_READ"
        )))

    def test_plain_success_is_not_a_receipt(self) -> None:
        issues = validate_stage_receipt(
            {"status": "success"}, task_id="task-1", contract_hash="a" * 64,
            transition="RESOLVED -> BASELINE_READ",
        )
        self.assertIn("typed stage receipt", " ".join(issues))

    def test_data_proof_stage_follows_typed_change_impact_decision(self) -> None:
        for required in (False, True):
            with self.subTest(required=required), tempfile.TemporaryDirectory() as tmp:
                contract = create_task_contract(
                    raw_request="Update a synthetic dashboard",
                    mode="update",
                    route="editor_advanced",
                    workspace=WorkspaceContract(project_root=tmp),
                ).to_dict()
                contract["data_diagnostics"] = {
                    **dict(contract["data_diagnostics"]),
                    "required": required,
                }
                journal = ProjectJournal(tmp, contract["task_id"])
                sentinel = {"status": "context_probe_called", "ok": True}
                with patch.object(
                    TaskDatasetContextService,
                    "stage_handler",
                    return_value=sentinel,
                ) as context_probe:
                    result = task_planning_stage_services(journal, contract)["plan_data_proof"](
                        {"transition": "ROUTE_BOUND -> DATA_PROOF_PLANNED"}
                    )

                if required:
                    self.assertEqual(result, sentinel)
                    context_probe.assert_called_once()
                else:
                    self.assertEqual(result["status"], "success")
                    self.assertIn("dataset probe not applicable", result["observed_facts"])
                    context_probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
