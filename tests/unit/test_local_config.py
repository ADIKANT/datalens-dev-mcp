import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from datalens_dev_mcp.local_config import apply_tool_defaults, load_local_config, sanitize_local_config
from datalens_dev_mcp.validators.artifact_validator import validate_schema_file


ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def patched_env(values):
    old_values = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


class LocalConfigTests(unittest.TestCase):
    def test_example_config_loads_with_safe_defaults(self):
        config = load_local_config(ROOT / "config" / "datalens_mcp.local.example.json", project_root=ROOT)

        self.assertEqual(config["defaults"]["workbook_id"], "<WORKBOOK_ID>")
        self.assertEqual(config["schema_version"], "2026-07-15.datalens_mcp_local_config.v2")
        self.assertEqual(config["execution"]["default"], "follow_user_request")
        self.assertTrue(config["execution"]["writes"])
        self.assertTrue(config["execution"]["save"])
        self.assertTrue(config["execution"]["publish"])
        self.assertTrue(config["execution"]["delete_requires_confirmation"])
        self.assertEqual(config["readback"]["mode"], "minimal")
        self.assertNotIn("mcp", config)
        self.assertEqual(config["validation"]["strictness"], "strict")
        self.assertTrue(config["safe_apply"]["require_safe_apply_plan"])
        self.assertTrue(config["safe_apply"]["require_readback_after_save"])
        self.assertFalse(config["live_testing"]["run_live_tests_by_default"])
        self.assertEqual(config["api_defaults"]["request_interval_sec"], 0.15)
        self.assertEqual(
            config["routing"]["chart_creation_routes"],
            ["wizard_native", "advanced_editor_js", "ql_explicit"],
        )
        self.assertEqual(config["routing"]["ql_behavior"], "explicit_user_request_only")
        self.assertEqual(config["selectors"]["label_placement"], "left")
        self.assertEqual(config["selectors"]["row_width_percent"], 96)
        self.assertEqual(config["selectors"]["default_selector_width_percent"], 24)

    def test_env_override_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "defaults": {"workbook_id": "wb_live", "project_workspace_path": "/tmp/dl-project"},
                        "readback": {"mode": "debug", "justification": "temporary debug run"},
                    }
                ),
                encoding="utf-8",
            )
            with patched_env({"DATALENS_MCP_LOCAL_CONFIG": str(config_path)}):
                config = load_local_config(project_root=ROOT)

        self.assertEqual(config["defaults"]["workbook_id"], "wb_live")
        self.assertEqual(config["defaults"]["project_workspace_path"], "/tmp/dl-project")
        self.assertEqual(config["readback"]["mode"], "debug")
        self.assertTrue(config["_meta"]["loaded_from_file"])

    def test_invalid_routing_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bad.json"
            config_path.write_text(json.dumps({"routing": {"chart_creation_routes": ["ql_chart_creation"]}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_local_config(config_path, project_root=ROOT)

    def test_legacy_map_only_local_config_is_migrated_in_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "legacy-routing.json"
            config_path.write_text(
                json.dumps(
                    {
                        "routing": {
                            "chart_creation_routes": ["wizard_map_native", "advanced_editor_js"],
                            "wizard_map_native": {"enabled": True, "requires_geo_evidence": True},
                            "ql_behavior": "reference_only",
                            "forbidden_routes": [
                                "ql_chart_creation",
                                "non_map_wizard_chart_creation",
                                "native_first_fallback",
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = load_local_config(config_path, project_root=ROOT)

        self.assertEqual(
            config["routing"]["chart_creation_routes"],
            ["wizard_native", "advanced_editor_js", "ql_explicit"],
        )
        self.assertEqual(config["routing"]["ql_behavior"], "explicit_user_request_only")
        self.assertEqual(config["routing"]["wizard_map_native_alias"]["visualization_id"], "geolayer")
        self.assertNotIn("non_map_wizard_chart_creation", config["routing"]["forbidden_routes"])
        self.assertTrue(config["_meta"]["compatibility_migrations"])

    def test_invalid_readback_and_write_defaults_are_rejected(self):
        invalid_configs = [
            {"readback": {"mode": "invalid"}},
            {"readback": {"mode": "none", "justification": ""}},
            {"execution": {"writes": False}},
            {"execution": {"save": False}},
            {"execution": {"publish": False}},
            {"execution": {"delete_requires_confirmation": False}},
            {"safe_apply": {"require_fresh_read": False}},
            {"live_testing": {"run_live_tests_by_default": True}},
            {"selectors": {"row_width_percent": 95}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for index, payload in enumerate(invalid_configs):
                config_path = Path(tmp) / f"bad-{index}.json"
                config_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        load_local_config(config_path, project_root=ROOT)

    def test_effective_config_output_is_sanitized(self):
        config = load_local_config(ROOT / "config" / "datalens_mcp.local.example.json", project_root=ROOT)
        config["accidental_token"] = "y0_sensitive_value"
        config["nested"] = {"password": "secret"}

        sanitized = sanitize_local_config(config)

        self.assertEqual(sanitized["accidental_token"], "<redacted>")
        self.assertEqual(sanitized["nested"]["password"], "<redacted>")
        self.assertEqual(sanitized["execution"]["writes"], True)

    def test_v1_execution_and_approval_config_is_migrated_in_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "legacy-v1.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2026-06-04.datalens_mcp_local_config.v1",
                        "safe_mode": {
                            "default": "plan_only",
                            "allow_writes": False,
                            "require_safe_apply_plan": True,
                            "require_fresh_read": True,
                            "preserve_revision": True,
                        },
                        "approval_gates": {
                            "write_requires_tool_approval": True,
                            "publish_requires_explicit_tool_approval": True,
                        },
                        "safe_apply": {
                            "require_approved_plan_path": True,
                            "require_approval_flag": True,
                            "require_env_write_enablement": True,
                            "require_save_mode_first": True,
                            "require_readback_after_save": True,
                            "allow_publish_by_default": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_local_config(config_path, project_root=ROOT)

        self.assertEqual(config["schema_version"], "2026-07-15.datalens_mcp_local_config.v2")
        self.assertEqual(config["execution"]["default"], "follow_user_request")
        self.assertTrue(config["execution"]["writes"])
        self.assertTrue(config["execution"]["save"])
        self.assertTrue(config["execution"]["publish"])
        self.assertNotIn("safe_mode", config)
        self.assertNotIn("approval_gates", config)
        self.assertNotIn("require_approved_plan_path", config["safe_apply"])
        self.assertIn("local_config:v1->v2_follow_user_request", config["_meta"]["compatibility_migrations"])

    def test_legacy_mcp_profile_config_is_tolerated_but_removed_from_effective_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "legacy.json"
            config_path.write_text(
                json.dumps({"mcp": {"tool_profile": "all", "unknown_profile_policy": "error"}}),
                encoding="utf-8",
            )
            config = load_local_config(config_path, project_root=ROOT)

        self.assertNotIn("mcp", config)

    def test_example_config_matches_json_schema(self):
        schema_result = validate_schema_file(ROOT / "schemas" / "datalens-mcp-local-config.schema.json")
        config = load_local_config(ROOT / "config" / "datalens_mcp.local.example.json", project_root=ROOT)

        self.assertTrue(schema_result.ok, schema_result.issues)
        self.assertTrue(config["_meta"]["loaded_from_file"])

    def test_local_config_schema_file_is_valid(self):
        result = validate_schema_file(ROOT / "schemas" / "datalens-mcp-local-config.schema.json")
        self.assertTrue(result.ok, result.issues)

    def test_default_dot_workspace_resolves_to_server_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            server_root = Path(tmp) / "project"
            config = load_local_config(project_root=server_root)
            resolved = apply_tool_defaults(
                "dl_runtime_status",
                {},
                config,
                project_root=str(server_root),
                supports_project_root=True,
                supports_workbook_id=False,
                supports_readback_mode=False,
            )

        self.assertEqual(resolved["project_root"], str(server_root.resolve()))

    def test_absolute_workspace_override_beats_server_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server_root = root / "server"
            workspace = root / "workspace"
            config_path = root / "local.json"
            config_path.write_text(
                json.dumps({"defaults": {"project_workspace_path": str(workspace)}}),
                encoding="utf-8",
            )
            config = load_local_config(config_path, project_root=server_root)
            resolved = apply_tool_defaults(
                "dl_runtime_status",
                {},
                config,
                project_root=str(server_root),
                supports_project_root=True,
                supports_workbook_id=False,
                supports_readback_mode=False,
            )

        self.assertEqual(resolved["project_root"], str(workspace.resolve()))

    def test_explicit_tool_project_root_has_highest_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "local.json"
            config_path.write_text(
                json.dumps({"defaults": {"project_workspace_path": str(root / "configured")}}),
                encoding="utf-8",
            )
            config = load_local_config(config_path, project_root=root / "server")
            resolved = apply_tool_defaults(
                "dl_runtime_status",
                {"project_root": str(root / "explicit")},
                config,
                project_root=str(root / "server"),
                supports_project_root=True,
                supports_workbook_id=False,
                supports_readback_mode=False,
            )

        self.assertEqual(resolved["project_root"], str(root / "explicit"))


if __name__ == "__main__":
    unittest.main()
