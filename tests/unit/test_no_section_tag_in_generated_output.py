import unittest


class NoSectionTagInGeneratedOutputTests(unittest.TestCase):
    def test_fallback_generated_advanced_editor_uses_allowed_markup(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        bundle = generate_editor_bundle(widget_id="fallback", route="editor_advanced", title="Fallback")
        joined = "\n".join(bundle["tabs"].values())
        result = validate_editor_runtime_contract({"tabs": bundle["tabs"]}, allow_unknown_warnings=True)

        self.assertNotIn("<section", joined)
        self.assertTrue(result["ok"], result["findings"])


if __name__ == "__main__":
    unittest.main()
