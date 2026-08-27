from __future__ import annotations

import tempfile
import unittest

from datalens_dev_mcp.mcp.tools.tasks import dl_task_start, dl_verify


class PublicTaskFailClosedTests(unittest.TestCase):
    def test_targetless_live_review_cannot_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            started = dl_task_start(
                "Review the current DataLens dashboard and verify it without browser",
                project_root=tmp, run_until="completed",
            )
            verified = dl_verify(started["task_id"], proof_target="live", project_root=tmp)
        self.assertEqual(started["state"], "BLOCKED")
        self.assertEqual(started["blocked_by"]["code"], "BLOCKED_DISCOVERY")
        self.assertFalse(verified["ok"])
        self.assertIn("live target binding", verified["missing_evidence"])

    def test_update_with_id_still_requires_server_owned_technical_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            started = dl_task_start(
                "Update dashboard synthetic_dashboard and publish it",
                project_root=tmp,
                context={"dashboard_id": "synthetic_dashboard", "object_ids": ["synthetic_dashboard"], "object_types": ["dashboard"]},
                run_until="completed",
            )
        self.assertEqual(started["state"], "BLOCKED")
        self.assertEqual(started["blocked_by"]["code"], "BLOCKED_DISCOVERY")
        self.assertIn("saved_revision", started["blocked_by"]["missing_facts"])
        self.assertNotIn("RESOLVED -> BASELINE_READ", started["performed"])


if __name__ == "__main__":
    unittest.main()
