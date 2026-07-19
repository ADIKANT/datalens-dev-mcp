import unittest


class DashboardLayoutContractTests(unittest.TestCase):
    def test_selector_width_planner_uses_percentages_and_targets_94(self):
        from datalens_dev_mcp.pipeline.layout_contract import plan_selector_row_widths, validate_selector_controls

        widths = plan_selector_row_widths(["environment", "schema", "table", "status"])

        self.assertEqual(set(widths), {"environment", "schema", "table", "status"})
        self.assertTrue(all(value.endswith("%") for value in widths.values()))
        self.assertEqual(sum(int(value.removesuffix("%")) for value in widths.values()), 94)
        self.assertTrue(
            validate_selector_controls(
                [{"param": name, "labelPlacement": "left", "width": width} for name, width in widths.items()]
            ).ok
        )

    def test_selector_validation_accepts_under_budget_row(self):
        from datalens_dev_mcp.pipeline.layout_contract import validate_selector_controls

        result = validate_selector_controls([{"param": "env", "labelPlacement": "left", "width": "50%"}])

        self.assertTrue(result.ok, result.issues)

    def test_layout_blueprints_exist_for_dashboard_types(self):
        from datalens_dev_mcp.pipeline.layout_contract import layout_blueprint_for_dashboard_type

        dashboard_types = [
            "overview",
            "self_service",
            "object_management",
            "alerts_mailing",
            "analytical_tool",
            "experiment_report",
            "project_ad_hoc",
        ]
        for dashboard_type in dashboard_types:
            with self.subTest(dashboard_type=dashboard_type):
                blueprint = layout_blueprint_for_dashboard_type(dashboard_type)
                self.assertEqual(blueprint["dashboard_type"], dashboard_type)
                self.assertEqual(blueprint["selector_row_width"], "94%")
                self.assertTrue(blueprint["native_metadata_required"])

    def test_selector_validation_rejects_top_pixel_and_overwide_rows(self):
        from datalens_dev_mcp.pipeline.layout_contract import validate_selector_controls

        result = validate_selector_controls(
            [
                {"param": "env", "labelPlacement": "top", "width": "48%"},
                {"param": "schema", "labelPlacement": "left", "width": "120px"},
                {"param": "table", "labelPlacement": "left", "width": "60%"},
            ]
        )

        self.assertFalse(result.ok)
        self.assertIn("labelPlacement must be left", "\n".join(result.issues))
        self.assertIn("width must be a percentage", "\n".join(result.issues))
        self.assertIn("selector row width total", "\n".join(result.issues))

    def test_dashboard_multi_tab_widget_requires_visible_header_and_chart_ids(self):
        from datalens_dev_mcp.pipeline.layout_contract import validate_dashboard_widget_tabs

        result = validate_dashboard_widget_tabs(
            {
                "data": {
                    "tabs": [
                        {
                            "items": [
                                {
                                    "id": "attribute-check-table",
                                    "type": "widget",
                                    "data": {
                                        "hideTitle": True,
                                        "tabs": [
                                            {"title": "summary", "chartId": "chart_summary"},
                                            {"title": "missing attributes"},
                                        ],
                                    },
                                }
                            ]
                        }
                    ]
                }
            }
        )

        self.assertFalse(result.ok)
        self.assertIn("data.hideTitle must be false", "\n".join(result.issues))
        self.assertIn("chartId is required", "\n".join(result.issues))

    def test_generated_selector_bundle_uses_left_percent_widths(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="selector_demo",
            route="editor_js_control",
            title="Selector Demo",
            param="segment",
            options=["all", "new"],
            family="unknown_family_to_force_fallback",
        )

        controls = bundle["tabs"]["controls.js"]
        self.assertIn("labelPlacement: 'left'", controls)
        self.assertIn("width: '94%'", controls)


if __name__ == "__main__":
    unittest.main()
