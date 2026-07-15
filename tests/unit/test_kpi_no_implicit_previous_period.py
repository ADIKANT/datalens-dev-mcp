import unittest
from pathlib import Path

from datalens_dev_mcp.editor.bundle import generate_editor_bundle


ROOT = Path(__file__).resolve().parents[2]
STALE_TOKENS = [
    "previous" + "_value",
    "previous" + "_period",
    "previous" + "Period",
    "period" + "_bucket",
    "delta" + "_pct",
]


class KpiNoImplicitPreviousPeriodTests(unittest.TestCase):
    def test_kpi_template_schema_and_sources_use_explicit_comparator_fields(self):
        paths = [
            ROOT / "templates" / "datalens" / "advanced_editor" / "kpi_card" / "sources.js",
            ROOT / "templates" / "datalens" / "advanced_editor" / "kpi_card" / "schema.json",
            ROOT
            / "src"
            / "datalens_dev_mcp"
            / "assets"
            / "templates"
            / "datalens"
            / "advanced_editor"
            / "kpi_card"
            / "sources.js",
            ROOT
            / "src"
            / "datalens_dev_mcp"
            / "assets"
            / "templates"
            / "datalens"
            / "advanced_editor"
            / "kpi_card"
            / "schema.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                for token in STALE_TOKENS:
                    self.assertNotIn(token, text)
                self.assertIn("comparator_value", text)
                self.assertIn("comparator_label", text)

    def test_generated_kpi_value_only_does_not_require_comparator(self):
        bundle = generate_editor_bundle(
            widget_id="kpi",
            route="editor_advanced",
            title="KPI",
            family="kpi_value_only",
        )
        joined = "\n".join(str(value) for value in bundle["tabs"].values())

        for token in STALE_TOKENS:
            self.assertNotIn(token, joined)
        self.assertIn("const SHOW_DELTA = false;", joined)

    def test_generated_kpi_explicit_comparator_uses_comparator_fields(self):
        bundle = generate_editor_bundle(
            widget_id="kpi_delta",
            route="editor_advanced",
            title="KPI Delta",
            family="kpi_value_delta",
        )
        joined = "\n".join(str(value) for value in bundle["tabs"].values())

        self.assertIn("comparator_value", joined)
        self.assertIn("comparator_label", joined)
        for token in STALE_TOKENS:
            self.assertNotIn(token, joined)


if __name__ == "__main__":
    unittest.main()
