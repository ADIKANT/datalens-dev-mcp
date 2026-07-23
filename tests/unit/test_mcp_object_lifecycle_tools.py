import json
import tempfile
import unittest
from pathlib import Path


REQUIRED_TOOLS = {
    "dl_probe_auth",
    "dl_read_object",
    "dl_validate_object_payload",
    "dl_plan_object_create",
    "dl_plan_object_update",
    "dl_validate_object",
    "dl_plan_publish_from_saved",
    "dl_list_related_objects",
    "dl_get_dataset_schema",
    "dl_create_editor_chart_plan",
    "dl_update_editor_chart_plan",
    "dl_create_wizard_chart_plan",
    "dl_update_wizard_chart_plan",
    "dl_create_dashboard_plan",
    "dl_update_dashboard_plan",
    "dl_create_connector_plan",
    "dl_update_connector_plan",
    "dl_create_dataset_plan",
    "dl_update_dataset_plan",
    "dl_plan_guarded_dataset_update",
    "dl_plan_dashboard_tab_update",
    "dl_save_object_plan",
    "dl_publish_object_plan",
}
UNSUPPORTED_SCHEMA_ONLY_TOOLS = {
    "dl_create_dataset_field_plan",
    "dl_update_dataset_field_plan",
    "dl_create_calculated_field_plan",
    "dl_update_calculated_field_plan",
}


class FakeClient:
    def rpc(self, method, payload):
        return {"method": method, "payload": payload, "fields": [{"name": "segment"}, {"name": "value"}]}


class OversizedReadClient:
    def rpc(self, method, payload):
        return {
            "datasetId": payload.get("datasetId", "dataset_1"),
            "revId": "rev_1",
            "fields": [
                {
                    "name": f"field_{index}",
                    "guid": f"guid_{index}",
                    "formula": "SUM([value]) " + ("x" * 120),
                }
                for index in range(80)
            ],
            "sources": [{"sql": "SELECT " + ("x" * 4_000)}],
        }


class FailingReadClient:
    def rpc(self, method, payload):
        raise RuntimeError("synthetic read failure " + ("x" * 5_000))


