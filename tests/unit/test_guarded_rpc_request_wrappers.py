import unittest


class GuardedRpcRequestWrapperTests(unittest.TestCase):
    def test_validate_dataset_uses_current_dataset_wrapper(self):
        from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request

        request = compile_guarded_rpc_request(
            "validateDataset",
            {"id": "dataset_1", "fields": [{"guid": "field_1"}]},
            object_type="dataset",
            object_id="dataset_1",
            workbook_id="workbook_1",
            mode="validate",
        )

        self.assertTrue(request["ok"], request["blocked_reasons"])
        self.assertEqual(request["schema_version"], "datalens.delta_v7.guarded_rpc_request.v1")
        self.assertEqual(request["payload"]["datasetId"], "dataset_1")
        self.assertIn("dataset", request["payload"]["data"])
        self.assertEqual(request["mode"], "validate")

    def test_wizard_update_uses_entry_id_template_mode_data_shape(self):
        from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request

        request = compile_guarded_rpc_request(
            "updateWizardChart",
            {"entryId": "chart_1", "revId": "rev_1", "data": {"visualization": "line"}},
            object_type="wizard_chart",
            object_id="chart_1",
            mode="save",
            base_revision="rev_1",
        )

        self.assertTrue(request["ok"], request["blocked_reasons"])
        self.assertEqual(request["payload"]["entryId"], "chart_1")
        self.assertEqual(request["payload"]["template"], "datalens")
        self.assertEqual(request["payload"]["mode"], "save")
        self.assertEqual(request["readback"]["expected_branch"], "saved")

    def test_dashboard_update_strips_readback_only_system_fields(self):
        from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request

        request = compile_guarded_rpc_request(
            "updateDashboard",
            {
                "entry": {
                    "entryId": "dash_1",
                    "revId": "rev_1",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "permissions": {"canEdit": True},
                    "data": {"tabs": []},
                    "meta": {},
                }
            },
            object_type="dashboard",
            object_id="dash_1",
            mode="save",
            base_revision="rev_1",
        )

        self.assertTrue(request["ok"], request["blocked_reasons"])
        self.assertNotIn("createdAt", request["payload"]["entry"])
        self.assertNotIn("permissions", request["payload"]["entry"])
        self.assertEqual(request["payload"]["entry"]["data"], {"tabs": []})

    def test_guarded_compiler_rejects_reference_destructive_and_unknown_methods(self):
        from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request

        cases = (
            ("deleteFolder", {"folderId": "folder_1"}),
            ("modifyPermissions", {"entryId": "entry_1", "permissions": []}),
            ("moveFolderEntry", {"entryId": "entry_1", "folderId": "folder_2"}),
            ("unknownWrite", {"id": "entry_1"}),
        )
        for method, payload in cases:
            with self.subTest(method=method):
                request = compile_guarded_rpc_request(method, payload, base_revision="rev_1")
                self.assertFalse(request["ok"])
                self.assertIn("method_not_allowed_by_guarded_rpc_policy", request["blocked_reasons"])

    def test_guarded_compiler_supports_canonical_non_map_and_map_wizard_creation(self):
        from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request

        non_map = compile_guarded_rpc_request(
            "createWizardChart",
            {"workbookId": "workbook_1", "name": "Bar", "data": {"visualization": {"id": "column100p"}}},
        )
        native_map = compile_guarded_rpc_request(
            "createWizardChart",
            {
                "workbookId": "workbook_1",
                "name": "Map",
                "route": "wizard_map_native",
                "data": {"visualization": {"id": "geolayer"}},
            },
        )

        self.assertTrue(non_map["ok"], non_map["blocked_reasons"])
        self.assertTrue(native_map["ok"], native_map["blocked_reasons"])

    def test_guarded_ql_requires_explicit_route_and_direct_request_provenance(self):
        from datalens_dev_mcp.api.request_compiler import compile_guarded_rpc_request

        payload = {
            "route": "ql_explicit",
            "key": "folder/ql",
            "template": "ql",
            "data": {"query": "SELECT 1"},
        }
        blocked = compile_guarded_rpc_request("createQLChart", payload)
        approved = compile_guarded_rpc_request(
            "createQLChart",
            payload,
            approval_provenance={
                "selection_origin": "explicit_user_request",
                "request_digest": "sha256:fixture",
            },
        )

        self.assertFalse(blocked["ok"])
        self.assertIn("ql_write_requires_explicit_user_request_provenance", blocked["blocked_reasons"])
        self.assertTrue(approved["ok"], approved["blocked_reasons"])


if __name__ == "__main__":
    unittest.main()
