import unittest


class ChartRoutingWizardJsOnlyTests(unittest.TestCase):
    def test_ambiguous_chart_request_asks_targeted_question(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(requirements_text="Make a chart.")

        self.assertEqual(decision["status"], "blocked_question")
        self.assertIn("question", decision)
        self.assertNotIn("ql", decision["route"].lower())

    def test_direct_ql_request_uses_explicit_only_route(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(requirements_text="Create a QL chart from the existing query.")

        self.assertEqual(decision["status"], "approved_with_requirements")
        self.assertEqual(decision["operation_kind"], "ql_explicit_chart")
        self.assertEqual(decision["route"], "ql_explicit")
        self.assertEqual(decision["selection_origin"], "explicit_user_request")
        self.assertIn("explicit_payload_or_fresh_saved_ql_seed", decision["required_before"])

    def test_removed_chart_request_routes_to_approved_alternative(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(requirements_text="Use a lollipop chart for epic ranking.")

        self.assertEqual(decision["status"], "approved_alternative")
        self.assertEqual(decision["family"], "horizontal_bar")
        self.assertEqual(decision["route"], "wizard_native")
        self.assertEqual(decision["visualization_id"], "bar")

    def test_manual_review_removed_chart_blocks_with_question(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(requirements_text="Use a slope chart for type open counts.")

        self.assertEqual(decision["status"], "blocked_question")
        self.assertEqual(decision["family"], "line_chart")
        self.assertIn("question", decision)

    def test_maps_tables_kpis_comparison_and_time_series_routes(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        cases = {
            "Map orders by region": ("wizard_native", "native_map_geo_widget", "geolayer"),
            "Self-service detail table with filters": ("wizard_native", "table_node", "flatTable"),
            "KPI metric with delta": ("wizard_native", "kpi_value_delta", "metric"),
            "Top categories by revenue": ("wizard_native", "horizontal_bar", "bar"),
            "Weekly trend of active users": ("wizard_native", "line_chart", "line"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                decision = route_datalens_operation(requirements_text=text)
                self.assertEqual(
                    (decision["route"], decision["family"], decision["visualization_id"]),
                    expected,
                )
                self.assertNotIn("ql", decision["route"].lower())
                if decision["family"] != "native_map_geo_widget":
                    self.assertIn("parameter_spec", decision)

    def test_registered_capability_gap_selects_javascript_before_transport(self):
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        decision = route_datalens_operation(requirements_text="Build a heatmap by weekday and hour")

        self.assertEqual(decision["route"], "editor_advanced")
        self.assertEqual(decision["selection_origin"], "registered_capability_gap")
        self.assertEqual(decision["capability_gap"], "wizard_has_no_heatmap_matrix_semantics")


if __name__ == "__main__":
    unittest.main()
