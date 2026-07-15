import json
import os
import sys
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


class ProjectLiveApplyAutoPublishFromSavedReadbackTests(unittest.TestCase):
    def test_project_live_apply_runs_manifest_publish_for_implementation_intent(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-02.project_live_workflow_manifest.v4",
                "project_name": "auto_publish",
                "workbook_id": "workbook_live",
                "dashboard_ids": ["dashboard_live"],
                "workflows": [
                    {
                        "name": "layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "apply": {"command": [sys.executable, "scripts/apply.py"], "summary_path": "reports/apply.json"},
                        "publish": {"command": [sys.executable, "scripts/publish.py"], "summary_path": "reports/publish.json"},
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text(
                "import json\nfrom pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
                "json.dump({'dashboard_id': 'dashboard_live', 'saved': True, "
                "'saved_readback_path': 'artifacts/readback/dashboard.saved.latest.json'}, open('reports/apply.json', 'w'))\n",
                encoding="utf-8",
            )
            (root / "scripts" / "publish.py").write_text(
                "import json\nfrom pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
                "json.dump({'dashboard_id': 'dashboard_live', 'published': True, "
                "'published_readback_path': 'artifacts/readback/dashboard.published.latest.json'}, open('reports/publish.json', 'w'))\n",
                encoding="utf-8",
            )

            result = dl_run_project_live_apply(
                str(root),
                workflow_name="layout",
                execute_now=True,
                delivery_intent_text="fix this dashboard",
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_then_publish")
        self.assertEqual(result["delivery_intent_decision"]["publish_stage_status"], "completed")
        self.assertTrue(result["project_live_delivery"]["saved"]["passed"])
        self.assertTrue(result["project_live_delivery"]["published"]["passed"])
        self.assertEqual(result["publish_blocked_reasons"], [])


if __name__ == "__main__":
    unittest.main()
