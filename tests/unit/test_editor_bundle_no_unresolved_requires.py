import unittest

from datalens_dev_mcp.editor.bundle import generate_editor_bundle


class EditorBundleNoUnresolvedRequiresTests(unittest.TestCase):
    def test_standard_advanced_bundles_inline_shared_helpers(self):
        for family in ("kpi_value_only", "line_chart", "horizontal_bar"):
            with self.subTest(family=family):
                bundle = generate_editor_bundle(
                    widget_id=family,
                    route="editor_advanced",
                    title=family.replace("_", " ").title(),
                    family=family,
                )
                prepare = bundle["tabs"]["prepare.js"]

                self.assertNotIn("require('../_shared/", prepare)
                self.assertIn("function normalizeRows", prepare)
                self.assertIn("const HOUSE_STYLE", prepare)

    def test_template_sources_and_packaged_assets_do_not_contain_shared_requires(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for base in (root / "templates", root / "src" / "datalens_dev_mcp" / "assets" / "templates"):
            for path in base.rglob("*.js"):
                text = path.read_text(encoding="utf-8")
                if "require('../_shared/" in text:
                    offenders.append(path.relative_to(root).as_posix())

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
