import unittest


class DashboardObjectGranularityTests(unittest.TestCase):
    def test_composite_advanced_editor_dashboard_fails(self):
        from datalens_dev_mcp.pipeline.dashboard_object_granularity import validate_dashboard_object_granularity

        result = validate_dashboard_object_granularity(
            {
                "expected_visual_count": 3,
                "objects": [
                    {
                        "object_id": "composite",
                        "object_type": "advanced_editor_chart",
                        "visual_count": 3,
                        "prepare": "<h1>Main</h1><h2>Quality</h2><div class='kpi-card card-grid'></div><table></table>",
                    }
                ],
            }
        )

        self.assertFalse(result.ok)
        self.assertIn("advanced_editor_multiple_visuals", {finding.rule for finding in result.findings})
        self.assertIn("kpi_card_grid_inside_advanced_editor_body", {finding.rule for finding in result.findings})

    def test_separate_object_graph_passes(self):
        from datalens_dev_mcp.pipeline.dashboard_object_granularity import validate_dashboard_object_granularity

        result = validate_dashboard_object_granularity(
            {
                "expected_visual_count": 2,
                "objects": [
                    {"object_id": "kpi", "object_type": "indicator_node"},
                    {"object_id": "table", "object_type": "table_node"},
                    {"object_id": "selector", "object_type": "control_node"},
                ],
                "tabs": [{"items": [{"object_id": "kpi"}, {"object_id": "table"}]}],
            }
        )

        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
