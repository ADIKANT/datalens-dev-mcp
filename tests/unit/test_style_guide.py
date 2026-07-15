import json
import unittest
from pathlib import Path


REQUIRED_TOKENS = [
    "dashboard_background",
    "card_background",
    "text_primary",
    "text_secondary",
    "text_muted",
    "border",
    "grid_line",
    "tooltip_background",
    "tooltip_text",
    "accent",
    "warning",
    "error",
    "success",
    "neutral_palette",
    "chart_categorical_palette",
    "chart_sequential_palette",
    "table_header_background",
    "table_row_background",
    "selector_label_text",
]


class StyleGuideTests(unittest.TestCase):
    def test_style_guide_config_defines_light_and_dark_tokens(self):
        config = json.loads(Path("config/datalens_style_guide.json").read_text(encoding="utf-8"))

        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                tokens = config["themes"][theme]
                for token in REQUIRED_TOKENS:
                    self.assertIn(token, tokens)

    def test_template_style_tokens_mirror_theme_config_shape(self):
        text = Path("templates/datalens/advanced_editor/_shared/style_tokens.js").read_text(encoding="utf-8")

        self.assertIn("STYLE_GUIDE", text)
        self.assertIn("light", text)
        self.assertIn("dark", text)
        self.assertIn("chart_categorical_palette", text)
        self.assertIn("table_header_background", text)

    def test_table_node_template_uses_gravity_theme_variables(self):
        text = Path("templates/datalens/editor_table/table_node/prepare.js").read_text(encoding="utf-8")

        for token in [
            "var(--g-color-text-primary",
            "var(--g-color-text-secondary",
            "var(--g-color-base-background",
            "var(--g-color-base-neutral-light",
        ]:
            self.assertIn(token, text)
        for light_only in ("#F7F9FC", "#FDECEC", "#ECF7EF", "#FFF7E0"):
            self.assertNotIn(light_only, text)

    def test_style_docs_record_governance_flow_and_dags_rule(self):
        guide = Path("docs/datalens/style_guide.md").read_text(encoding="utf-8")

        self.assertIn("style guide -> template params -> generated chart code", guide)
        self.assertIn("DAGS Checker", guide)
        self.assertIn("DataLens/Gravity CSS variables", guide)


if __name__ == "__main__":
    unittest.main()
