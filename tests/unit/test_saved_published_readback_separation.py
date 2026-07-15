import json
import tempfile
import unittest
from pathlib import Path


class SavedPublishedReadbackSeparationTests(unittest.TestCase):
    def test_readback_writes_saved_and_published_branch_artifacts_separately(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

        class FakeClient:
            def rpc(self, method, payload):
                return {"entry": {"entryId": payload.get("dashboardId") or "dashboard_1", "revId": payload.get("branch", "saved")}}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = dl_readback_and_report(
                tmp,
                target="dashboard",
                dashboard_id="dashboard_1",
                branch="saved",
                client=FakeClient(),
            )
            published = dl_readback_and_report(
                tmp,
                target="dashboard",
                dashboard_id="dashboard_1",
                branch="published",
                client=FakeClient(),
            )
            saved_path = root / "artifacts" / "readback" / "dashboard.saved.latest.json"
            published_path = root / "artifacts" / "readback" / "dashboard.published.latest.json"
            saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
            published_payload = json.loads(published_path.read_text(encoding="utf-8"))

        self.assertNotEqual(saved["readback"]["artifact_path"], published["readback"]["artifact_path"])
        self.assertEqual(saved_payload["branch"], "saved")
        self.assertEqual(published_payload["branch"], "published")
        self.assertEqual(saved_payload["proof_level"], "save_readback")
        self.assertEqual(published_payload["proof_level"], "publish_readback")
        self.assertNotEqual(saved_path, published_path)

    def test_publish_plan_rejects_published_unknown_branch_and_summary_only_readbacks(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            published_path = root / "dashboard.published.latest.json"
            published_path.write_text(
                json.dumps(
                    {
                        "branch": "published",
                        "dashboard": {"entry": {"entryId": "dash_1", "revId": "rev_pub", "savedId": "saved_1"}},
                    }
                ),
                encoding="utf-8",
            )
            unknown_path = root / "dashboard.unknown.latest.json"
            unknown_path.write_text(
                json.dumps(
                    {
                        "branch": "unknown",
                        "dashboard": {"entry": {"entryId": "dash_1", "revId": "rev_unknown", "savedId": "saved_1"}},
                    }
                ),
                encoding="utf-8",
            )
            summary_path = root / "dashboard.saved.latest.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "dashboard": {"entry": {"entryId": "dash_1", "revId": "rev_saved", "savedId": "saved_1"}},
                    }
                ),
                encoding="utf-8",
            )

            published_plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="dashboard",
                object_type="dashboard",
                saved_readback_path=str(published_path),
                approved=True,
            )
            unknown_plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="dashboard",
                object_type="dashboard",
                saved_readback_path=str(unknown_path),
                approved=True,
            )
            summary_plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="dashboard",
                object_type="dashboard",
                saved_readback_path=str(summary_path),
                approved=True,
            )

        self.assertFalse(published_plan["ok"])
        self.assertEqual(published_plan["error"]["category"], "invalid_saved_readback")
        self.assertFalse(unknown_plan["ok"])
        self.assertEqual(unknown_plan["error"]["category"], "invalid_saved_readback")
        self.assertFalse(summary_plan["ok"])
        self.assertEqual(summary_plan["error"]["category"], "incomplete_saved_entry")


if __name__ == "__main__":
    unittest.main()
