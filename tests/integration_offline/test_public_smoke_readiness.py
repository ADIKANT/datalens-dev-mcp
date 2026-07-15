import json
import tempfile
import unittest
from pathlib import Path


class PublicSmokeReadinessTests(unittest.TestCase):
    def test_placeholder_dashboard_flow(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_create_dataset_field_plan,
            dl_create_dataset_plan,
            dl_create_wizard_chart_plan,
            dl_publish_object_plan,
            dl_save_object_plan,
        )
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_governance_brief,
            dl_build_payload_plan,
            dl_create_safe_apply_plan,
            dl_generate_editor_bundle,
            dl_ingest_requirements_markdown,
            dl_readback_and_report,
            dl_start_pipeline,
            dl_validate_project,
        )

        with tempfile.TemporaryDirectory() as tmp:
            dl_start_pipeline(tmp, scenario="new_dashboard", dashboard_name="Public Smoke")
            dl_ingest_requirements_markdown(
                tmp,
                markdown_text=(
                    "# Public Smoke Dashboard\n"
                    "- Dataset table: mart.smoke_orders\n"
                    "- Connector: analytics-placeholder\n"
                    "- Field attribute: order_month\n"
                    "- Field attribute: region\n"
                    "- Metric KPI: order_count\n"
                    "- Selector filter control: region\n"
                    "- Chart visual: heatmap by order month and region\n"
                    "- Page tab: Overview\n"
                ),
                source_name="REQ-smoke",
            )
            brief = dl_build_governance_brief(tmp)
            brief["data_contract"]["fields"] = ["order_month", "region", "order_count"]
            from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec

            brief["chart_decisions"][0]["family"] = "heatmap"
            brief["chart_decisions"][0]["route"] = "editor_advanced"
            brief["chart_decisions"][0]["parameter_spec"] = get_chart_param_spec("heatmap").brief()
            brief["chart_decisions"][0]["selection_origin"] = "registered_capability_gap"
            brief["chart_decisions"][0]["capability_gap"] = "wizard_has_no_heatmap_matrix_semantics"
            brief["chart_decisions"][0]["widget_id"] = "orders_trend"
            Path(tmp, "artifacts", "dashboard_brief.json").write_text(json.dumps(brief), encoding="utf-8")

            dataset_plan = dl_create_dataset_plan(
                {
                    "name": "dataset_placeholder",
                    "dataset": {"fields": ["order_month", "region", "order_count"]},
                }
            )
            field_plan = dl_create_dataset_field_plan({"name": "order_count", "type": "integer"})
            wizard_plan = dl_create_wizard_chart_plan(
                {
                    "route": "wizard_native",
                    "visualization_id": "geolayer",
                    "workbookId": "workbook_placeholder",
                    "name": "Region map",
                }
            )
            editor_bundle = dl_generate_editor_bundle(
                tmp,
                widget_id="orders_trend",
                dataset_alias="orders_dataset",
                columns=["bucket", "metric", "value", "label"],
                route="editor_advanced",
            )
            payload_plan = dl_build_payload_plan(tmp, workbook_id="workbook_placeholder")
            Path(tmp, "datasets").mkdir()
            Path(tmp, "datasets", "smoke_orders.sql").write_text(
                "SELECT order_month, region, order_count FROM mart.smoke_orders\n",
                encoding="utf-8",
            )
            dashboard_payload_dir = Path(tmp, "artifacts", "dashboard_payloads")
            dashboard_payload_dir.mkdir(parents=True, exist_ok=True)
            Path(dashboard_payload_dir, "smoke.dashboard.payload.json").write_text(
                json.dumps({"dashboardId": "dashboard_placeholder", "tabs": [], "items": []}),
                encoding="utf-8",
            )
            validation = dl_validate_project(tmp)
            safe_apply = dl_create_safe_apply_plan(
                tmp,
                readback_mode="minimal",
                delivery_intent_text="plan only",
            )
            dashboard_entry = {
                "entryId": "dashboard_placeholder",
                "revId": "rev_placeholder",
                "data": {"counter": 1, "salt": "s", "schemeVersion": 8, "tabs": [], "settings": {}},
                "meta": {},
            }
            save_plan = dl_save_object_plan("dashboard", dashboard_entry)
            publish_plan = dl_publish_object_plan("dashboard", dashboard_entry)
            readback = dl_readback_and_report(tmp, dashboard_id="", chart_ids=[], readback_mode="minimal")

            self.assertTrue(dataset_plan["ok"])
            self.assertEqual(dataset_plan["method"], "createDataset")
            self.assertFalse(dataset_plan["execute_now"])
            self.assertFalse(field_plan["ok"])
            self.assertTrue(wizard_plan["ok"])
            self.assertIn("requirements_context", editor_bundle)
            self.assertEqual(validation["status"], "pass", validation)
            self.assertEqual(len(payload_plan["payloads"]), 1)
            self.assertEqual(safe_apply["delivery_intent_decision"]["state"], "plan_only")
            self.assertEqual(save_plan["payload"]["mode"], "save")
            self.assertEqual(publish_plan["payload"]["mode"], "publish")
            self.assertFalse(readback["readback"]["live_readback"])

            catalog = Path(tmp, "docs", "datalens", "implemented_charts.md").read_text(encoding="utf-8")
            relations = Path(tmp, "artifacts", "dashboard_object_relations.json").read_text(encoding="utf-8")
            self.assertIn("orders_trend", catalog)
            self.assertIn("selector_region", relations)


if __name__ == "__main__":
    unittest.main()
