import os
import unittest
from unittest.mock import patch


class DeliveryIntentPolicyTests(unittest.TestCase):
    def test_environment_context_defaults_save_and_publish_on(self):
        from datalens_dev_mcp.pipeline.delivery_intent import delivery_context_from_env

        with patch.dict(os.environ, {}, clear=True):
            context = delivery_context_from_env(target_known=True, approved=True)

        self.assertTrue(context.writes_enabled)
        self.assertTrue(context.save_enabled)
        self.assertTrue(context.publish_enabled)
        self.assertFalse(context.publish_disabled_by_policy)

    def test_review_is_read_only_and_unknown_target_blocks_delivery(self):
        from datalens_dev_mcp.pipeline.delivery_intent import resolve_delivery_intent

        review = resolve_delivery_intent("review this dashboard")
        blocked = resolve_delivery_intent("сделай и обнови дашборд")

        self.assertEqual(review.intent, "read_only_review")
        self.assertEqual(review.state, "read_only")
        self.assertFalse(review.writes_expected)
        self.assertEqual(blocked.intent, "blocked_missing_target")
        self.assertEqual(blocked.state, "blocked")
        self.assertIn("target_lock", blocked.required_gates)

    def test_save_and_publish_delivery_reports_required_gates(self):
        from datalens_dev_mcp.pipeline.delivery_intent import DeliveryContext, resolve_delivery_intent

        decision = resolve_delivery_intent(
            "исправь и обнови",
            DeliveryContext(target_known=True, writes_enabled=True, safe_apply_approved=True),
        )

        self.assertEqual(decision.intent, "save_and_publish_delivery")
        self.assertEqual(decision.state, "save_then_publish")
        self.assertTrue(decision.publish_expected)
        self.assertIn("saved_readback_fresh", decision.required_gates)
        self.assertIn("published_readback", decision.required_gates)
        self.assertIn("user_request_authorization", decision.satisfied_gates)

    def test_draft_and_destructive_intents_are_separate(self):
        from datalens_dev_mcp.pipeline.delivery_intent import DeliveryContext, resolve_delivery_intent

        draft = resolve_delivery_intent(
            "save only draft",
            DeliveryContext(target_known=True, writes_enabled=True, safe_apply_approved=True),
        )
        destructive = resolve_delivery_intent(
            "delete the old chart",
            DeliveryContext(target_known=True, writes_enabled=True, safe_apply_approved=True),
        )

        self.assertEqual(draft.intent, "save_only_draft")
        self.assertEqual(draft.state, "save_only")
        self.assertFalse(draft.publish_expected)
        self.assertEqual(destructive.intent, "blocked_manual_review")
        self.assertEqual(destructive.state, "blocked")


if __name__ == "__main__":
    unittest.main()
