import json
import unittest
from pathlib import Path

from datalens_dev_mcp.api.methods import get_method_schema, is_readonly_method, is_write_method

from datalens_dev_mcp.mcp.tools.rpc import dl_get_api_method_schema


ROOT = Path(__file__).resolve().parents[2]


class ApiSchemaRequestResponseContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / "config" / "datalens_api_operation_policy.json").read_text(encoding="utf-8"))
        cls.schemas = json.loads(
            (ROOT / "schemas" / "datalens-api" / "selected-openapi-schema-refs.json").read_text(encoding="utf-8")
        )
        cls.closed_schemas = json.loads(
            (ROOT / "schemas" / "datalens-api" / "closed-schema-bundle.json").read_text(encoding="utf-8")
        )["schemas"]

    def test_schema_refs_have_hashes_when_present(self):
        for record in self.policy["operations"]:
            with self.subTest(operation=record["operation_id"]):
                request_ref = record["request_schema_ref"]
                response_ref = record["response_schema_ref"]
                if request_ref:
                    self.assertIn(request_ref, self.schemas)
                    self.assertRegex(record["request_schema_hash"], r"^[0-9a-f]{64}$")
                    self.assertRegex(record["request_schema_closure_hash"], r"^[0-9a-f]{64}$")
                    self.assertIn(request_ref, record["request_schema_closure_refs"])
                if response_ref:
                    self.assertIn(response_ref, self.schemas)
                    self.assertRegex(record["response_schema_hash"], r"^[0-9a-f]{64}$")
                    self.assertRegex(record["response_schema_closure_hash"], r"^[0-9a-f]{64}$")
                    self.assertIn(response_ref, record["response_schema_closure_refs"])

    def test_transitive_scope_contracts_are_covered_by_closure_hashes(self):
        policy = {record["method_name"]: record for record in self.policy["operations"]}

        self.assertIn("AuditEntry", policy["getAuditEntriesUpdates"]["response_schema_closure_refs"])
        self.assertIn("EntryScope", policy["getEntriesRelations"]["request_schema_closure_refs"])
        self.assertIn("EntryScope", policy["getEntriesRelations"]["response_schema_closure_refs"])
        self.assertIn("GetWorkbookEntriesEntry", policy["getWorkbookEntries"]["response_schema_closure_refs"])
        self.assertIn("WorkbookTransferNotification", policy["getWorkbookExportStatus"]["response_schema_closure_refs"])
        self.assertIn("WorkbookTransferNotification", policy["getWorkbookImportStatus"]["response_schema_closure_refs"])

    def test_dashboard_and_report_neuro_widget_hide_actions_stays_optional(self):
        for bundle_name, schemas in (("selected", self.schemas), ("closed", self.closed_schemas)):
            collections = {
                "DashboardData": schemas["DashboardData"]["properties"]["tabs"],
                "ReportData": schemas["ReportData"]["properties"]["slideGroups"],
            }
            for schema_name, collection in collections.items():
                with self.subTest(bundle=bundle_name, schema=schema_name):
                    variants = collection["items"]["properties"]["items"]["items"]["oneOf"]
                    neuro_widget = next(
                        variant
                        for variant in variants
                        if variant["properties"]["type"].get("enum") == ["neuro_widget"]
                    )
                    widget_data = neuro_widget["properties"]["data"]
                    self.assertEqual(widget_data["properties"]["hideActions"], {"type": "boolean"})
                    self.assertNotIn("hideActions", widget_data["required"])

    def test_dashboard_and_report_revision_audit_fields_stay_optional(self):
        for bundle_name, schemas in (("selected", self.schemas), ("closed", self.closed_schemas)):
            for schema_name in ("DashboardV1", "ReportV1"):
                with self.subTest(bundle=bundle_name, schema=schema_name):
                    schema = schemas[schema_name]
                    self.assertEqual(schema["properties"]["revUpdatedAt"], {"type": "string"})
                    self.assertEqual(schema["properties"]["revUpdatedBy"], {"type": "string"})
                    self.assertNotIn("revUpdatedAt", schema["required"])
                    self.assertNotIn("revUpdatedBy", schema["required"])

    def test_audit_parent_folder_id_stays_required_nullable(self):
        for bundle_name, schemas in (("selected", self.schemas), ("closed", self.closed_schemas)):
            with self.subTest(bundle=bundle_name):
                audit_entry = schemas["AuditEntry"]
                self.assertEqual(audit_entry["properties"]["parentFolderId"], {"type": ["string", "null"]})
                self.assertIn("parentFolderId", audit_entry["required"])

    def test_runtime_schema_lookup_matches_policy_refs(self):
        policy_by_method = {record["method_name"]: record for record in self.policy["operations"]}

        for method in ("getDashboard", "updateDataset", "validateDataset", "createEditorChart", "createQLChart"):
            with self.subTest(method=method):
                runtime = dl_get_api_method_schema(method)
                policy = policy_by_method[method]
                self.assertEqual(runtime["request_schema_ref"], policy["request_schema_ref"])
                self.assertEqual(runtime["response_schema_ref"], policy["response_schema_ref"])
                self.assertEqual(runtime["path"], policy["path"])

    def test_unknown_operation_returns_explicit_unavailable_shape(self):
        runtime = dl_get_api_method_schema("missingOperationForCoverageTest")

        self.assertEqual(runtime["mode"], "unknown")
        self.assertIn("not in the curated", runtime["description"])

    def test_compute_and_artifact_scope_examples_are_preserved_in_contract_fixtures(self):
        fixture_dir = ROOT / "tests" / "fixtures" / "api_contracts"
        audit = json.loads((fixture_dir / "getAuditEntriesUpdates.json").read_text(encoding="utf-8"))
        relations = json.loads((fixture_dir / "getEntriesRelations.json").read_text(encoding="utf-8"))
        inventory = json.loads((fixture_dir / "getWorkbookEntries.json").read_text(encoding="utf-8"))
        export_status = json.loads((fixture_dir / "getWorkbookExportStatus.json").read_text(encoding="utf-8"))
        import_status = json.loads((fixture_dir / "getWorkbookImportStatus.json").read_text(encoding="utf-8"))

        self.assertEqual(audit["response_payload"]["entries"][0]["scope"], "artifact")
        self.assertEqual(relations["response_payload"]["relations"][0]["scope"], "compute")
        self.assertEqual(inventory["response_payload"]["entries"][0]["scope"], "compute")
        self.assertEqual(export_status["response_payload"]["notifications"][0]["scope"], "compute")
        self.assertEqual(import_status["response_payload"]["notifications"][0]["scope"], "compute")

    def test_readonly_and_reference_only_operations_do_not_drift_into_write_routes(self):
        policy = {record["method_name"]: record for record in self.policy["operations"]}
        supported_readonly = {"batchListMembers", "dlsSuggest", "getPermissions"}
        reference_only = {"deleteFolder", "modifyPermissions", "moveFolderEntry"}

        for method in supported_readonly:
            with self.subTest(method=method):
                schema = get_method_schema(method)
                self.assertEqual(schema["mode"], "readonly")
                self.assertEqual(schema["support_status"], "EXECUTABLE_TOOL_SUPPORTED")
                self.assertEqual(schema["mcp_route"], "read_only")
                self.assertEqual(schema["mcp_tool"], "dl_rpc_readonly")
                self.assertTrue(is_readonly_method(method))
                self.assertFalse(is_write_method(method))
                self.assertEqual(policy[method]["status"], "supported_tool")
                self.assertEqual(policy[method]["owning_mcp_tool"], "dl_rpc_readonly")

        for method in reference_only:
            with self.subTest(method=method):
                schema = get_method_schema(method)
                self.assertEqual(schema["mode"], "forbidden")
                self.assertEqual(schema["support_status"], "READ_ONLY_REFERENCE")
                self.assertEqual(schema["mcp_route"], "forbidden")
                self.assertFalse(schema["mcp_tool"])
                self.assertFalse(is_readonly_method(method))
                self.assertFalse(is_write_method(method))
                self.assertEqual(policy[method]["status"], "readonly_reference")
                self.assertEqual(policy[method]["owning_mcp_tool"], "dl_reference")

    def test_generated_api_source_and_package_resources_have_byte_parity(self):
        pairs = [
            (
                ROOT / "config" / "datalens_api_methods.json",
                ROOT / "src" / "datalens_dev_mcp" / "assets" / "config" / "datalens_api_methods.json",
            ),
            (
                ROOT / "config" / "datalens_api_operation_policy.json",
                ROOT
                / "src"
                / "datalens_dev_mcp"
                / "assets"
                / "config"
                / "datalens_api_operation_policy.json",
            ),
        ]
        package_schema_dir = ROOT / "src" / "datalens_dev_mcp" / "assets" / "schemas" / "datalens-api"
        for source in sorted((ROOT / "schemas" / "datalens-api").glob("*.json")):
            pairs.append((source, package_schema_dir / source.name))

        for source, packaged in pairs:
            with self.subTest(resource=source.name):
                self.assertTrue(packaged.is_file())
                self.assertEqual(packaged.read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
