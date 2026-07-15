import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "codex_mcp_launch.sh"


@contextmanager
def patched_env(values, *, clear=False):
    old_env = dict(os.environ)
    if clear:
        os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


class LauncherHardeningTests(unittest.TestCase):
    def test_launcher_has_no_homebrew_yc_path_and_resolves_yc_only_for_refresh(self):
        text = LAUNCHER.read_text(encoding="utf-8")

        self.assertNotIn("/opt/homebrew/bin/yc", text)
        self.assertIn("DATALENS_YC_BINARY", text)
        self.assertIn("command -v yc", text)
        self.assertIn(".venv/bin/python", text)
        self.assertIn("DATALENS_ENABLE_TOKEN_REFRESH_ON_401", text)

    def test_launcher_uses_env_file_and_does_not_mint_token_at_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_python = tmp_path / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                "printf 'ARGS=%s\\n' \"$*\"\n"
                "printf 'TOKEN_PRESENT=%s\\n' \"${DATALENS_IAM_TOKEN:+1}\"\n"
                "printf 'YC_TOKEN_PRESENT=%s\\n' \"${YC_IAM_TOKEN:+1}\"\n"
                "printf 'ENV_FILE=%s\\n' \"$DATALENS_ENV_FILE\"\n"
                "printf 'WRITES=%s\\n' \"$DATALENS_MCP_ENABLE_WRITES\"\n"
                "printf 'EXPERT=%s\\n' \"$DATALENS_MCP_ENABLE_EXPERT_RPC\"\n"
                "printf 'SAVE=%s\\n' \"$DATALENS_MCP_LIVE_ALLOW_SAVE\"\n"
                "printf 'PUBLISH=%s\\n' \"$DATALENS_MCP_LIVE_ALLOW_PUBLISH\"\n"
                "printf 'REFRESH=%s\\n' \"$DATALENS_ENABLE_TOKEN_REFRESH_ON_401\"\n"
                "printf 'BASE=%s\\n' \"$DATALENS_API_BASE_URL\"\n"
                "printf 'VERSION=%s\\n' \"$DATALENS_API_VERSION\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = {
                **os.environ,
                "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            for key in ("DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "DATALENS_YC_BINARY"):
                env.pop(key, None)
            result = subprocess.run(
                [str(LAUNCHER)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("TOKEN_PRESENT=", result.stdout)
        self.assertIn("YC_TOKEN_PRESENT=", result.stdout)
        self.assertIn("ENV_FILE=", result.stdout)
        self.assertIn("WRITES=1", result.stdout)
        self.assertIn("EXPERT=0", result.stdout)
        self.assertIn("SAVE=1", result.stdout)
        self.assertIn("PUBLISH=1", result.stdout)
        self.assertIn("REFRESH=1", result.stdout)
        self.assertIn(f"--project-root {REPO_ROOT}", result.stdout)
        self.assertIn("BASE=https://api.datalens.tech", result.stdout)
        self.assertIn("VERSION=auto", result.stdout)

    def test_launcher_honors_explicit_yc_binary_only_when_refresh_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_python = tmp_path / "python3"
            fake_yc = tmp_path / "custom-yc"
            fake_python.write_text("#!/bin/sh\nprintf 'YC_BINARY=%s\\n' \"$DATALENS_YC_BINARY\"\n", encoding="utf-8")
            fake_yc.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
            fake_python.chmod(0o755)
            fake_yc.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
                "DATALENS_YC_BINARY": str(fake_yc),
                "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            env.pop("DATALENS_IAM_TOKEN", None)
            env.pop("YC_IAM_TOKEN", None)
            result = subprocess.run(
                [str(LAUNCHER)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn(f"YC_BINARY={fake_yc}", result.stdout)


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_auth_probe_failure_categories_are_actionable(self):
        from datalens_dev_mcp.api.auth import classify_auth_probe_failure

        cases = {
            "BLOCKED_LIVE_CREDENTIALS: Missing DATALENS_ORG_ID": "missing_credentials",
            "getWorkbooksList failed with HTTP 401: auth_invalid_or_expired": "expired_token",
            "getWorkbooksList failed with HTTP 403: permission denied": "organization_access_denied",
            "getWorkbooksList failed before HTTP response: connection refused": "transport_failure",
            "getWorkbooksList failed with HTTP 500": "api_failure",
            "initial_token_bootstrap_failed: yc iam create-token failed": "yc_reauthentication_required",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                result = classify_auth_probe_failure(RuntimeError(message))
                self.assertEqual(result["category"], expected)
                self.assertTrue(result["next_action"])

    def test_auth_probe_missing_credentials_is_classified_without_network(self):
        from datalens_dev_mcp.mcp.tools.runtime import dl_auth_probe

        with patched_env({}, clear=True):
            result = dl_auth_probe()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["category"], "missing_credentials")
        self.assertFalse(result["credential"]["token_present"])
        self.assertFalse(result["credential"]["org_id_set"])

    def test_runtime_status_defaults_normal_execution_on(self):
        from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

        with patched_env({}, clear=True):
            result = dl_runtime_status(project_root="/tmp/project", local_config_path="")

        self.assertTrue(result["allow_writes"])
        self.assertTrue(result["allow_save"])
        self.assertTrue(result["allow_publish"])
        self.assertTrue(result["delete_requires_confirmation"])
        self.assertTrue(result["runtime_env"]["write_flags"]["allow_writes"])
        self.assertTrue(result["runtime_env"]["write_flags"]["allow_save"])
        self.assertTrue(result["runtime_env"]["write_flags"]["allow_publish"])
        self.assertEqual(result["runtime_env"]["api"]["request_timeout_sec"], 30.0)

    def test_runtime_status_reports_explicit_execution_off_switches(self):
        from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

        with patched_env(
            {
                "DATALENS_MCP_ENABLE_WRITES": "0",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "0",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "0",
            },
            clear=True,
        ):
            result = dl_runtime_status(project_root="/tmp/project", local_config_path="")

        self.assertFalse(result["allow_writes"])
        self.assertFalse(result["allow_save"])
        self.assertFalse(result["allow_publish"])
        self.assertIn("runtime_write_switch_disabled", {item["category"] for item in result["diagnostics"]})

    def test_server_loads_credentials_but_preserves_process_execution_hard_off(self):
        from datalens_dev_mcp.server import JsonRpcServer

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "datalens.env"
            env_file.write_text(
                "DATALENS_IAM_TOKEN=super-secret-token-value\n"
                "DATALENS_ORG_ID=org_synthetic\n"
                "DATALENS_MCP_LIVE_ALLOW_SAVE=1\n"
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH=1\n",
                encoding="utf-8",
            )
            with patched_env(
                {
                    "DATALENS_ENV_FILE": str(env_file),
                    "DATALENS_MCP_LIVE_ALLOW_SAVE": "0",
                    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "0",
                },
                clear=True,
            ):
                server = JsonRpcServer(project_root="/tmp/project")
                result = server._call_tool({"name": "dl_runtime_status", "arguments": {}})
                payload = json.loads(result["content"][0]["text"])

                self.assertEqual(os.environ.get("DATALENS_ORG_ID"), "org_synthetic")
                self.assertEqual(os.environ.get("DATALENS_MCP_LIVE_ALLOW_SAVE"), "0")
                self.assertEqual(os.environ.get("DATALENS_MCP_LIVE_ALLOW_PUBLISH"), "0")

        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(result["isError"])
        self.assertTrue(payload["token_present"])
        self.assertTrue(payload["org_id_set"])
        self.assertFalse(payload["allow_save"])
        self.assertFalse(payload["allow_publish"])
        self.assertEqual(payload["runtime_env"]["auth"]["token_source"], "env_file")
        self.assertNotIn(str(env_file), dumped)
        self.assertNotIn("super-secret-token-value", dumped)

    def test_runtime_status_rereads_canonical_env_without_process_restart(self):
        from datalens_dev_mcp.server import JsonRpcServer

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "datalens.env"
            env_file.write_text(
                "DATALENS_IAM_TOKEN=super-secret-token-value\n"
                "DATALENS_ORG_ID=org_synthetic\n"
                "DATALENS_MCP_ENABLE_WRITES=1\n"
                "DATALENS_MCP_LIVE_ALLOW_SAVE=1\n"
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH=1\n",
                encoding="utf-8",
            )
            with patched_env({"DATALENS_ENV_FILE": str(env_file)}, clear=True):
                server = JsonRpcServer(project_root="/tmp/project")
                env_file.write_text(
                    "DATALENS_IAM_TOKEN=super-secret-token-value\n"
                    "DATALENS_ORG_ID=org_synthetic\n"
                    "DATALENS_MCP_ENABLE_WRITES=0\n"
                    "DATALENS_MCP_LIVE_ALLOW_SAVE=0\n"
                    "DATALENS_MCP_LIVE_ALLOW_PUBLISH=0\n",
                    encoding="utf-8",
                )
                response = server._call_tool({"name": "dl_runtime_status", "arguments": {}})
                payload = json.loads(response["content"][0]["text"])
                env_file.write_text(
                    "DATALENS_IAM_TOKEN=super-secret-token-value\n"
                    "DATALENS_ORG_ID=org_synthetic\n"
                    "DATALENS_MCP_ENABLE_WRITES=1\n"
                    "DATALENS_MCP_LIVE_ALLOW_SAVE=1\n"
                    "DATALENS_MCP_LIVE_ALLOW_PUBLISH=1\n",
                    encoding="utf-8",
                )
                enabled_response = server._call_tool({"name": "dl_runtime_status", "arguments": {}})
                enabled_payload = json.loads(enabled_response["content"][0]["text"])

        self.assertFalse(payload["allow_writes"])
        self.assertFalse(payload["allow_save"])
        self.assertFalse(payload["allow_publish"])
        self.assertTrue(enabled_payload["allow_writes"])
        self.assertTrue(enabled_payload["allow_save"])
        self.assertTrue(enabled_payload["allow_publish"])

    def test_runtime_status_masks_secrets_and_reports_write_flags(self):
        from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

        with tempfile.TemporaryDirectory() as tmp:
            fake_yc = Path(tmp) / "yc"
            fake_yc.write_text("#!/bin/sh\nprintf 'synthetic-token\\n'\n", encoding="utf-8")
            fake_yc.chmod(0o755)
            env = {
                "DATALENS_IAM_TOKEN": "super-secret-token-value",
                "DATALENS_ORG_ID": "org_synthetic",
                "DATALENS_API_BASE_URL": "https://api.datalens.tech",
                "DATALENS_API_VERSION": "1",
                "DATALENS_MCP_ENABLE_WRITES": "1",
                "DATALENS_MCP_ENABLE_EXPERT_RPC": "1",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
                "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "1",
                "DATALENS_YC_BINARY": str(fake_yc),
            }
            with patched_env(env, clear=True):
                result = dl_runtime_status(project_root="/tmp/project", local_config_path="/tmp/config.json")

        dumped = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["allow_writes"])
        self.assertTrue(result["allow_save"])
        self.assertTrue(result["allow_publish"])
        self.assertTrue(result["expert_rpc_enabled"])
        self.assertTrue(result["token_present"])
        self.assertTrue(result["token_refresh_on_401"])
        self.assertTrue(result["yc_binary_configured"])
        self.assertEqual(result["api_base_url"], "https://api.datalens.tech")
        self.assertEqual(result["api_version"], "1")
        self.assertEqual(result["project_root"], "/tmp/project")
        self.assertEqual(result["local_config_path"], "/tmp/config.json")
        self.assertEqual(result["runtime_env"]["auth"]["token_source"], "process_env")
        self.assertEqual(result["runtime_env"]["api"]["base_url_source"], "process_env")
        self.assertTrue(result["api_version_selection"]["explicit_version_mismatch"])
        self.assertFalse(result["api_version_selection"]["write_compatible"])
        self.assertIn("explicit_v1_readonly_compatibility_only", result["api_version_selection"]["write_block_reason"])
        self.assertFalse(result["write_compatible"])
        self.assertTrue(result["runtime_env"]["auth"]["refresh_available"])
        self.assertEqual(result["config_defaults"]["execution_default"], "follow_user_request")
        self.assertTrue(result["config_defaults"]["writes_default"])
        self.assertTrue(result["config_defaults"]["save_default"])
        self.assertTrue(result["config_defaults"]["publish_default"])
        self.assertIn("explicit_api_version_mismatch", {item["category"] for item in result["diagnostics"]})
        self.assertIn("standalone_script_env_mismatch", {item["category"] for item in result["diagnostics"]})
        self.assertIn("supported", result["route_policy"])
        self.assertNotIn("super-secret-token-value", dumped)
        self.assertNotIn("synthetic-token", dumped)

    def test_runtime_status_reports_refresh_unavailable_without_yc(self):
        from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

        env = {
            "DATALENS_IAM_TOKEN": "super-secret-token-value",
            "DATALENS_ORG_ID": "org_synthetic",
            "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "1",
            "DATALENS_YC_BINARY": "/tmp/missing-yc",
        }
        with patched_env(env, clear=True):
            result = dl_runtime_status(project_root="/tmp/project", local_config_path="")

        self.assertFalse(result["runtime_env"]["auth"]["refresh_available"])
        self.assertFalse(result["runtime_env"]["yc"]["resolved"])
        self.assertIn("token_refresh_unavailable", {item["category"] for item in result["diagnostics"]})

    def test_auth_probe_uses_minimal_workbook_read_and_structured_error(self):
        from datalens_dev_mcp.mcp.tools.runtime import dl_auth_probe

        class FakeClient:
            def __init__(self, fail=False):
                self.fail = fail
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if self.fail:
                    raise RuntimeError("HTTP 401 Authorization Bearer super-secret-token-value")
                return {"workbooks": []}

        with tempfile.TemporaryDirectory() as tmp:
            fake_yc = Path(tmp) / "yc"
            fake_yc.write_text("#!/bin/sh\nprintf 'synthetic-token\\n'\n", encoding="utf-8")
            fake_yc.chmod(0o755)
            env = {
                "DATALENS_IAM_TOKEN": "super-secret-token-value",
                "DATALENS_ORG_ID": "org_synthetic",
                "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "1",
                "DATALENS_YC_BINARY": str(fake_yc),
            }
            with patched_env(env, clear=True):
                ok_client = FakeClient()
                ok = dl_auth_probe(client=ok_client)
                failed = dl_auth_probe(client=FakeClient(fail=True))

        self.assertTrue(ok["ok"])
        self.assertEqual(ok_client.calls, [("getWorkbooksList", {"page": 1, "pageSize": 1})])
        self.assertEqual(ok["auth_mode"], "process_env")
        self.assertTrue(ok["refresh_on_401"])
        self.assertTrue(ok["token_refresh_available"])
        self.assertFalse(failed["ok"])
        self.assertIn("error", failed)
        self.assertEqual(failed["error"]["category"], "expired_token")
        self.assertNotIn("super-secret-token-value", json.dumps(failed))

    def test_auth_probe_bootstraps_missing_token_with_yc_and_reports_no_secret(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.mcp.tools.runtime import dl_auth_probe

        class ProbeTransport:
            def __init__(self):
                self.calls = 0

            def post_json(self, url, body, headers):
                self.calls += 1
                return b'{"workbooks": []}'

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_file = tmp_path / "env"
            fake_yc = tmp_path / "yc"
            env_file.write_text(
                "DATALENS_ORG_ID=org_synthetic\n"
                "DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1\n"
                f"DATALENS_YC_BINARY={fake_yc}\n",
                encoding="utf-8",
            )
            fake_yc.write_text("#!/bin/sh\nprintf 'fresh-token-placeholder\\n'\n", encoding="utf-8")
            fake_yc.chmod(0o755)
            transport = ProbeTransport()
            with patched_env({"DATALENS_ENV_FILE": str(env_file)}, clear=True):
                client = DataLensApiClient(DataLensConfig.from_env(), transport=transport)
                result = dl_auth_probe(client=client)
            persisted = env_file.read_text(encoding="utf-8")
            mode = env_file.stat().st_mode & 0o777

        self.assertTrue(result["ok"])
        self.assertTrue(result["initial_token_bootstrapped"])
        self.assertEqual(transport.calls, 1)
        self.assertEqual(mode, 0o600)
        self.assertIn("DATALENS_IAM_TOKEN=fresh-token-placeholder", persisted)
        self.assertNotIn("fresh-token-placeholder", json.dumps(result))

    def test_credential_report_omits_env_file_path(self):
        from datalens_dev_mcp.config import DataLensConfig

        cfg = DataLensConfig(
            iam_token="super-secret-token-value",
            org_id="org_synthetic",
            env_file_path="/tmp/datalens.env",
            env_file_loaded=True,
            credential_source="env_file",
            org_id_source="env_file",
        )

        report = cfg.credential_report()
        dumped = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["env_file"]["configured"])
        self.assertTrue(report["env_file"]["loaded"])
        self.assertNotIn("path", report["env_file"])
        self.assertNotIn("/tmp/datalens.env", dumped)

    def test_supported_env_copy_script_filters_keys_and_writes_0600(self):
        spec = spec_from_file_location("copy_supported_datalens_env", REPO_ROOT / "scripts" / "copy_supported_datalens_env.py")
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.env"
            target = Path(tmp) / "managed.env"
            source.write_text(
                "DATALENS_IAM_TOKEN=super-secret-token-value\n"
                "DATALENS_ORG_ID=org_synthetic\n"
                "DATALENS_REQUEST_TIMEOUT_SEC=12.5\n"
                "DATALENS_AUTH_MODE=authorization\n",
                encoding="utf-8",
            )

            result = module.copy_supported(source, target)
            text = target.read_text(encoding="utf-8")

        dumped = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode_octal"], "0o600")
        self.assertIn("DATALENS_MCP_ENABLE_WRITES=1", text)
        self.assertIn("DATALENS_MCP_LIVE_ALLOW_SAVE=1", text)
        self.assertIn("DATALENS_MCP_LIVE_ALLOW_PUBLISH=1", text)
        self.assertIn("DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1", text)
        self.assertIn("DATALENS_REQUEST_TIMEOUT_SEC=12.5", text)
        self.assertNotIn("DATALENS_AUTH_MODE", text)
        self.assertIn("DATALENS_AUTH_MODE", result["unsupported_keys_skipped"])
        self.assertNotIn("super-secret-token-value", dumped)


class DataLensInternalNameTests(unittest.TestCase):
    def test_sanitizer_examples(self):
        from datalens_dev_mcp.validators.datalens_names import sanitize_datalens_internal_name

        cases = {
            "Revenue / configuration history": "revenue_configuration_history",
            "Event diagnostic results": "event_diagnostic_results",
            "Device logger": "device_logger",
            "Device eSIM": "device_esim",
            "Source Tables / Details": "source_tables_details",
            "Продажи по регионам": "prodazhi_po_regionam",
            "Выручка по регионам": "vyruchka_po_regionam",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(sanitize_datalens_internal_name(source), expected)

    def test_visible_title_with_slash_is_allowed_but_internal_data_name_is_flagged(self):
        from datalens_dev_mcp.validators.datalens_names import find_unsafe_internal_names

        payload = {
            "entry": {
                "data": {
                    "title": "Revenue / configuration history",
                    "name": "Revenue / configuration history",
                }
            }
        }

        issues = find_unsafe_internal_names(payload)

        self.assertEqual([issue["path"] for issue in issues], ["entry.data.name"])
        self.assertEqual(issues[0]["suggested"], "revenue_configuration_history")

    def test_generated_editor_payload_sanitizes_internal_name_but_keeps_visible_title(self):
        from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload

        payload = compile_editor_payload(
            {
                "widget_id": "revenue_widget",
                "route": "editor_advanced",
                "entry_type": "advanced-chart_node",
                "name": "Revenue / configuration history",
                "tabs": {
                    "meta.json": '{"links": {}, "title": "Revenue / configuration history"}',
                    "params.js": "module.exports = {};",
                    "sources.js": "module.exports = {};",
                    "controls.js": "module.exports = {};",
                    "prepare.js": "module.exports = {render: () => 'Revenue / configuration history'};",
                },
            },
            workbook_id="workbook_synthetic_001",
        )

        self.assertEqual(payload["entry"]["name"], "revenue_configuration_history")
        self.assertIn("Revenue / configuration history", payload["entry"]["data"]["prepare"])


class WritePreflightTests(unittest.TestCase):
    def test_expert_rpc_rejects_write_methods_before_request(self):
        from datalens_dev_mcp.api.errors import DataLensSafetyError
        from datalens_dev_mcp.mcp.tools.rpc import dl_rpc_expert

        class RecordingClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                return {"ok": True}

        client = RecordingClient()
        env = {
            "DATALENS_IAM_TOKEN": "token-value",
            "DATALENS_ORG_ID": "org_synthetic",
            "DATALENS_MCP_ENABLE_EXPERT_RPC": "1",
        }
        with patched_env(env, clear=True):
            with self.assertRaises(DataLensSafetyError):
                dl_rpc_expert(
                    "createEditorChart",
                    {"entry": {"data": {"name": "Revenue / configuration history"}}},
                    client=client,
                )

        self.assertEqual(client.calls, [])

    def test_safe_apply_blocks_unsafe_internal_name_before_write_call(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class RecordingClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                return {"ok": True}

        client = RecordingClient()
        plan = create_safe_apply_plan(
            project_root="/tmp/synthetic-project",
            approved=True,
            actions=[
                {
                    "action": "create_editor_chart",
                    "method": "createEditorChart",
                    "payload": {"entry": {"data": {"name": "Source Tables / Details"}}},
                    "fresh_read_method": "getWorkbooksList",
                    "fresh_read_payload": {"page": 1, "pageSize": 1},
                }
            ],
        )

        result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertFalse(result["executed"])
        self.assertTrue(any("entry.data.name" in reason for reason in result["blocked_reasons"]))
        self.assertEqual(client.calls, [])


class PartialCreateReconciliationTests(unittest.TestCase):
    def test_reconciliation_reuses_existing_object_and_detects_duplicates(self):
        from datalens_dev_mcp.mcp.tools.reconciliation import dl_reconcile_partial_creates

        planned = [
            {
                "display_title": "Revenue / configuration history",
                "internal_name": "revenue_configuration_history",
                "object_type": "editor_chart",
            },
            {"display_title": "Event diagnostic results", "internal_name": "event_diagnostic_results", "object_type": "editor_chart"},
        ]
        entries_payload = {
            "entries": [
                {
                    "entryId": "entry_existing",
                    "scope": "editor_chart",
                    "type": "advanced-chart_node",
                    "name": "revenue_configuration_history",
                    "displayKey": "Revenue / configuration history",
                },
                {
                    "entryId": "entry_dup_a",
                    "scope": "editor_chart",
                    "type": "advanced-chart_node",
                    "name": "event_diagnostic_results",
                    "displayKey": "Event diagnostic results",
                },
                {
                    "entryId": "entry_dup_b",
                    "scope": "editor_chart",
                    "type": "advanced-chart_node",
                    "name": "event_diagnostic_results",
                    "displayKey": "Event diagnostic results",
                },
            ]
        }

        result = dl_reconcile_partial_creates("workbook_1", planned, entries_payload=entries_payload)

        self.assertTrue(result["ok"])
        self.assertEqual(result["objects"][0]["existing_object_id"], "entry_existing")
        self.assertEqual(result["objects"][0]["recommended_action"], "reuse")
        self.assertEqual(result["objects"][1]["recommended_action"], "manual_review")
        self.assertEqual(result["duplicates_detected"][0]["internal_name"], "event_diagnostic_results")
        self.assertFalse(result["delete_attempted"])


class ProjectAdapterTests(unittest.TestCase):
    def test_unsupported_custom_layout_is_not_successful_empty_safe_apply(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan
        from datalens_dev_mcp.pipeline.project_adapters import detect_project_adapter

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "discovery").mkdir()
            (root / "discovery" / "apply_dashboard.py").write_text("# custom project script\n", encoding="utf-8")

            detected = detect_project_adapter(root)
            plan = dl_create_safe_apply_plan(str(root))

        self.assertEqual(detected["adapter"], "unknown_custom_layout")
        self.assertEqual(plan["status"], "adapter_required")
        self.assertEqual(plan["error"]["category"], "unsupported_custom_layout")
        self.assertEqual(plan["actions"], [])
        self.assertFalse(plan["ok"])


if __name__ == "__main__":
    unittest.main()
