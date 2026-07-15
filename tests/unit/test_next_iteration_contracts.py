import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PublicApiContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(
            (ROOT / "config" / "datalens_api_methods.json").read_text(encoding="utf-8")
        )

    def test_catalog_covers_compiled_api_inventory(self):
        self.assertEqual(self.catalog["operation_count"], 88)
        self.assertEqual(self.catalog["required_api_header_version"], "2")
        methods = {method["method"]: method for method in self.catalog["methods"]}
        for method in (
            "createConnection",
            "updateConnection",
            "createDataset",
            "updateDataset",
            "validateDataset",
            "createWizardChart",
            "updateWizardChart",
            "createEditorChart",
            "updateEditorChart",
            "getEntriesRelations",
        ):
            with self.subTest(method=method):
                self.assertIn(method, methods)

    def test_ql_is_explicit_and_delete_is_closed(self):
        from datalens_dev_mcp.api.methods import get_method_schema, is_write_method

        self.assertEqual(get_method_schema("createQLChart")["mode"], "guarded_write")
        self.assertTrue(is_write_method("createQLChart"))
        self.assertEqual(get_method_schema("updateQLChart")["mode"], "guarded_write")
        self.assertEqual(get_method_schema("deleteQLChart")["mode"], "forbidden")
        self.assertFalse(is_write_method("deleteQLChart"))

    def test_compiled_schema_bundle_preserves_update_wrappers(self):
        bundle = json.loads(
            (ROOT / "schemas" / "datalens-api" / "closed-schema-bundle.json").read_text(encoding="utf-8")
        )
        index = json.loads(
            (ROOT / "schemas" / "datalens-api" / "operation-schema-index.json").read_text(encoding="utf-8")
        )
        self.assertEqual(bundle["missing_refs"], [])
        self.assertEqual(index["updateDataset"]["request_schema_ref"], "UpdateDatasetRequest")
        self.assertEqual(index["validateDataset"]["request_schema_ref"], "ValidateDatasetRequest")
        self.assertEqual(index["updateConnection"]["request_schema_ref"], "UpdateConnectionRequest")


class PublicRequirementsContractTests(unittest.TestCase):
    def test_dashboard_type_and_requirements_templates_are_packaged(self):
        model = json.loads(
            (ROOT / "config" / "datalens_dashboard_type_model.json").read_text(encoding="utf-8")
        )
        self.assertIn("overview", model["dashboard_types"])
        self.assertIn("self_service", model["dashboard_types"])
        self.assertIn("project-authored requirements workflow", model["source_trace"])

        for rel in (
            "templates/requirements/dashboard_map.md",
            "templates/requirements/dashboard_canvas.md",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("Dashboard", text)
            self.assertIn("Project-authored", text)

    def test_native_title_standard_is_documented(self):
        text = (ROOT / "docs" / "datalens" / "native_titles_hints.md").read_text(encoding="utf-8")
        self.assertIn("hideTitle=false", text)
        self.assertIn("enableHint=true", text)


if __name__ == "__main__":
    unittest.main()
