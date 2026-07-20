import inspect
import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp import __version__
from datalens_dev_mcp.mcp.tool_registry_policy import (
    HIDDEN_TOOL_CALLS_ENV,
    LEGACY_TOOL_PROFILE_ENV,
    TEST_ONLY_REGISTRY_ENV,
)
from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status
from datalens_dev_mcp.pipeline.context_contracts import PROJECT_CONTEXT_AWARE_TOOLS
from datalens_dev_mcp.server import DEFAULT_TOOL_SURFACE, STANDARD_TOOL_NAMES, TOOLS, JsonRpcServer, list_tools


ROOT = Path(__file__).resolve().parents[2]


class ToolSchemaTests(unittest.TestCase):
    def test_server_version_matches_package_metadata_and_is_not_initial_placeholder(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        server = JsonRpcServer(project_root=".")
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})

        self.assertEqual(__version__, metadata["project"]["version"])
        self.assertEqual(response["result"]["serverInfo"]["version"], __version__)
        self.assertNotEqual(__version__, "0.1.0")

    def test_all_registered_tools_have_explicit_input_schemas(self):
        listed = {tool["name"]: tool for tool in list_tools("all")}
        self.assertEqual(set(listed), set(TOOLS))

        for name, fn in TOOLS.items():
            schema = listed[name]["inputSchema"]
            self.assertEqual(schema["type"], "object", name)
            self.assertFalse(schema["additionalProperties"], name)
            self.assertIn("properties", schema, name)

            expected_params = {
                param_name
                for param_name, param in inspect.signature(fn).parameters.items()
                if param_name != "client"
                and param.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
            }
            if name in PROJECT_CONTEXT_AWARE_TOOLS:
                expected_params.update({"context_ref", "evidence_refs"})
            self.assertEqual(expected_params, set(schema["properties"]), name)
            self.assertLess(len(listed[name]["description"]), 180, name)
            for required in schema.get("required", []):
                self.assertIn(required, schema["properties"], name)

    def test_list_tools_returns_mutation_safe_schema_copies(self):
        first = list_tools()
        original_name = first[0]["name"]
        first[0]["name"] = "poisoned_tool"
        first[0]["inputSchema"]["properties"]["poisoned"] = {"type": "string"}

        second = list_tools()
        restored = next(tool for tool in second if tool["name"] == original_name)

        self.assertNotIn("poisoned_tool", {tool["name"] for tool in second})
        self.assertNotIn("poisoned", restored["inputSchema"]["properties"])
        self.assertEqual({tool["name"] for tool in second}, STANDARD_TOOL_NAMES)

    def test_required_fields_and_enums_are_visible(self):
        listed = {tool["name"]: tool for tool in list_tools("all")}

        workbook_schema = listed["dl_get_workbook_entries"]["inputSchema"]
        self.assertEqual(workbook_schema["required"], ["workbook_id"])
        self.assertIn("workbook_id", workbook_schema["properties"])

        safe_apply_schema = listed["dl_create_safe_apply_plan"]["inputSchema"]
        self.assertEqual(safe_apply_schema["properties"]["readback_mode"]["enum"], ["none", "minimal", "full", "debug"])

        route_schema = listed["dl_generate_editor_bundle"]["inputSchema"]
        self.assertIn("wizard_native", route_schema["properties"]["route"]["enum"])
        self.assertIn("wizard_map_native", route_schema["properties"]["route"]["enum"])
        selector_schema = route_schema["properties"]["selector_contract"]
        self.assertFalse(selector_schema["additionalProperties"])
        self.assertEqual(
            selector_schema["required"],
            ["label", "option_source", "reset_behavior"],
        )
        self.assertEqual(len(selector_schema["oneOf"]), 2)
        dataset_readbacks_schema = route_schema["properties"]["dataset_readbacks"]
        self.assertEqual(dataset_readbacks_schema["type"], "array")
        self.assertEqual(dataset_readbacks_schema["items"]["type"], "object")

    def test_structured_list_annotations_are_not_advertised_as_string_arrays(self):
        listed = {tool["name"]: tool for tool in list_tools()}
        expected_object_arrays = {
            ("dl_validate_source_availability_consumers", "consumers"),
            ("dl_create_safe_apply_plan", "existing_update_actions"),
            ("dl_reconcile_partial_creates", "planned_objects"),
        }
        for tool_name, parameter_name in expected_object_arrays:
            with self.subTest(tool=tool_name, parameter=parameter_name):
                schema = listed[tool_name]["inputSchema"]["properties"][parameter_name]
                self.assertEqual(schema["type"], "array")
                self.assertEqual(schema["items"]["type"], "object")

        maintenance_schema = listed["dl_run_live_maintenance_update"]["inputSchema"]
        maintenance_properties = maintenance_schema["properties"]
        self.assertIn("maintenance_evidence", maintenance_properties)
        self.assertNotIn("safe_apply_execution_evidence", maintenance_properties)
        self.assertNotIn("saved_readback_evidence", maintenance_properties)
        self.assertNotIn("legacy_evidence", maintenance_properties)
        evidence_schema = maintenance_properties["maintenance_evidence"]
        self.assertFalse(evidence_schema["additionalProperties"])
        for parameter_name in ("changed_objects", "safe_apply_actions", "guarded_requests"):
            with self.subTest(tool="dl_run_live_maintenance_update", parameter=parameter_name):
                schema = evidence_schema["properties"][parameter_name]
                self.assertEqual(schema["type"], "array")
                self.assertEqual(schema["items"]["type"], "object")

        union_schema = evidence_schema["properties"]["source_budget_evidence"]
        self.assertEqual(
            union_schema["anyOf"],
            [{"type": "object"}, {"type": "array", "items": {"type": "object"}}],
        )

    def test_live_maintenance_bundle_and_validated_legacy_keywords_share_one_boundary(self):
        from datalens_dev_mcp.mcp.tools import pipeline

        with patch.object(pipeline, "run_live_maintenance_update", return_value={"ok": True}) as run_update:
            bundled = pipeline.dl_run_live_maintenance_update(
                workbook_id="workbook_1",
                maintenance_evidence={
                    "browser_runtime_required": False,
                    "non_rendering_exemption": "No rendering surface is changed.",
                    "safe_apply_actions": [{"method": "updateEditorChart"}],
                },
            )
            bundled_call = run_update.call_args.kwargs
            legacy = pipeline.dl_run_live_maintenance_update(
                workbook_id="workbook_1",
                browser_runtime_required=False,
                non_rendering_exemption="No rendering surface is changed.",
                safe_apply_actions=[{"method": "updateEditorChart"}],
            )
            legacy_call = run_update.call_args.kwargs

        self.assertTrue(bundled["ok"])
        self.assertTrue(legacy["ok"])
        self.assertEqual(bundled_call["browser_runtime_required"], legacy_call["browser_runtime_required"])
        self.assertEqual(bundled_call["non_rendering_exemption"], legacy_call["non_rendering_exemption"])
        self.assertEqual(bundled_call["safe_apply_actions"], legacy_call["safe_apply_actions"])
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            pipeline.dl_run_live_maintenance_update(maintenance_evidence={"unknown_evidence": {}})
        with self.assertRaisesRegex(ValueError, "supplied twice"):
            pipeline.dl_run_live_maintenance_update(
                maintenance_evidence={"browser_runtime_required": True},
                browser_runtime_required=True,
            )
        with self.assertRaisesRegex(ValueError, "array of objects"):
            pipeline.dl_run_live_maintenance_update(
                maintenance_evidence={"safe_apply_actions": ["not-an-object"]},
            )

    def test_tool_list_has_no_legacy_sync_or_corpus_tools(self):
        payload = json.dumps(list_tools("all"), ensure_ascii=False)
        for forbidden in ("corpus", "sync_private", "parity", "codex-plugins", "plugin cache"):
            self.assertNotIn(forbidden, payload)

    def test_default_tools_list_uses_standard_surface_without_profile_selection(self):
        server = JsonRpcServer(project_root=".")
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        result = response["result"]
        names = {tool["name"] for tool in result["tools"]}

        self.assertEqual(result["tool_surface"], DEFAULT_TOOL_SURFACE)
        self.assertEqual(names, STANDARD_TOOL_NAMES)
        self.assertNotIn("profile", result)
        self.assertNotIn("dl_rpc_readonly", names)
        self.assertNotIn("dl_rpc_expert", names)
        self.assertNotIn("dl_load_project_context", names)
        self.assertNotIn("dl_update_project_memory", names)
        self.assertNotIn("dl_create_dataset_field_plan", names)
        self.assertNotIn("dl_create_calculated_field_plan", names)
        self.assertLessEqual(len(names), 40)
        for required in (
            "dl_runtime_status",
            "dl_auth_probe",
            "dl_get_workbook_entries",
            "dl_get_entries_relations",
            "dl_read_object",
            "dl_snapshot_dashboard",
            "dl_list_api_methods",
            "dl_get_api_method_schema",
            "dl_plan_object_create",
            "dl_plan_object_update",
            "dl_validate_object",
            "dl_validate_project",
            "dl_plan_guarded_dataset_update",
            "dl_plan_dashboard_tab_update",
            "dl_create_safe_apply_plan",
            "dl_execute_safe_apply",
            "dl_create_publish_from_saved_plan",
            "dl_readback_and_report",
            "dl_build_validation_evidence_report",
            "dl_detect_project_live_workflows",
            "dl_run_project_live_dry_run",
            "dl_run_project_live_apply",
        ):
            self.assertIn(required, names)

        core_bytes = len(json.dumps(result, separators=(",", ":")).encode("utf-8"))
        all_bytes = len(json.dumps({"tools": list_tools("all")}, separators=(",", ":")).encode("utf-8"))
        self.assertLessEqual(core_bytes, 25_000)
        self.assertLess(core_bytes, all_bytes)

        listed = {tool["name"]: tool for tool in result["tools"]}
        project_schema = listed["dl_build_payload_plan"]["inputSchema"]["properties"]
        self.assertEqual(project_schema["context_ref"]["type"], "object")
        self.assertEqual(project_schema["evidence_refs"]["items"]["type"], "object")

    def test_standard_write_plan_schemas_do_not_advertise_forbidden_routes(self):
        listed = {tool["name"]: tool for tool in list_tools()}
        payload = json.dumps({"tools": list(listed.values())}, ensure_ascii=False)

        for forbidden in ("d3_node", "d3_gravity_node", "graph_ql_node", '"move"'):
            self.assertNotIn(forbidden, payload)

        for tool_name in ("dl_plan_object_create", "dl_plan_object_update", "dl_validate_object"):
            enum = listed[tool_name]["inputSchema"]["properties"]["object_type"]["enum"]
            self.assertIn("ql_chart", enum)
            for forbidden in ("permission", "workbook_permission", "workbook_entry"):
                self.assertNotIn(forbidden, enum)
        self.assertIn("ql_chart", listed["dl_read_object"]["inputSchema"]["properties"]["object_type"]["enum"])
        self.assertNotIn("deleteQLChart", payload)

    def test_profile_membership_and_all_compatibility(self):
        profiles = {profile: {tool["name"] for tool in list_tools(profile)} for profile in ("dashboard", "dq", "dataset", "expert")}

        self.assertEqual({tool["name"] for tool in list_tools("all")}, set(TOOLS))
        self.assertIn("dl_update_dashboard_plan", profiles["dashboard"])
        self.assertIn("dl_build_selector_wiring_summary", profiles["dashboard"])
        self.assertIn("dl_classify_dq_reconciliation", profiles["dq"])
        self.assertIn("dl_get_dataset", profiles["dataset"])
        self.assertIn("dl_rpc_expert", profiles["expert"])
        self.assertNotIn("dl_rpc_expert", {tool["name"] for tool in list_tools("core")})

    def test_unknown_internal_profile_fails_clearly(self):
        with self.assertRaises(ValueError) as raised:
            list_tools("unknown")

        self.assertIn("unknown MCP tool profile", str(raised.exception))

    def test_fresh_default_server_exposes_quality_roadmap_and_order_sequences(self):
        server = JsonRpcServer(project_root=".")
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}

        quality_sequence = [
            "dl_runtime_status",
            "dl_auth_probe",
            "dl_get_workbook_entries",
            "dl_snapshot_dashboard",
            "dl_read_object",
            "dl_validate_editor_runtime_contract",
            "dl_validate_project",
            "dl_build_payload_plan",
            "dl_plan_object_update",
            "dl_create_safe_apply_plan",
            "dl_execute_safe_apply",
            "dl_readback_and_report",
            "dl_build_validation_evidence_report",
        ]
        roadmap_sequence = [
            "dl_get_entries_relations",
            "dl_read_object",
            "dl_diagnose",
            "dl_plan_dashboard_tab_update",
            "dl_plan_object_update",
            "dl_create_publish_from_saved_plan",
            "dl_classify_source_error",
        ]
        order_sequence = [
            "dl_validate_object",
            "dl_plan_guarded_dataset_update",
            "dl_detect_project_live_workflows",
            "dl_plan_project_manifest",
            "dl_plan_project_live_workflow",
            "dl_run_project_live_dry_run",
            "dl_run_project_live_apply",
            "dl_read_project_live_summary",
        ]
        for sequence in (quality_sequence, roadmap_sequence, order_sequence):
            with self.subTest(sequence=sequence[0]):
                self.assertLessEqual(set(sequence), names)

        self.assertIn("dl_generate_editor_bundle", names)
        self.assertNotIn("dl_compile_guarded_rpc_request", names)

    def test_missing_required_runtime_input_is_structured_tool_error(self):
        server = JsonRpcServer(project_root=".")
        result = server._call_tool({"name": "dl_get_workbook_entries", "arguments": {}})
        body = json.loads(result["content"][0]["text"])

        self.assertTrue(result["isError"])
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["category"], "missing_input")
        self.assertEqual(body["tool"], "dl_get_workbook_entries")

    def test_generic_tool_exception_uses_shared_redaction(self):
        secret = "Bearer " + "abcdefghijklmnop" + "qrstuvwxyz123456"

        def explode():
            raise RuntimeError(f"upstream failed with {secret}")

        with patch.dict(TOOLS, {"dl_runtime_status": explode}):
            server = JsonRpcServer(project_root=".")
            result = server._call_tool({"name": "dl_runtime_status", "arguments": {}})
            body = json.loads(result["content"][0]["text"])

        self.assertTrue(result["isError"])
        self.assertEqual(body["error"]["category"], "unknown_runtime_error")
        self.assertIn("<redacted>", body["error"]["message"])
        self.assertNotIn(secret, body["error"]["message"])

    def test_hidden_tools_are_not_callable_through_standard_json_rpc_dispatch(self):
        server = JsonRpcServer(project_root=".")

        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "dl_rpc_expert", "arguments": {"method": "deleteDashboard", "payload": {"dashboardId": "dash_1"}}},
            }
        )

        self.assertIn("error", response)
        self.assertIn("not exposed on the standard MCP tool surface", response["error"]["message"])

    def test_hidden_tool_env_alone_is_ignored_without_test_only_marker(self):
        with patch.dict(os.environ, {HIDDEN_TOOL_CALLS_ENV: "1", TEST_ONLY_REGISTRY_ENV: ""}, clear=False):
            server = JsonRpcServer(project_root=".")
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "dl_build_runtime_verification_plan",
                        "arguments": {"workbook_id": "wb_test"},
                    },
                }
            )

        self.assertIn("error", response)
        self.assertIn("not exposed on the standard MCP tool surface", response["error"]["message"])

    def test_hidden_tool_calls_require_explicit_test_only_marker(self):
        with patch.dict(os.environ, {HIDDEN_TOOL_CALLS_ENV: "1", TEST_ONLY_REGISTRY_ENV: "1"}, clear=False):
            server = JsonRpcServer(project_root=".")
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "dl_build_runtime_verification_plan",
                        "arguments": {"workbook_id": "wb_test", "run_id": "run_test"},
                    },
                }
            )

        self.assertNotIn("error", response)
        result = response["result"]
        self.assertFalse(result["isError"])
        body = json.loads(result["content"][0]["text"])
        self.assertEqual(body["workbook_id"], "wb_test")
        self.assertEqual(body["run_id"], "run_test")

    def test_runtime_status_does_not_expose_registry_test_controls(self):
        with patch.dict(
            os.environ,
            {HIDDEN_TOOL_CALLS_ENV: "1", TEST_ONLY_REGISTRY_ENV: "", LEGACY_TOOL_PROFILE_ENV: "expert"},
            clear=False,
        ):
            env_only = dl_runtime_status(project_root=".")
        self.assertNotIn("tool_registry", env_only["runtime_env"])
        self.assertNotIn("hidden_tool", json.dumps(env_only, ensure_ascii=False))

        with patch.dict(
            os.environ,
            {HIDDEN_TOOL_CALLS_ENV: "1", TEST_ONLY_REGISTRY_ENV: "1"},
            clear=False,
        ):
            enabled = dl_runtime_status(project_root=".")
        self.assertNotIn("tool_registry", enabled["runtime_env"])
        self.assertNotIn("hidden_tool", json.dumps(enabled, ensure_ascii=False))

    def test_missing_live_credentials_are_structured_auth_block(self):
        env = os.environ.copy()
        for key in ("DATALENS_ENV_FILE", "DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "DATALENS_ORG_ID"):
            env[key] = ""
        with patch.dict(os.environ, env, clear=True):
            server = JsonRpcServer(project_root=".")
            result = server._call_tool({"name": "dl_list_workbooks", "arguments": {"page": 1, "page_size": 1}})
        body = json.loads(result["content"][0]["text"])

        self.assertTrue(result["isError"])
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["category"], "auth_failure")
        self.assertIn("BLOCKED_LIVE_CREDENTIALS", body["error"]["message"])


if __name__ == "__main__":
    unittest.main()
