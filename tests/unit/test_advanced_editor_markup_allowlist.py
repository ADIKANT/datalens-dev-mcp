import unittest


class AdvancedEditorMarkupAllowlistTests(unittest.TestCase):
    def test_section_tag_is_blocked(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        result = validate_editor_runtime_contract({"prepare": "return Editor.generateHtml(`<section>Bad</section>`);"})

        self.assertFalse(result["ok"])
        self.assertIn("section_tag", {finding["rule"] for finding in result["findings"]})

    def test_inline_event_handler_is_blocked(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        result = validate_editor_runtime_contract({"prepare": "return Editor.generateHtml(`<div onclick=\"x()\">Bad</div>`);"})

        self.assertFalse(result["ok"])
        self.assertIn("inline_event_handler", {finding["rule"] for finding in result["findings"]})

    def test_table_tag_is_blocked_by_runtime_quality_contract(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        result = validate_editor_runtime_contract({"prepare": "return Editor.generateHtml(`<table><tr><td>A</td></tr></table>`);"})

        self.assertFalse(result["ok"])
        self.assertIn("table_tag", {finding["rule"] for finding in result["findings"]})


if __name__ == "__main__":
    unittest.main()
