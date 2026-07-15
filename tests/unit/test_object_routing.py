import json
import unittest
from pathlib import Path


class ObjectRoutingTests(unittest.TestCase):
    def test_map_requests_route_to_wizard_native_not_advanced(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(
            requirements_text="Build a geo map by region with order count.",
            dataset_schema={"fields": [{"name": "region"}, {"name": "orders"}]},
            required_fields=["region", "orders"],
        )

        self.assertEqual(decision["operation_kind"], "wizard_native_chart")
        self.assertEqual(decision["route"], "wizard_native")
        self.assertEqual(decision["visualization_id"], "geolayer")
        self.assertNotEqual(decision["route"], "editor_advanced")
        self.assertEqual(decision["field_validation"]["status"], "validated")

    def test_dataset_connector_and_dashboard_relation_are_first_class_routes(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        cases = {
            "create connector for the reporting database": ("connector_operation", "connector"),
            "add dataset calculated field and aggregation": ("dataset_operation", "dataset"),
            "update selector relation between widgets": ("dashboard_relation_operation", "dashboard_relation"),
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                decision = route_datalens_operation(requirements_text=text)
                self.assertEqual((decision["operation_kind"], decision["route"]), expected)

    def test_chart_field_validation_blocks_missing_dataset_fields(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(
            requirements_text="Create trend chart for orders by month.",
            dataset_schema={"fields": [{"name": "month"}]},
            required_fields=["month", "orders"],
        )

        self.assertEqual(decision["status"], "blocked_missing_fields")
        self.assertEqual(decision["field_validation"]["missing_fields"], ["orders"])

    def test_routing_model_schema_config_and_docs_exist(self):
        expected_paths = [
            "config/datalens_routing_model.json",
            "docs/datalens/routing_model.md",
            "docs/datalens/wizard_charts.md",
            "docs/datalens/datasets_connectors_fields.md",
            "docs/datalens/chart_selection_decision_matrix.md",
            "schemas/wizard-chart-config.schema.json",
            "schemas/connector-config.schema.json",
            "schemas/dataset-config.schema.json",
            "schemas/field-config.schema.json",
            "schemas/calculated-field-config.schema.json",
            "schemas/measure-dimension-metadata.schema.json",
            "schemas/aggregation-config.schema.json",
        ]
        for rel in expected_paths:
            with self.subTest(path=rel):
                self.assertTrue(Path(rel).is_file(), f"{rel} is missing")

        routing = json.loads(Path("config/datalens_routing_model.json").read_text(encoding="utf-8"))
        self.assertIn("wizard_native_chart", routing["operation_routes"])
        self.assertIn("dataset_operation", routing["operation_routes"])
        self.assertIn("connector_operation", routing["operation_routes"])


if __name__ == "__main__":
    unittest.main()
