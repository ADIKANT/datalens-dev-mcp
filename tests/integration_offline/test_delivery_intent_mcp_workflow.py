import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


WRITE_ENV = {
    "DATALENS_ENV_FILE": "",
    "DATALENS_MCP_ENABLE_WRITES": "1",
    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
}


class DeliveryIntentMcpWorkflowTests(unittest.TestCase):
    def test_fix_intent_traces_save_then_publish_plan_from_saved_readback(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_create_publish_from_saved_plan,
            dl_create_safe_apply_plan,
        )

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            payload_path = root / "artifacts" / "payloads" / "dashboard.payload.json"
            payload_path.parent.mkdir(parents=True)
            payload_path.write_text(
                json.dumps({"entry": {"name": "dashboard_fix", "data": {"name": "dashboard_fix", "title": "Dashboard"}}}),
                encoding="utf-8",
            )
            (root / "artifacts" / "payload_plan.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_live_1",
                        "payloads": [
                            {
                                "widget_id": "dashboard_fix",
                                "method": "createEditorChart",
                                "payload_path": str(payload_path),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            safe_plan = dl_create_safe_apply_plan(
                str(root),
                delivery_intent_text="implement the requested dashboard fix",
            )

            saved_path = root / "artifacts" / "readback" / "dashboard.saved.latest.json"
            saved_path.parent.mkdir(parents=True, exist_ok=True)
            saved_path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "dashboard": {
                            "entry": {
                                "entryId": "dash_1",
                                "revId": "rev_saved",
                                "savedId": "saved_123",
                                "data": {"counter": 1, "salt": "s", "schemeVersion": 8, "tabs": [], "settings": {}},
                                "meta": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            publish_plan = dl_create_publish_from_saved_plan(
                str(root),
                target="dashboard",
                object_type="dashboard",
                object_id="dash_1",
                saved_readback_path=str(saved_path),
                delivery_intent_text="implement the requested dashboard fix",
            )

        self.assertFalse(safe_plan["ok"], safe_plan)
        self.assertEqual(safe_plan["status"], "safe_apply_plan_blocked")
        self.assertIn(
            "object_reuse_decision is required",
            "\n".join(safe_plan["blocked_reasons"]),
        )
        self.assertEqual(safe_plan["delivery_intent_decision"]["intent"], "save_and_publish_delivery")
        self.assertEqual(safe_plan["delivery_intent_decision"]["state"], "save_then_publish")
        self.assertIn("Run saved readback.", safe_plan["delivery_intent_decision"]["next_actions"])
        self.assertTrue(publish_plan["ok"], publish_plan)
        self.assertEqual(publish_plan["delivery_intent_decision"]["state"], "publish_from_saved")
        self.assertEqual(publish_plan["delivery_intent_decision"]["target_branch"], "published")
        self.assertEqual(publish_plan["actions"][0]["payload"]["mode"], "publish")
        self.assertEqual(publish_plan["actions"][0]["readback_payload"]["branch"], "published")


if __name__ == "__main__":
    unittest.main()
