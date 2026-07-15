import json
import subprocess
import sys
import unittest
from pathlib import Path

from datalens_dev_mcp.editor.bundle import generate_editor_bundle
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract


ROOT = Path(__file__).resolve().parents[2]


class RendererVisualContractTests(unittest.TestCase):
    def test_generated_bundles_do_not_emit_decorative_css_or_duplicate_title_hints(self):
        for family in ("kpi_value_only", "line_chart", "horizontal_bar"):
            with self.subTest(family=family):
                bundle = generate_editor_bundle(
                    widget_id=family,
                    route="editor_advanced",
                    title=family,
                    family=family,
                )
                joined = "\n".join(str(value) for value in bundle["tabs"].values())

                self.assertNotIn("box-shadow", joined)
                self.assertNotIn("drop-shadow", joined)
                self.assertNotIn('data-id="hint"', joined)
                self.assertNotIn("data.title", joined)
                result = validate_editor_runtime_contract({"tabs": bundle["tabs"]}, source=family, allow_unknown_warnings=True)
                self.assertTrue(result["ok"], json.dumps(result["findings"], indent=2))

    def test_table_bundle_uses_native_bar_contract(self):
        bundle = generate_editor_bundle(
            widget_id="table",
            route="editor_table",
            title="Table",
            family="table_node",
            columns=["name", "value"],
        )
        prepare = bundle["tabs"]["prepare.js"]

        self.assertIn("type: 'bar'", prepare)
        self.assertIn("barColor", prepare)
        self.assertNotRegex(prepare, r"<div[^>]+width\s*:")

    def test_visual_runtime_contract_sweep_passes(self):
        completed = subprocess.run(
            [sys.executable, "scripts/run_visual_runtime_contract_sweep.py", "--strict"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
