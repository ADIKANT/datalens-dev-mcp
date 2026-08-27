from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
