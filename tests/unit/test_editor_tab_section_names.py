import unittest


class EditorTabSectionNamesTests(unittest.TestCase):
    def test_metaon_tab_is_blocked(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        result = validate_editor_runtime_contract({"entry": {"data": {"metaon": "{}"}}})

        self.assertFalse(result["ok"])
        self.assertIn("editor_metaon_tab", {finding["rule"] for finding in result["findings"]})


if __name__ == "__main__":
    unittest.main()
