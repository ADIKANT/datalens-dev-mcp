import unittest


class NoLiteralApproveRequiredTests(unittest.TestCase):
    def test_codex_tool_approval_source_is_enough_after_safe_gates(self):
        from datalens_dev_mcp.pipeline.approval_intent import SafeGates, resolve_approval_intent
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        lock = create_target_lock("update dashboard_id:dash_1", target_workbook_id="wb_1")
        decision = resolve_approval_intent(
            "update the dashboard",
            target_lock=lock,
            safe_gates=SafeGates(
                writes_enabled=True,
                safe_apply_approved=True,
                fresh_readback_available=True,
                revision_preservation_available=True,
                saved_readback_available=True,
                publish_enabled=True,
            ),
            approval_sources=["codex_tool_approval"],
        )

        self.assertTrue(decision.approved)
        self.assertEqual(decision.approval_source, "codex_tool_approval")
        self.assertFalse(decision.literal_chat_phrase_required)


if __name__ == "__main__":
    unittest.main()
