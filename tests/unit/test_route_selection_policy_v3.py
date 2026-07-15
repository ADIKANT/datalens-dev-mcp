import unittest


class RouteSelectionPolicyV3Tests(unittest.TestCase):
    def test_wizard_default_and_explicit_js(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v3

        default = select_route_v3("Make a custom chart")
        explicit_js = select_route_v3("Собери на JS")

        self.assertEqual(default.selected_route, "wizard_native")
        self.assertEqual(default.selection_origin, "wizard_first_default")
        self.assertEqual(explicit_js.selected_route, "editor_advanced")
        self.assertEqual(explicit_js.selection_origin, "explicit_user_request")

    def test_explicit_wizard_does_not_silently_fallback_to_js(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v3

        decision = select_route_v3("Собери wizard chart")

        self.assertEqual(decision.status, "approved")
        self.assertEqual(decision.selected_route, "wizard_native")
        self.assertEqual(decision.selection_origin, "explicit_user_request")
        self.assertNotEqual(decision.selected_route, "editor_advanced")
        self.assertTrue(decision.docs_api_evidence)

    def test_table_prefers_native_table_node(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v3

        decision = select_route_v3("Сделай таблицу с bar cells")

        self.assertEqual(decision.selected_route, "wizard_native")
        self.assertEqual(decision.selected_family, "table_node")
        self.assertEqual(decision.visualization_id, "flatTable")

    def test_v4_canonical_selector_and_kpi_routes(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v4

        selector = select_route_v4("Build selector row for Period and Team")
        kpi = select_route_v4("Build KPI indicator")

        self.assertEqual(selector.selected_route, "editor_js_control")
        self.assertEqual(selector.selected_family, "control_node")
        self.assertEqual(kpi.selected_route, "wizard_native")
        self.assertEqual(kpi.selected_family, "kpi_value_only")
        self.assertEqual(kpi.visualization_id, "metric")
        self.assertEqual(kpi.policy, "2026-07-13.route_selection_policy_v5")

    def test_semantic_map_does_not_require_literal_wizard(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v4

        decision = select_route_v4("Build a map of warehouse locations")

        self.assertEqual(decision.status, "approved_with_requirements")
        self.assertEqual(decision.selected_route, "wizard_native")
        self.assertEqual(decision.visualization_id, "geolayer")
        self.assertEqual(decision.selection_origin, "wizard_first_default")
        self.assertIn("validated_geo_evidence", decision.required_evidence)

    def test_existing_wizard_preserves_technology_without_relabeling(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v4

        non_map = select_route_v4(
            "Update it",
            existing_object_type="graph_wizard_node",
            existing_visualization_id="column100p",
        )
        native_map = select_route_v4(
            "Update it",
            existing_object_type="ymap_wizard_node",
            existing_visualization_id="geolayer",
        )

        self.assertEqual(non_map.status, "approved_with_requirements")
        self.assertEqual(non_map.selected_route, "wizard_native")
        self.assertEqual(non_map.visualization_id, "column100p")
        self.assertEqual(non_map.selection_origin, "fresh_saved_readback")
        self.assertEqual(native_map.selected_route, "wizard_native")
        self.assertEqual(native_map.visualization_id, "geolayer")

    def test_datalens_seo_dashboard_url_extracts_canonical_id(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        normalized = normalize_user_request(
            "Review https://datalens.ru/demo000000001-sample-dashboard?tab=demo"
        )

        self.assertEqual(normalized.target_dashboard_id, "demo000000001")
        self.assertEqual(normalized.target_object_type, "dashboard")


if __name__ == "__main__":
    unittest.main()
