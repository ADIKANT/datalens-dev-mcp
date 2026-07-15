import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AdvancedTemplatesParameterizationTests(unittest.TestCase):
    REQUIRED_COMMENT_BLOCKS = [
        "Source/data contract",
        "Params/config",
        "Prepare/model normalization",
        "Render lifecycle",
        "Layout/scales",
        "Labels/tooltips",
        "Theme tokens",
        "Interactions",
        "Extension points",
    ]

    def test_advanced_prepare_templates_have_required_comment_blocks(self):
        for prepare_path in sorted((ROOT / "templates" / "datalens" / "advanced_editor").glob("*/prepare.js")):
            text = prepare_path.read_text(encoding="utf-8")
            with self.subTest(path=prepare_path):
                for marker in self.REQUIRED_COMMENT_BLOCKS:
                    self.assertIn(marker, text)
                self.assertIn("Editor.wrapFn", text)
                self.assertIn("Editor.generateHtml", text)
                self.assertIn("HOUSE_STYLE", text)
                self.assertNotIn("createQLChart", text)
                self.assertNotIn("d3_node", text)

    def test_every_advanced_template_has_schema_example_and_policy_spec(self):
        from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec

        registry = json.loads((ROOT / "templates" / "datalens" / "standard_chart_templates.json").read_text(encoding="utf-8"))
        for family, spec in registry["families"].items():
            if spec["route"] != "editor_advanced":
                continue
            template_dir = ROOT / spec["template_dir"]
            matrix_spec = get_chart_param_spec(family)
            with self.subTest(family=family):
                self.assertIn(matrix_spec.route, {"wizard_native", "editor_advanced"})
                if matrix_spec.route == "wizard_native":
                    self.assertTrue(matrix_spec.visualization_id)
                else:
                    self.assertTrue(matrix_spec.capability_gap)
                self.assertTrue((template_dir / "schema.json").is_file())
                self.assertTrue((template_dir / "example_input.json").is_file())
                self.assertTrue(matrix_spec.required_parameters)
                self.assertTrue(matrix_spec.raw["visual_constraints"])

    def test_node_syntax_check_for_advanced_prepare_templates(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        for prepare_path in sorted((ROOT / "templates" / "datalens" / "advanced_editor").glob("*/prepare.js")):
            with self.subTest(path=prepare_path):
                result = subprocess.run([node, "-c", str(prepare_path)], cwd=ROOT, check=False, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_generated_bundle_exposes_parameter_spec_and_no_native_title_body_contract(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="orders_trend",
            route="editor_advanced",
            title="Orders Trend",
            family="line_chart",
        )

        self.assertIn("parameter_spec", bundle)
        self.assertEqual(bundle["parameter_spec"]["family"], "line_chart")
        checks = bundle["parameter_spec"]["ask_user_when"] + bundle["parameter_spec"].get("visual_constraints", [])
        self.assertIn("keep_native_dashboard_title_and_hint_outside_chart_body", checks)


if __name__ == "__main__":
    unittest.main()