def compact_chars(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


class McpObjectLifecycleToolTests(unittest.TestCase):
    def test_server_lists_object_lifecycle_tools_without_sync_tools(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"] for tool in list_tools("all")}
        default_tools = {tool["name"] for tool in list_tools()}
        all_tools = {tool["name"] for tool in list_tools("all")}
        self.assertTrue(REQUIRED_TOOLS.issubset(tools), sorted(REQUIRED_TOOLS - tools))
        self.assertFalse(UNSUPPORTED_SCHEMA_ONLY_TOOLS & default_tools)
        self.assertTrue(UNSUPPORTED_SCHEMA_ONLY_TOOLS.issubset(all_tools))
        self.assertFalse(any("sync_private_corpus" in item or "cache_sync" in item for item in default_tools))

    def test_guarded_write_tools_return_plans_not_execution(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_create_editor_chart_plan,
            dl_publish_object_plan,
            dl_save_object_plan,
        )

        create = dl_create_editor_chart_plan(
            {"workbookId": "workbook_1", "name": "Chart", "data": {"tabs": {}}}
        )
        dashboard_data = {"counter": 1, "salt": "s", "schemeVersion": 8, "tabs": [], "settings": {}}
        dashboard_entry = {"entryId": "dash_1", "revId": "rev_1", "data": dashboard_data, "meta": {}}
        save = dl_save_object_plan("dashboard", dashboard_entry)
        publish = dl_publish_object_plan("dashboard", dashboard_entry)

        self.assertTrue(create["ok"])
        self.assertEqual(create["method"], "createEditorChart")
        self.assertFalse(create["execute_now"])
        self.assertNotIn("mode", create["payload"])
        self.assertEqual(save["payload"]["mode"], "save")
        self.assertEqual(publish["payload"]["mode"], "publish")

    def test_unavailable_and_unsafe_methods_return_structured_errors(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_create_calculated_field_plan,
            dl_create_dataset_plan,
            dl_plan_object_create,
            dl_create_wizard_chart_plan,
            dl_validate_object_payload,
        )

        dataset_plan = dl_create_dataset_plan(
            {"workbookId": "workbook_1", "dataset": {"sources": []}, "name": "Example"}
        )
        ql_blocked = dl_plan_object_create("ql_chart", {"entry": {"data": {}}})
        unavailable = dl_create_calculated_field_plan({"name": "ratio"})
        unsafe = dl_validate_object_payload("dashboard", {"password": "secret"}, operation="update")
        unsupported = dl_create_wizard_chart_plan({"chart_type": "unknown-internal-token"})

        self.assertTrue(dataset_plan["ok"])
        self.assertEqual(dataset_plan["method"], "createDataset")
        self.assertEqual(ql_blocked["error"]["category"], "ql_explicit_route_required")
        self.assertEqual(unavailable["error"]["category"], "unavailable_api_method")
        self.assertFalse(unavailable["implemented"])
        self.assertEqual(unsafe["error"]["category"], "unsafe_sensitive_input")
        self.assertEqual(unsupported["error"]["category"], "unsupported_chart_type")

    def test_explicit_ql_create_and_update_use_generic_lifecycle(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_object_create, dl_plan_object_update

        create = dl_plan_object_create(
            "ql_chart",
            {
                "route": "ql_explicit",
                "key": "folder/ql",
                "template": "ql",
                "data": {"query": "SELECT 1"},
            },
            delivery_intent_text="create this QL chart",
        )
        update = dl_plan_object_update(
            "ql_chart",
            {
                "route": "ql_explicit",
                "branch": "saved",
                "entryId": "ql_fixture",
                "revId": "rev_fixture",
                "template": "ql",
                "data": {"query": "SELECT 2"},
            },
            source_adapter="saved_entry",
            delivery_intent_text="update this QL chart",
        )

        self.assertTrue(create["ok"], create)
        self.assertEqual(create["method"], "createQLChart")
        self.assertTrue(update["ok"], update)
        self.assertEqual(update["method"], "updateQLChart")

    def test_generic_lifecycle_adapters_block_ambiguous_dataset_readbacks(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_object_update, dl_validate_object

        exact = dl_plan_object_update("dataset", {"datasetId": "ds_1", "data": {"dataset": {"fields": []}}})
        raw_readback = {"datasetId": "ds_1", "revId": "rev_1", "fields": [{"name": "region", "guid": "region_g"}]}
        blocked = dl_plan_object_update("dataset", raw_readback)
        adapted = dl_plan_object_update("dataset", raw_readback, source_adapter="rpc_readback_envelope")
        summary = dl_plan_object_update("dataset", {"summary": {"identity": {"id": "ds_1"}}})
        validate = dl_validate_object("dataset", raw_readback, source_adapter="rpc_readback_envelope")

        self.assertTrue(exact["ok"])
        self.assertEqual(exact["source_adapter"], "canonical_request_payload")
        self.assertEqual(exact["payload"]["datasetId"], "ds_1")
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["error"]["category"], "explicit_adapter_required")
        self.assertTrue(adapted["ok"])
        self.assertEqual(adapted["source_adapter"], "rpc_readback_envelope")
        self.assertIn("dataset", adapted["payload"]["data"])
        self.assertNotIn("dataset", adapted["payload"])
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["error"]["category"], "summary_readback_not_mutation_source")
        self.assertTrue(validate["ok"])
        self.assertEqual(validate["method"], "validateDataset")
        self.assertFalse(validate["validation_result"]["executed"])

    def test_connection_is_read_only_unless_connector_route_is_explicit(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_object_update, dl_read_object

        read = dl_read_object("connection", "conn_1", client=FakeClient())
        connection_update = dl_plan_object_update("connection", {"connectionId": "conn_1", "data": {}})
        connector_update = dl_plan_object_update("connector", {"connectionId": "conn_1", "data": {}})

        self.assertTrue(read["ok"])
        self.assertEqual(read["method"], "getConnection")
        self.assertFalse(connection_update["ok"])
        self.assertEqual(connection_update["object_type"], "connection")
        self.assertEqual(connection_update["error"]["category"], "unavailable_api_method")
        self.assertEqual(connection_update["lifecycle_semantics"]["write_object_type"], "connector")
        self.assertTrue(connector_update["ok"], connector_update)
        self.assertEqual(connector_update["object_type"], "connector")
        self.assertEqual(connector_update["method"], "updateConnection")

    def test_lifecycle_adapter_rejects_nested_rpc_envelope_left_in_payload(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_object_update

        malformed = {
            "result": {
                "datasetId": "ds_1",
                "data": {
                    "dataset": {
                        "result": {
                            "datasetId": "ds_1",
                            "fields": [{"name": "region"}],
                        }
                    }
                },
            }
        }

        result = dl_plan_object_update("dataset", malformed, source_adapter="rpc_readback_envelope")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["category"], "malformed_readback_envelope")

    def test_generic_lifecycle_blocks_permission_move_and_compiles_artifact_sources(self):
        import json
        import tempfile
        from pathlib import Path

        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_object_create, dl_plan_object_update

        folder = dl_plan_object_create("folder", {"key": "/shared/core-correctness"})
        permission = dl_plan_object_update(
            "permission",
            {
                "entryId": "entry_1",
                "body": {"diff": {"added": {"acl_view": [{"subject": "user:test"}]}}},
            },
        )
        move = dl_plan_object_update(
            "workbook_entry",
            {"entryId": "entry_1", "destination": "/shared/target", "name": "Entry"},
            lifecycle_operation="move",
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "dashboard.json"
            artifact.write_text(
                json.dumps({"entryId": "dash_1", "data": {"tabs": []}, "meta": {}}),
                encoding="utf-8",
            )
            dashboard = dl_plan_object_update(
                "dashboard",
                {"artifact_path": str(artifact)},
                source_adapter="artifact_path",
            )

        self.assertTrue(folder["ok"])
        self.assertEqual(folder["method"], "createFolder")
        self.assertNotIn("mode", folder["payload"])
        self.assertFalse(permission["ok"])
        self.assertEqual(permission["error"]["category"], "blocked_by_explicit_policy")
        self.assertFalse(move["ok"])
        self.assertEqual(move["error"]["category"], "blocked_by_explicit_policy")
        self.assertTrue(dashboard["ok"])
        self.assertEqual(dashboard["source_adapter"], "artifact_path")
        self.assertEqual(dashboard["payload"]["entry"]["entryId"], "dash_1")

    def test_read_probe_relations_and_dataset_schema_support_fake_client(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_get_dataset_schema,
            dl_list_related_objects,
            dl_probe_auth,
            dl_read_object,
        )

        probe = dl_probe_auth(client=FakeClient())
        read = dl_read_object("dataset", "dataset_1", client=FakeClient())
        relations = dl_list_related_objects(["entry_1"], client=FakeClient())
        schema = dl_get_dataset_schema(dataset_id="dataset_1", required_fields=["segment", "missing"], client=FakeClient())

        self.assertTrue(probe["ok"])
        self.assertEqual(read["method"], "getDataset")
        self.assertEqual(relations["method"], "getEntriesRelations")
        self.assertEqual(schema["field_validation"]["status"], "blocked_missing_fields")
        self.assertEqual(schema["field_validation"]["missing_fields"], ["missing"])

    def test_read_object_composes_envelope_inside_requested_budget(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_read_object

        stable_keys = {
            "ok",
            "response_mode",
            "requested_response_mode",
            "summary_kind",
            "summary",
            "full_response",
            "artifact",
            "method",
            "object_type",
            "object_id",
            "branch",
            "contract",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for response_mode in ("summary", "structure", "full", "artifact"):
                for budget in (800, 1_000, 2_000):
                    with self.subTest(response_mode=response_mode, budget=budget):
                        result = dl_read_object(
                            "dataset",
                            "dataset_1",
                            response_mode=response_mode,
                            inline_char_budget=budget,
                            project_root=tmp,
                            run_id=f"budget-{response_mode}-{budget}",
                            client=OversizedReadClient(),
                        )

                        self.assertTrue(result["ok"], result)
                        self.assertLessEqual(compact_chars(result), budget)
                        self.assertEqual(set(result), stable_keys)
                        self.assertEqual(result["method"], "getDataset")
                        self.assertEqual(result["object_type"], "dataset")
                        self.assertEqual(result["object_id"], "dataset_1")
                        self.assertEqual(result["branch"], "")
                        self.assertEqual(
                            result["contract"]["schema_version"],
                            "2026-06-25.object_read_registry.v1",
                        )
                        self.assertTrue(result["contract"]["truncated"])
                        self.assertTrue(Path(result["artifact"]["path"]).is_file())

    def test_read_object_preserves_full_contract_when_budget_allows(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_read_object
        from datalens_dev_mcp.server import list_tools

        result = dl_read_object(
            "dataset",
            "dataset_1",
            inline_char_budget=20_000,
            client=FakeClient(),
        )

        self.assertTrue(result["ok"], result)
        self.assertLessEqual(compact_chars(result), 20_000)
        self.assertEqual(result["contract"]["read_method"], "getDataset")
        self.assertIn("method_schema", result["contract"])
        self.assertNotIn("truncated", result["contract"])
        schema = next(tool for tool in list_tools() if tool["name"] == "dl_read_object")["inputSchema"]
        self.assertEqual(schema["properties"]["inline_char_budget"]["minimum"], 800)

    def test_read_object_minimum_budget_covers_every_readable_registered_type(self):
        from datalens_dev_mcp.mcp.object_registry import object_read_contract, object_type_registry
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_read_object

        with tempfile.TemporaryDirectory() as tmp:
            for object_type in object_type_registry()["object_types"]:
                contract = object_read_contract(object_type)
                if not contract or not contract.read_method:
                    continue
                with self.subTest(object_type=object_type):
                    result = dl_read_object(
                        object_type,
                        "fixture-object-id-1234567890",
                        branch="published",
                        inline_char_budget=800,
                        project_root=tmp,
                        client=OversizedReadClient(),
                    )
                    self.assertTrue(result["ok"], result)
                    self.assertLessEqual(compact_chars(result), 800)

    def test_read_object_error_and_unsupported_paths_respect_supported_budgets(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_read_object

        for budget in (800, 1_000, 2_000):
            cases = (
                dl_read_object("calculated_field", "field_1", inline_char_budget=budget),
                dl_read_object("unsupported_fixture", "entry_1", inline_char_budget=budget),
                dl_read_object("dataset", "dataset_1", inline_char_budget=budget, client=FailingReadClient()),
            )
            for result in cases:
                with self.subTest(budget=budget, category=result["error"]["category"]):
                    self.assertFalse(result["ok"])
                    self.assertLessEqual(compact_chars(result), budget)

        invalid = dl_read_object("dataset", "dataset_1", inline_char_budget=799, client=FakeClient())
        self.assertEqual(invalid["error"]["category"], "invalid_input")
        invalid_mode = dl_read_object(
            "dataset",
            "dataset_1",
            response_mode="unsupported_mode",
            inline_char_budget=800,
            client=FakeClient(),
        )
        self.assertEqual(invalid_mode["error"]["category"], "invalid_input")
        self.assertLessEqual(compact_chars(invalid_mode), 800)

    def test_guarded_dataset_update_validate_only_does_not_plan_update(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_guarded_dataset_update

        current = {
            "datasetId": "ds_1",
            "revId": "rev_current",
            "fields": [
                {"name": "linked_issue", "guid": "linked_issue_cd_ui9r"},
                {"name": "issue_count", "guid": "issue_count_p10zx"},
            ],
        }
        proposed = {
            "datasetId": "ds_1",
            "revId": "rev_current",
            "fields": [
                {"name": "linked_issue", "guid": "linked_issue_cd_ui9r", "calc": "lower(linked_issue)"},
                {"name": "issue_count", "guid": "issue_count_p10zx"},
            ],
        }

        plan = dl_plan_guarded_dataset_update("ds_1", current, proposed)

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["mode"], "validate_only")
        self.assertEqual(plan["validate_method"], "validateDataset")
        self.assertTrue(plan["publish_separate"])
        self.assertNotIn("updateDataset", {step["method"] for step in plan["action_sequence"]})
        self.assertEqual(plan["guid_report"]["changed_field_guids"], [])

    def test_guarded_dataset_update_apply_preserves_guids_and_detects_broken_chart_refs(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_guarded_dataset_update

        current = {
            "revId": "rev_current",
            "fields": [
                {"name": "linked_issue", "guid": "linked_issue_cd_ui9r"},
                {"name": "issue_count", "guid": "issue_count_p10zx"},
            ]
        }
        proposed = {
            "fields": [
                {"name": "linked_issue", "guid": "linked_issue_cd_ui9r"},
                {"name": "issue_count", "guid": "issue_count_p10zx"},
            ]
        }
        chart_payloads = [{"chartId": "chart_1", "encoding": {"fieldGuid": "linked_issue_cd_ui9r"}}]

        plan = dl_plan_guarded_dataset_update(
            "ds_1",
            current,
            proposed,
            affected_chart_payloads=chart_payloads,
            validate_only=False,
            delivery_intent_text="update this dataset",
        )

        self.assertTrue(plan["ok"])
        self.assertIn("updateDataset", {step["method"] for step in plan["action_sequence"]})
        self.assertTrue(plan["preserve_field_guids"])
        self.assertEqual(plan["guid_report"]["broken_chart_guid_references"], [])

        broken = dl_plan_guarded_dataset_update(
            "ds_1",
            current,
            {"fields": [{"name": "linked_issue", "guid": "different_guid"}]},
            affected_chart_payloads=chart_payloads,
            validate_only=False,
            delivery_intent_text="update this dataset",
        )

        self.assertFalse(broken["ok"])
        self.assertEqual(broken["error"]["category"], "guarded_write_blocked")
        self.assertTrue(broken["guid_report"]["broken_chart_guid_references"])

    def test_guarded_dataset_update_validates_embedded_calculated_fields(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_guarded_dataset_update

        current = {
            "datasetId": "ds_1",
            "revId": "rev_current",
            "fields": [{"name": "amount", "guid": "amount_guid"}],
        }
        valid = dl_plan_guarded_dataset_update(
            "ds_1",
            current,
            {
                "datasetId": "ds_1",
                "revId": "rev_current",
                "fields": [
                    {"name": "amount", "guid": "amount_guid"},
                    {"name": "amount_total", "guid": "amount_total_guid", "formula": "SUM([amount])"},
                ],
            },
        )
        invalid = dl_plan_guarded_dataset_update(
            "ds_1",
            current,
            {
                "datasetId": "ds_1",
                "revId": "rev_current",
                "fields": [
                    {"name": "a", "guid": "a_guid", "formula": "[b] + 1"},
                    {"name": "b", "guid": "b_guid", "formula": "[a] + 1"},
                    {"name": "broken", "guid": "broken_guid", "formula": "SUM([missing])"},
                ],
            },
        )

        self.assertTrue(valid["calculated_field_report"]["ok"], valid["calculated_field_report"])
        self.assertFalse(invalid["ok"])
        categories = {item["category"] for item in invalid["calculated_field_report"]["issues"]}
        self.assertIn("unknown_field_reference", categories)
        self.assertIn("calculated_field_cycle", categories)
        self.assertFalse(invalid["calculated_field_report"]["standalone_api_used"])

    def test_dashboard_tab_append_preserves_existing_tabs_and_metadata(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_dashboard_tab_update

        current = {
            "entryId": "dash_1",
            "meta": {"title": "Legacy title", "hints": {"legacy": True}},
            "data": {
                "tabs": [
                    {"id": "overview", "widgets": [{"id": "w1"}]},
                    {"id": "details", "widgets": [{"id": "w2"}]},
                ]
            },
        }
        tab = {"id": "dq", "widgets": [{"id": "w3"}]}

        plan = dl_plan_dashboard_tab_update(current, tab)

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["changed_paths"], ["$.data.tabs[2]"])
        self.assertEqual(plan["proposed_dashboard"]["data"]["tabs"][:2], current["data"]["tabs"])
        self.assertEqual(plan["proposed_dashboard"]["meta"], current["meta"])
        self.assertFalse(plan["force_legacy_title_hint_metadata"])
        self.assertTrue(plan["publish_separate"])

    def test_publish_remains_separate_from_save_plans(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_publish_object_plan, dl_update_wizard_chart_plan

        save = dl_update_wizard_chart_plan(
            {
                "route": "wizard_native",
                "branch": "saved",
                "entryId": "chart_1",
                "revId": "rev_1",
                "data": {"visualization": {"id": "geolayer"}},
            },
            mode="save",
            source_adapter="saved_entry",
        )
        publish = dl_publish_object_plan(
            "wizard_chart",
            {
                "route": "wizard_native",
                "branch": "saved",
                "entryId": "chart_1",
                "revId": "rev_1",
                "data": {"visualization": {"id": "geolayer"}},
            },
        )

        self.assertTrue(save["ok"], save)
        self.assertEqual(save["payload"]["mode"], "save")
        self.assertTrue(save["publish_separate"])
        self.assertTrue(publish["ok"], publish)
        self.assertEqual(publish["payload"]["mode"], "publish")
        self.assertFalse(publish["publish_separate"])

    def test_editor_live_validation_request_reports_static_applicability(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_validate_object

        class NoRpcClient:
            def rpc(self, method, payload):
                raise AssertionError(f"unexpected RPC: {method} {payload}")

        result = dl_validate_object(
            "control_node",
            {
                "entry": {
                    "entryId": "selector_synthetic",
                    "revId": "rev_synthetic",
                    "data": {
                        "meta": "module.exports = {};",
                        "params": "module.exports = {};",
                        "sources": "module.exports = {};",
                        "controls": "module.exports = {controls: []};",
                        "prepare": "module.exports = {};",
                    },
                }
            },
            execute_validation=True,
            client=NoRpcClient(),
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["validation_result"]["executed"])
        self.assertEqual(
            result["validation_result"]["applicability"],
            "static_validation_only",
        )

    def test_docs_exist(self):
        from pathlib import Path

        for rel in [
            "docs/mcp/tools.md",
            "docs/mcp/datalens_object_lifecycle.md",
            "docs/mcp/response_contracts.md",
        ]:
            with self.subTest(rel=rel):
                self.assertTrue(Path(rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
