import tempfile
import unittest
from pathlib import Path


class ImplementedChartsCatalogTests(unittest.TestCase):
    def test_generation_updates_catalog_and_requirements(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_governance_brief,
            dl_generate_editor_bundle,
            dl_ingest_requirements_markdown,
            dl_start_pipeline,
        )

        with tempfile.TemporaryDirectory() as tmp:
            dl_start_pipeline(tmp, dashboard_name="Catalog")
            dl_ingest_requirements_markdown(
                tmp,
                markdown_text=(
                    "# Catalog Dashboard\n"
                    "- Dataset table: mart.orders\n"
                    "- Connector: analytics-prod\n"
                    "- Field attribute: order_month\n"
                    "- Metric KPI: order_count\n"
                    "- Selector filter control: segment\n"
                    "- Chart visual: line trend\n"
                ),
                source_name="REQ-catalog",
            )
            brief = dl_build_governance_brief(tmp)
            brief["data_contract"]["fields"] = ["order_month", "segment", "order_count"]
            brief["chart_decisions"][0]["family"] = "line_chart"
            brief["chart_decisions"][0]["route"] = "editor_advanced"
            brief["chart_decisions"][0]["widget_id"] = "orders_trend"
            Path(tmp, "artifacts", "dashboard_brief.json").write_text(__import__("json").dumps(brief), encoding="utf-8")

            dl_generate_editor_bundle(tmp, widget_id="orders_trend")

            catalog = Path(tmp, "docs", "datalens", "implemented_charts.md").read_text(encoding="utf-8")
            charts = Path(tmp, "requirements", "charts.md").read_text(encoding="utf-8")
            metrics = Path(tmp, "requirements", "metrics.md").read_text(encoding="utf-8")
            relations = Path(tmp, "requirements", "object_relations.md").read_text(encoding="utf-8")

            self.assertIn("orders_trend", catalog)
            self.assertIn("line_chart", catalog)
            self.assertIn("templates/datalens/advanced_editor/time_series", catalog)
            self.assertIn("order_month", catalog)
            self.assertIn("order_count", catalog)
            self.assertNotIn("selector_segment", catalog)
            self.assertIn("Implemented Chart Catalog", charts)
            self.assertIn("Implemented Metrics And Attributes", metrics)
            self.assertIn("order_count", metrics)
            self.assertIn("Implemented Object Relations", relations)
            self.assertIn("artifacts/dashboard_object_relations.json", relations)

    def test_catalog_resolves_removed_families_to_approved_alternative(self):
        from datalens_dev_mcp.pipeline.implemented_charts_catalog import update_implemented_charts_catalog

        with tempfile.TemporaryDirectory() as tmp:
            relations = {
                "dashboard": {"name": "Conversion"},
                "charts": [
                    {
                        "chart_id": "legacy",
                        "widget_id": "legacy",
                        "family": "radar",
                        "route": "editor_advanced",
                        "dataset_dependencies": ["DATA-001"],
                        "field_dependencies": ["segment", "value"],
                        "calculated_field_dependencies": [],
                    }
                ],
                "selectors": [],
                "datasets": [{"dataset_id": "DATA-001", "fields": ["segment", "value"], "calculated_fields": []}],
            }
            update_implemented_charts_catalog(tmp, relations=relations)
            catalog = Path(tmp, "docs", "datalens", "implemented_charts.md").read_text(encoding="utf-8")

            self.assertNotIn("`radar`", catalog)
            self.assertIn("Known limitations", catalog)

    def test_docs_exist(self):
        for rel in [
            "docs/datalens/implemented_charts.md",
            "docs/datalens/template_family_implementation_matrix.md",
        ]:
            self.assertTrue(Path(rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
