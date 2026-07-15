import unittest


class SavePublishDefaultForLiveImplementationTests(unittest.TestCase):
    def test_default_delivery_is_save_publish(self):
        from datalens_dev_mcp.pipeline.approval_intent import SafeGates, resolve_approval_intent
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        lock = create_target_lock("fix dashboard_id:dash_1", target_workbook_id="wb_1")
        decision = resolve_approval_intent(
            "fix the dashboard",
            target_lock=lock,
            safe_gates=SafeGates(
                writes_enabled=True,
                safe_apply_approved=True,
                fresh_readback_available=True,
                revision_preservation_available=True,
                saved_readback_available=True,
                publish_enabled=True,
            ),
            approval_sources=["current_user_request", "codex_tool_approval"],
        )

        self.assertEqual(decision.default_delivery, ["save", "saved_readback", "publish", "published_readback"])
        self.assertTrue(decision.publish_expected)


if __name__ == "__main__":
    unittest.main()
