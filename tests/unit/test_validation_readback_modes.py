import tempfile
import unittest
from pathlib import Path


class FakeClient:
    def __init__(self):
        self.calls = []

    def rpc(self, method, payload):
        self.calls.append((method, payload))
        return {"method": method, "payload": payload}


class ObjectReadbackClient(FakeClient):
    def rpc(self, method, payload):
        self.calls.append((method, payload))
        if method == "getDataset":
            return {
                "dataset": {
                    "datasetId": payload["datasetId"],
                    "revId": "rev_ds",
                    "fields": [{"name": "amount", "guid": "guid_amount"}],
                    "sources": [{"type": "sql", "connectionId": "connection_1", "sql": "select * from table"}],
                }
            }
        if method == "getConnection":
            return {"connection": {"connectionId": payload["connectionId"], "revId": "rev_conn", "type": "postgres"}}
        return super().rpc(method, payload)


class ValidationReadbackModeTests(unittest.TestCase):
    def test_readback_none_skips_live_calls(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            report = dl_readback_and_report(
                tmp,
                target="dash",
                dashboard_id="dashboard_1",
                chart_ids=["chart_1"],
                readback_mode="none",
                client=client,
            )

        self.assertEqual(client.calls, [])
        self.assertEqual(report["readback"]["status"], "skipped")
        self.assertEqual(report["readback"]["proof_level"], "source_static")
        self.assertFalse(report["deployment_report"]["readback_required"])
        self.assertEqual(report["deployment_report"]["readback_proof_level"], "source_static")

    def test_minimal_readback_reads_dashboard_and_first_chart_only(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            report = dl_readback_and_report(
                tmp,
                target="dash",
                dashboard_id="dashboard_1",
                chart_ids=["chart_1", "chart_2"],
                readback_mode="minimal",
                client=client,
            )

        self.assertEqual([call[0] for call in client.calls], ["getDashboard", "getEditorChart"])
        self.assertEqual(report["readback"]["omitted_chart_ids"], ["chart_2"])
        self.assertEqual(report["readback"]["proof_level"], "save_readback")
        self.assertTrue(report["deployment_report"]["readback_required"])
        self.assertIn("save_readback", report["deployment_report"]["proof_levels"])

    def test_full_readback_reads_all_supplied_charts(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            report = dl_readback_and_report(
                tmp,
                target="dash",
                dashboard_id="dashboard_1",
                chart_ids=["chart_1", "chart_2"],
                readback_mode="full",
                client=client,
            )

        methods = [call[0] for call in client.calls]
        self.assertEqual(methods.count("getDashboard"), 1)
        self.assertEqual(methods.count("getEditorChart"), 2)
        self.assertEqual(methods.count("getEntriesRelations"), 1)
        self.assertEqual(report["readback"]["omitted_chart_ids"], [])
        self.assertIn("snapshot_manifest", report["readback"])

    def test_saved_and_published_readback_artifacts_are_separate(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

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
            saved_exists = saved_path.is_file()
            published_exists = published_path.is_file()

        self.assertTrue(saved_exists)
        self.assertTrue(published_exists)
        self.assertNotEqual(saved["readback"]["artifact_path"], published["readback"]["artifact_path"])
        self.assertEqual(saved["readback"]["branch"], "saved")
        self.assertEqual(published["readback"]["branch"], "published")
        self.assertEqual(saved["readback"]["proof_level"], "save_readback")
        self.assertEqual(published["readback"]["proof_level"], "publish_readback")

    def test_dataset_and_connection_readback_targets_execute(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

        with tempfile.TemporaryDirectory() as tmp:
            dataset_client = ObjectReadbackClient()
            dataset_report = dl_readback_and_report(
                tmp,
                target="dataset",
                dataset_id="dataset_1",
                readback_mode="minimal",
                client=dataset_client,
            )
            connection_client = ObjectReadbackClient()
            connection_report = dl_readback_and_report(
                tmp,
                target="connection",
                connection_id="connection_1",
                readback_mode="minimal",
                client=connection_client,
            )

        self.assertEqual(dataset_client.calls, [("getDataset", {"datasetId": "dataset_1"})])
        self.assertEqual(connection_client.calls, [("getConnection", {"connectionId": "connection_1"})])
        self.assertEqual(dataset_report["readback"]["counts_by_object_type"]["dataset"], 1)
        self.assertEqual(connection_report["readback"]["counts_by_object_type"]["connection"], 1)
        self.assertEqual(dataset_report["readback"]["dataset"]["summary"]["identity"]["id"], "dataset_1")
        self.assertEqual(connection_report["readback"]["connection"]["summary"]["identity"]["id"], "connection_1")

    def test_safe_apply_allows_readback_none_only_with_justification(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan

        plan = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "mode": "save",
                    "requires_fresh_read": True,
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                    "readback_mode": "none",
                    "payload": {
                        "mode": "save",
                        "entry": {"entryId": "chart_1", "revId": "rev_1", "data": {"javascript": "module.exports = {};"}},
                    },
                }
            ],
        )
        result = validate_safe_apply_plan(plan)
        self.assertFalse(result.ok)
        self.assertIn("readback_justification", "\n".join(result.issues))

        plan["actions"][0]["readback_justification"] = "covered by debug readback in previous stage"
        self.assertTrue(validate_safe_apply_plan(plan).ok)


if __name__ == "__main__":
    unittest.main()
