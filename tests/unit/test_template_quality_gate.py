import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TemplateQualityGateTests(unittest.TestCase):
    COMMENT_MARKERS = (
        "Source/data contract",
        "Params/config",
        "Prepare/model normalization",
        "Render lifecycle",
        "Theme tokens",
        "Interactions",
    )

    def test_quality_gate_doc_exists(self):
        text = (ROOT / "docs" / "datalens" / "template_quality_gate.md").read_text(encoding="utf-8")
        self.assertIn("Chart creation is limited", text)
        self.assertIn("QL create/update may appear only", text)
        self.assertIn("node -c", text)

    def test_registry_routes_are_approved_and_template_backed(self):
        registry = json.loads((ROOT / "templates" / "datalens" / "standard_chart_templates.json").read_text(encoding="utf-8"))
        approved_routes = {"editor_advanced", "editor_table", "editor_markdown", "editor_js_control"}

        for family, spec in registry["families"].items():
            with self.subTest(family=family):
                self.assertIn(spec["route"], approved_routes)
                template_dir = ROOT / spec["template_dir"]
                self.assertTrue(template_dir.is_dir())
                for required in spec["required_files"]:
                    self.assertTrue((template_dir / required).is_file(), f"{family}: {required}")

    def test_all_canonical_wizard_templates_are_creation_supported(self):
        registry = json.loads((ROOT / "templates" / "datalens" / "wizard" / "wizard_template_registry.json").read_text(encoding="utf-8"))

        supported = [name for name, spec in registry["templates"].items() if spec.get("creation_supported")]
        self.assertEqual(len(supported), 16)
        self.assertEqual(registry["canonical_route"], "wizard_native")
        self.assertEqual(registry["compatibility_aliases"]["wizard_map_native"], "geolayer")
        for name, spec in registry["templates"].items():
            self.assertTrue(spec["creation_supported"], name)
            self.assertEqual(spec["visualization_id"], name)
            self.assertTrue(spec["semantic_families"])

    def test_route_native_templates_have_contract_comments(self):
        files = [
            ROOT / "templates" / "datalens" / "editor_table" / "table_node" / "prepare.js",
            ROOT / "templates" / "datalens" / "editor_js_control" / "selector" / "controls.js",
            ROOT / "templates" / "datalens" / "editor_markdown" / "markdown_block" / "prepare.js",
            ROOT / "templates" / "editor_advanced" / "prepare.js",
            ROOT / "templates" / "editor_table" / "prepare.js",
            ROOT / "templates" / "editor_js_control" / "controls.js",
            ROOT / "templates" / "editor_markdown" / "prepare.js",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for marker in self.COMMENT_MARKERS:
                    self.assertIn(marker, text)
                self.assertNotIn("createQLChart", text)
                self.assertNotIn("d3_node", text)

    def test_theme_tokens_cover_light_dark_and_css_variables(self):
        for path in [
            ROOT / "templates" / "advanced" / "style-tokens.js",
            ROOT / "templates" / "datalens" / "advanced_editor" / "_shared" / "style_tokens.js",
        ]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("light", text)
                self.assertIn("dark", text)
                self.assertIn("var(--g-color", text)
                self.assertIn("HOUSE_STYLE", text)

    def test_removed_and_unknown_chart_requests_do_not_create_new_routes(self):
        from datalens_dev_mcp.pipeline.chart_taxonomy import REMOVED_CHARTS
        from datalens_dev_mcp.pipeline.object_routing import route_datalens_operation

        registry = json.loads((ROOT / "templates" / "datalens" / "standard_chart_templates.json").read_text(encoding="utf-8"))
        families = set(registry["families"])
        self.assertFalse(set(REMOVED_CHARTS).intersection(families))

        unknown = route_datalens_operation(requirements_text="Make a custom violin chart.")
        self.assertEqual(unknown["status"], "blocked_question")
        self.assertIn("question", unknown)
        self.assertNotIn("ql", unknown["route"].lower())

    def test_js_templates_pass_syntax_check_when_node_is_available(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        for path in sorted((ROOT / "templates").rglob("*.js")):
            with self.subTest(path=path):
                result = subprocess.run([node, "-c", str(path)], cwd=ROOT, text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
