import unittest


class RouteContractTests(unittest.TestCase):
    def test_closed_route_set_and_entry_types(self):
        from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT

        self.assertEqual(
            set(ROUTE_CONTRACT.routes),
            {
                "editor_advanced",
                "editor_table",
                "editor_markdown",
                "editor_js_control",
                "wizard_native",
                "ql_explicit",
            },
        )
        self.assertEqual(ROUTE_CONTRACT.routes["editor_advanced"].entry_type, "advanced-chart_node")
        self.assertEqual(ROUTE_CONTRACT.routes["editor_table"].entry_type, "table_node")
        self.assertEqual(ROUTE_CONTRACT.routes["editor_markdown"].entry_type, "markdown_node")
        self.assertEqual(ROUTE_CONTRACT.routes["editor_js_control"].entry_type, "control_node")
        self.assertEqual(ROUTE_CONTRACT.routes["wizard_native"].entry_type, "wizard_chart")
        self.assertEqual(ROUTE_CONTRACT.routes["ql_explicit"].entry_type, "ql_chart")

    def test_forbidden_terms_are_rejected(self):
        from datalens_dev_mcp.validators.route_validator import validate_route_payload

        payload = {
            "route": "editor_advanced",
            "entry_type": "advanced-chart_node",
            "tabs": {"prepare.js": "const x = 'deleteQLChart and d3_node';"},
        }

        result = validate_route_payload(payload)

        self.assertFalse(result.ok)
        self.assertTrue(any("deleteQLChart" in issue for issue in result.issues))
        self.assertTrue(any("d3_node" in issue for issue in result.issues))

    def test_map_route_requires_geo_evidence(self):
        from datalens_dev_mcp.validators.route_validator import validate_route_payload

        result = validate_route_payload(
            {
                "route": "wizard_map_native",
                "entry_type": "wizard_chart",
                "visualization_id": "geolayer",
                "geo_evidence": {"status": "inferred", "kind": "city_name"},
            }
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("geo_evidence" in issue for issue in result.issues))

    def test_non_map_wizard_does_not_require_geo_and_ql_requires_provenance(self):
        from datalens_dev_mcp.validators.route_validator import validate_route_payload

        wizard = validate_route_payload(
            {"route": "wizard_native", "entry_type": "wizard_chart", "visualization_id": "line"}
        )
        ql = validate_route_payload({"route": "ql_explicit", "entry_type": "ql_chart"})

        self.assertTrue(wizard.ok, wizard.issues)
        self.assertFalse(ql.ok)
        self.assertTrue(any("explicit_user_request" in issue for issue in ql.issues))


if __name__ == "__main__":
    unittest.main()
