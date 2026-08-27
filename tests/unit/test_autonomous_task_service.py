from __future__ import annotations

import tempfile
import unittest

from datalens_dev_mcp.pipeline.autonomous_task_service import AutonomousTaskService
from datalens_dev_mcp.pipeline.execution_authorization import resolve_execution_authorization
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract, create_task_contract


class AutonomousTaskServiceTests(unittest.TestCase):
    def test_unconfigured_stage_fails_closed_with_typed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            contract = create_task_contract(
                raw_request="Review a synthetic target", mode="review", route="unresolved",
                workspace=WorkspaceContract(project_root=tmp),
            ).to_dict()
            journal = ProjectJournal(tmp, contract["task_id"])
            service = AutonomousTaskService(
                journal, contract, execution_grant=resolve_execution_authorization(contract),
                build_identity_hash="a" * 64, target_binding_hash="b" * 64,
            )
            receipt = service.handlers()["read_baseline"]({"transition": "RESOLVED -> BASELINE_READ"})
        self.assertEqual(receipt["schema_id"], "datalens_task_stage_receipt")
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["missing_capability"], "target_discovery")
        self.assertFalse(receipt["ok"])


if __name__ == "__main__":
    unittest.main()
