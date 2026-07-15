import unittest
from pathlib import Path


class AdvancedEditorContractTests(unittest.TestCase):
    def test_contract_docs_define_allowed_methods_and_lifecycle(self):
        contract = Path("docs/datalens/advanced_editor_contract.md").read_text(encoding="utf-8")
        methods = Path("docs/datalens/advanced_editor_methods.md").read_text(encoding="utf-8")

        for method in [
            "Editor.generateHtml",
            "Editor.getLoadedData",
            "Editor.getParam",
            "Editor.getParams",
            "Editor.wrapFn",
        ]:
            self.assertIn(method, methods)

        self.assertIn("render: Editor.wrapFn({", contract)
        self.assertIn("args: [model]", contract)
        self.assertIn("fn: function(options, data)", contract)
        self.assertIn("return Editor.generateHtml", contract)
        self.assertIn("must not be wrapped", contract)
        self.assertIn("fallback behavior", contract)

    def test_validator_rejects_unavailable_methods_and_bad_render_export(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_advanced_editor_js

        result = validate_advanced_editor_js(
            """
            const render = Editor.generateHtml('<div>bad</div>');
            Editor.getData();
            module.exports = {render};
            """
        )

        self.assertFalse(result.ok)
        self.assertIn("unavailable Editor method getData", "\n".join(result.issues))
        self.assertIn("render must be exported as Editor.wrapFn", "\n".join(result.issues))

    def test_standard_advanced_templates_follow_contract(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_advanced_editor_js

        for prepare_path in Path("templates/datalens/advanced_editor").glob("*/prepare.js"):
            with self.subTest(path=prepare_path):
                result = validate_advanced_editor_js(prepare_path.read_text(encoding="utf-8"), source=str(prepare_path))
                self.assertTrue(result.ok, result.issues)

    def test_fallback_advanced_bundle_uses_safe_wrapfn_shape(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_advanced_editor_js

        bundle = generate_editor_bundle(
            widget_id="fallback_advanced",
            route="editor_advanced",
            title="Fallback Advanced",
            family="unknown_family_to_force_fallback",
        )
        prepare = bundle["tabs"]["prepare.js"]

        self.assertIn("render: Editor.wrapFn({", prepare)
        self.assertIn("args: [model]", prepare)
        self.assertIn("fn: function(options, data)", prepare)
        self.assertNotIn("render: Editor.generateHtml", prepare)
        self.assertTrue(validate_advanced_editor_js(prepare).ok)


if __name__ == "__main__":
    unittest.main()
