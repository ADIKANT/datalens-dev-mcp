import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LiveSmokePlanTests(unittest.TestCase):
    def test_readonly_smoke_skips_without_live_flag(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("DATALENS_MCP_RUN_LIVE_TESTS", None)
        result = subprocess.run(
            [sys.executable, "scripts/live_smoke_readonly.py"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["skipped"])
        self.assertFalse(payload["write_attempted"])
        self.assertFalse(payload["publish_attempted"])
        self.assertNotIn("IAM_TOKEN", result.stdout)
        self.assertNotIn("Bearer", result.stdout)

    def test_readonly_smoke_has_no_safe_apply_execution_path(self):
        text = (ROOT / "scripts" / "live_smoke_readonly.py").read_text(encoding="utf-8")
        self.assertNotIn("execute_safe_apply", text)
        self.assertNotIn("dl_execute_safe_apply", text)
        self.assertNotIn("client.rpc(\"update", text)
        self.assertNotIn("client.rpc('update", text)

    def test_live_testing_doc_records_gates(self):
        text = (ROOT / "docs" / "live_testing_local.md").read_text(encoding="utf-8")
        for phrase in (
            "dl_runtime_status",
            "dl_auth_probe",
            "Save-only",
            "Save and publish",
            "delete_confirmation_required",
            "confirm_delete=true",
            "production-объекты",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
