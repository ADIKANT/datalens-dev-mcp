import unittest


class SafeApplyBaselineObjectReuseTests(unittest.TestCase):
    def test_create_without_reuse_decision_is_blocked_by_safe_apply_validation(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        plan = create_safe_apply_plan(
            project_root="/tmp/delta-v7",
            approved=True,
            actions=[
                {
                    "action": "create_runtime_fix_dataset",
                    "method": "createDataset",
                    "payload": {"dataset": {"name": "Runtime Fix V13"}},
                    "requires_fresh_read": True,
                    "fresh_read_method": "getWorkbookEntries",
                    "fresh_read_payload": {"workbookId": "workbook_1"},
                    "readback_method": "getWorkbookEntries",
                    "readback_payload": {"workbookId": "workbook_1"},
                }
            ],
        )

        result = validate_safe_apply_plan_exhaustive(plan)
        issue_text = "\n".join(result["issues"])

        self.assertFalse(result["ok"])
        self.assertIn("object_reuse_decision is required", issue_text)
        self.assertIn("temporary/runtime-fix object names require an explicit cleanup lifecycle", issue_text)

    def test_create_with_reuse_decision_and_cleanup_lifecycle_passes_reuse_gate(self):
        from datalens_dev_mcp.pipeline.baseline_preservation import build_object_reuse_decision
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        reuse = build_object_reuse_decision(
            desired_role="request_metric_dataset",
            selected_action="create",
            create_necessity_proof={
                "update_insufficient_reason": "existing dataset grain cannot support the requested metric",
                "existing_readback_checked": True,
            },
            cleanup_lifecycle={"mode": "created_object_registry"},
            baseline_proof_artifact="/tmp/baseline.json",
        )
        plan = create_safe_apply_plan(
            project_root="/tmp/delta-v7",
            approved=True,
            actions=[
                {
                    "action": "create_scoped_dataset",
                    "method": "createDataset",
                    "payload": {"dataset": {"name": "request_metric_dataset"}},
                    "object_reuse_decision": reuse,
                    "creation_necessity_proof": reuse["create_necessity_proof"],
                    "cleanup_lifecycle": reuse["cleanup_lifecycle"],
                    "requires_fresh_read": True,
                    "fresh_read_method": "getWorkbookEntries",
                    "fresh_read_payload": {"workbookId": "workbook_1"},
                    "readback_method": "getWorkbookEntries",
                    "readback_payload": {"workbookId": "workbook_1"},
                }
            ],
        )

        result = validate_safe_apply_plan_exhaustive(plan)
        issue_text = "\n".join(result["issues"])

        self.assertNotIn("object_reuse_decision is required", issue_text)
        self.assertNotIn("temporary/runtime-fix object names", issue_text)


if __name__ == "__main__":
    unittest.main()
