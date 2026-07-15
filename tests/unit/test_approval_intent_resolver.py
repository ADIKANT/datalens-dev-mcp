import unittest


class ApprovalIntentResolverTests(unittest.TestCase):
    def test_no_literal_approve_required_for_normal_live_task(self):
        from datalens_dev_mcp.pipeline.approval_intent import SafeGates, resolve_approval_intent
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        lock = create_target_lock("implement dashboard_id:dash_1", target_workbook_id="wb_1")
        decision = resolve_approval_intent(
            "implement the target dashboard",
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
        self.assertFalse(decision.literal_chat_phrase_required)
        self.assertEqual(decision.default_delivery, ["save", "saved_readback", "publish", "published_readback"])

    def test_draft_override_stops_publish(self):
        from datalens_dev_mcp.pipeline.approval_intent import SafeGates, resolve_approval_intent
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        lock = create_target_lock("fix dashboard_id:dash_1", target_workbook_id="wb_1")
        decision = resolve_approval_intent(
            "fix target dashboard save only",
            target_lock=lock,
            safe_gates=SafeGates(
                writes_enabled=True,
                safe_apply_approved=True,
                fresh_readback_available=True,
                revision_preservation_available=True,
                publish_enabled=True,
            ),
            approval_sources=["codex_tool_approval"],
        )

        self.assertTrue(decision.approved)
        self.assertFalse(decision.publish_expected)
        self.assertEqual(decision.default_delivery, ["save", "saved_readback"])


if __name__ == "__main__":
    unittest.main()
