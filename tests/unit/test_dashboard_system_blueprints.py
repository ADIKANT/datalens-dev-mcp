import tempfile
import unittest
from pathlib import Path


class DashboardSystemBlueprintTests(unittest.TestCase):
    def test_selects_self_service_for_filter_heavy_detail_request(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import select_dashboard_blueprint

        result = select_dashboard_blueprint(
            "Need a self-service report with many filters, exportable detail table, and reset defaults.",
            data_profile={"fields": [f"field_{index}" for index in range(10)]},
        )

        self.assertEqual(result["dashboard_type"], "self_service")
        self.assertIn("table_node", result["recommended_chart_families"])
        self.assertIn("filter", result["selector_filter_behavior"].lower())

    def test_selects_alerts_for_threshold_subscription_request(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import select_dashboard_blueprint

        result = select_dashboard_blueprint("Create alert subscriptions for threshold exceptions and owner action.")

        self.assertEqual(result["dashboard_type"], "alerts_mailing")
        self.assertIn("thresholds_are_named", result["acceptance_checklist"])

    def test_ingest_populates_dashboard_map_and_canvas(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_requirements_markdown(
                tmp,
                markdown_text="Experiment report for A/B cohorts with hypothesis, variants, and rollout decision.",
                source_name="REQ-AB",
            )
            root = Path(tmp) / "requirements"
            map_text = (root / "dashboard_map.md").read_text(encoding="utf-8")
            canvas_text = (root / "dashboard_canvas.md").read_text(encoding="utf-8")

            self.assertTrue(result["ok"])
            self.assertEqual(result["dashboard_blueprint"]["dashboard_type"], "experiment_report")
            self.assertIn("Dashboard type: `experiment_report`", map_text)
            self.assertIn("Native title/hint rule", canvas_text)

    def test_mcp_blueprint_tools_are_registered(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"] for tool in list_tools("dashboard")}
        default_tools = {tool["name"] for tool in list_tools()}

        self.assertIn("dl_select_dashboard_blueprint", tools)
        self.assertIn("dl_populate_dashboard_map_canvas", tools)
        self.assertNotIn("dl_select_dashboard_blueprint", default_tools)


if __name__ == "__main__":
    unittest.main()
