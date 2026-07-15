import unittest


class EditorMetaShapeAgainstApiTests(unittest.TestCase):
    def test_title_inside_editor_meta_is_blocked(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        result = validate_editor_runtime_contract({"entry": {"data": {"meta": "{\"title\":\"Bad\"}"}}})

        self.assertFalse(result["ok"])
        self.assertIn("unsupported_editor_meta_title", {finding["rule"] for finding in result["findings"]})


if __name__ == "__main__":
    unittest.main()
