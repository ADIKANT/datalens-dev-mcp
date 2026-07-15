import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ChartParamMatrixTests(unittest.TestCase):
    def setUp(self):
        self.matrix_path = ROOT / "config" / "datalens_chart_param_matrix.json"
        self.matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        self.families = self.matrix["families"]

    def test_matrix_covers_every_approved_family_and_native_map_route(self):
        from datalens_dev_mcp.pipeline.chart_taxonomy import APPROVED_CHARTS, REMOVED_CHARTS

        self.assertLessEqual(set(APPROVED_CHARTS), set(self.families))
        self.assertIn("native_map_geo_widget", self.families)
        self.assertFalse(set(REMOVED_CHARTS).intersection(self.families))

    def test_matrix_specs_have_required_parameter_contract_fields(self):
        required_keys = {
            "route",
            "intent",
            "data_shape",
            "required_parameters",
            "optional_parameters",
            "default_sorting",
            "labels_axes_gridlines",
            "color_strategy",
            "value_formatting",
            "interaction_expectations",
            "ask_user_when",
            "fallback_family",
            "visual_constraints",
        }
        for family, spec in self.families.items():
            with self.subTest(family=family):
                self.assertLessEqual(required_keys, set(spec))
                self.assertTrue(spec["required_parameters"])
                self.assertTrue(spec["ask_user_when"])
                self.assertTrue(spec["visual_constraints"])

    def test_matrix_routes_are_allowlisted_and_do_not_expose_forbidden_chart_creation(self):
        routes = {spec["route"] for spec in self.families.values()}
        self.assertLessEqual(
            routes,
            {"wizard_native", "editor_advanced", "editor_table", "editor_markdown", "editor_js_control"},
        )
        self.assertFalse(any(spec["route"] == "ql_explicit" for spec in self.families.values()))
        self.assertIn("ql_explicit", self.matrix["allowed_creation_routes"])
        self.assertEqual(self.matrix["route_policy_ref"], "config/route_selection_policy_v5.json")

    def test_standard_template_registry_matches_matrix_route_and_template(self):
        registry = json.loads((ROOT / "templates" / "datalens" / "standard_chart_templates.json").read_text(encoding="utf-8"))
        for family, template_spec in registry["families"].items():
            with self.subTest(family=family):
                matrix_spec = self.families[family]
                if matrix_spec["route"].startswith("editor_"):
                    self.assertEqual(matrix_spec["route"], template_spec["route"])
                    self.assertEqual(matrix_spec["template_dir"], template_spec["template_dir"])
                else:
                    self.assertEqual(matrix_spec["route"], "wizard_native")
                    self.assertEqual(
                        matrix_spec["template_dir"],
                        "templates/datalens/wizard/canonical_templates.json",
                    )

    def test_runtime_loader_exposes_family_specs_to_governance_and_templates(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec, route_for_chart_family
        from datalens_dev_mcp.pipeline.governance import build_governance_brief

        self.assertEqual(route_for_chart_family("line_chart"), "wizard_native")
        self.assertEqual(get_chart_param_spec("line_chart").visualization_id, "line")
        self.assertEqual(get_chart_param_spec("native_map_geo_widget").route, "wizard_native")
        self.assertEqual(get_chart_param_spec("native_map_geo_widget").visualization_id, "geolayer")

        brief = build_governance_brief(requirements_text="Show a weekly trend of completed orders.")
        decision = brief["chart_decisions"][0]
        self.assertEqual(decision["family"], "line_chart")
        self.assertIn("parameter_spec", decision)
        self.assertEqual(decision["parameter_spec"]["route"], "wizard_native")

        bundle = generate_editor_bundle(
            widget_id="trend_widget",
            route="editor_advanced",
            title="Completed Orders",
            family="line_chart",
        )
        self.assertIn("parameter_spec", bundle)
        self.assertEqual(bundle["parameter_spec"]["family"], "line_chart")


if __name__ == "__main__":
    unittest.main()
