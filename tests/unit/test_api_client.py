import json
import os
import stat
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.response import addinfourl


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post_json(self, url, body, headers):
        self.requests.append((url, json.loads(body.decode("utf-8")), dict(headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response).encode("utf-8")


def http_error(status, payload):
    body = json.dumps(payload).encode("utf-8")
    return HTTPError(
        url="https://api.datalens.tech/rpc/updateEditorChart",
        code=status,
        msg="error",
        hdrs={},
        fp=BytesIO(body),
    )


class ApiClientTests(unittest.TestCase):
    def test_default_transport_uses_configured_request_timeout(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        client = DataLensApiClient(
            DataLensConfig(
                iam_token="secret-token",
                org_id="org_synthetic",
                api_version="2",
                request_interval_sec=0,
                request_timeout_sec=4.25,
            )
        )
        with patch("datalens_dev_mcp.api.client.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'
            result = client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 4.25})

    def test_config_env_defaults_execution_on_and_explicit_zero_is_hard_off(self):
        from datalens_dev_mcp.config import DataLensConfig

        with patch.dict(os.environ, {"DATALENS_REQUEST_TIMEOUT_SEC": "8.5"}, clear=True):
            config = DataLensConfig.from_env()

        self.assertTrue(config.write_enabled)
        self.assertTrue(config.save_enabled)
        self.assertTrue(config.publish_enabled)
        self.assertEqual(config.request_timeout_sec, 8.5)

        with patch.dict(
            os.environ,
            {
                "DATALENS_MCP_ENABLE_WRITES": "0",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "0",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "0",
            },
            clear=True,
        ):
            explicitly_disabled = DataLensConfig.from_env()

        self.assertFalse(explicitly_disabled.write_enabled)
        self.assertFalse(explicitly_disabled.save_enabled)
        self.assertFalse(explicitly_disabled.publish_enabled)

    def test_process_zero_is_hard_off_even_when_canonical_env_file_enables_execution(self):
        from datalens_dev_mcp.config import DataLensConfig

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text(
                "DATALENS_MCP_ENABLE_WRITES=1\n"
                "DATALENS_MCP_LIVE_ALLOW_SAVE=1\n"
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH=1\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "DATALENS_ENV_FILE": str(env_file),
                    "DATALENS_MCP_ENABLE_WRITES": "0",
                    "DATALENS_MCP_LIVE_ALLOW_SAVE": "0",
                    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "0",
                },
                clear=True,
            ):
                config = DataLensConfig.from_env()

        self.assertFalse(config.write_enabled)
        self.assertFalse(config.save_enabled)
        self.assertFalse(config.publish_enabled)

    def test_missing_initial_token_is_bootstrapped_and_persisted_0600(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([{"workbooks": []}])
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text(
                "DATALENS_ORG_ID=org_synthetic\nDATALENS_ENABLE_TOKEN_REFRESH_ON_401=1\n",
                encoding="utf-8",
            )
            config = DataLensConfig.from_env(env_file)
            client = DataLensApiClient(config, transport=transport, token_refresher=lambda: "fresh-token-placeholder")

            result = client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1})
            file_text = env_file.read_text(encoding="utf-8")
            file_mode = stat.S_IMODE(env_file.stat().st_mode)

        self.assertEqual(result, {"workbooks": []})
        self.assertEqual(len(transport.requests), 1)
        self.assertIn("fresh-token-placeholder", transport.requests[0][2]["Authorization"])
        self.assertIn("DATALENS_IAM_TOKEN=fresh-token-placeholder", file_text)
        self.assertEqual(file_mode, 0o600)
        self.assertEqual(client.config.env_file_reload_state, "bootstrapped_with_yc")

    def test_canonical_env_reload_updates_all_execution_switches(self):
        from datalens_dev_mcp.config import DataLensConfig

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text(
                "DATALENS_MCP_ENABLE_WRITES=1\n"
                "DATALENS_MCP_LIVE_ALLOW_SAVE=1\n"
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH=1\n",
                encoding="utf-8",
            )
            config = DataLensConfig.from_env(env_file)
            env_file.write_text(
                "DATALENS_MCP_ENABLE_WRITES=0\n"
                "DATALENS_MCP_LIVE_ALLOW_SAVE=0\n"
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH=0\n",
                encoding="utf-8",
            )
            reloaded = config.reload_canonical_env(reload_state="test_reload")

        self.assertFalse(reloaded.write_enabled)
        self.assertFalse(reloaded.save_enabled)
        self.assertFalse(reloaded.publish_enabled)
        self.assertEqual(reloaded.env_file_reload_state, "test_reload")

    def test_headers_and_write_payload_compaction_preserves_empty_values(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([{"ok": True}])
        client = DataLensApiClient(
            DataLensConfig(iam_token="secret-token", org_id="org_synthetic", api_version="2", request_interval_sec=0),
            transport=transport,
        )

        client.rpc(
            "createEditorChart",
            {
                "entry": {"data": {"params": ""}},
                "includeLinks": False,
                "name": " X ",
                "emptyList": [],
                "emptyObject": {},
                "emptyString": "",
            },
        )

        _, payload, headers = transport.requests[0]
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["x-dl-org-id"], "org_synthetic")
        self.assertEqual(headers["x-dl-api-version"], "2")
        self.assertEqual(payload["entry"]["data"]["params"], "")
        self.assertIs(payload["includeLinks"], False)
        self.assertEqual(payload["name"], "X")
        self.assertEqual(payload["emptyList"], [])
        self.assertEqual(payload["emptyObject"], {})
        self.assertEqual(payload["emptyString"], "")

    def test_read_payload_compaction_drops_only_whitelisted_false_flags_and_empty_values(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([{"ok": True}])
        client = DataLensApiClient(
            DataLensConfig(iam_token="secret-token", org_id="org_synthetic", api_version="2", request_interval_sec=0),
            transport=transport,
        )

        client.rpc(
            "getDashboard",
            {
                "dashboardId": "dash_1",
                "includeLinks": False,
                "branch": "",
                "filters": [],
                "options": {},
                "strict": False,
            },
        )

        _, payload, _ = transport.requests[0]
        self.assertEqual(payload, {"dashboardId": "dash_1", "strict": False})

    def test_401_refreshes_once_and_retries_original_request(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport(
            [
                http_error(401, {"message": "unauthorized"}),
                {"ok": True},
            ]
        )
        refresh_calls = []
        client = DataLensApiClient(
            DataLensConfig(
                iam_token="super-secret-token-value",
                org_id="org_synthetic",
                api_version="2",
                request_interval_sec=0,
            ),
            transport=transport,
            token_refresher=lambda: refresh_calls.append("called") or "refreshed-token-value",
        )

        self.assertEqual(client.rpc("updateEditorChart", {"entryId": "entry_synthetic"}), {"ok": True})

        self.assertEqual(refresh_calls, ["called"])
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0][0], "https://api.datalens.tech/rpc/updateEditorChart")
        self.assertEqual(transport.requests[1][0], "https://api.datalens.tech/rpc/updateEditorChart")
        self.assertIn("super-secret-token-value", transport.requests[0][2]["Authorization"])
        self.assertIn("refreshed-token-value", transport.requests[1][2]["Authorization"])

    def test_401_refresh_persists_env_file_atomically_with_0600(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport(
            [
                http_error(401, {"message": "unauthorized"}),
                http_error(401, {"message": "minimal probe unauthorized"}),
                http_error(401, {"message": "reload unauthorized"}),
                {"ok": True},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text(
                "DATALENS_IAM_TOKEN=old-token-value\nDATALENS_ORG_ID=org_synthetic\n",
                encoding="utf-8",
            )
            env_file.chmod(0o600)
            client = DataLensApiClient(
                DataLensConfig(
                    iam_token="old-token-value",
                    org_id="org_synthetic",
                    api_version="2",
                    request_interval_sec=0,
                    env_file_path=str(env_file),
                ),
                transport=transport,
                token_refresher=lambda: "new-token-value",
            )

            self.assertEqual(client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1}), {"ok": True})
            mode = stat.S_IMODE(env_file.stat().st_mode)
            text = env_file.read_text(encoding="utf-8")

        self.assertEqual(mode, 0o600)
        self.assertIn("DATALENS_IAM_TOKEN=new-token-value", text)
        self.assertIn("DATALENS_ORG_ID=org_synthetic", text)

    def test_refresh_failure_returns_clear_auth_error_without_leaking_token(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([http_error(401, {"message": "unauthorized"})])
        client = DataLensApiClient(
            DataLensConfig(
                iam_token="super-secret-token-value",
                org_id="org_synthetic",
                api_version="2",
                request_interval_sec=0,
            ),
            transport=transport,
            token_refresher=lambda: (_ for _ in ()).throw(RuntimeError("refresh token command failed")),
        )

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc("updateEditorChart", {"entryId": "entry_synthetic"})

        text = str(raised.exception)
        self.assertIn("token_refresh_failed", text)
        self.assertNotIn("super-secret-token-value", text)
        self.assertNotIn("Authorization", text)

    def test_missing_credentials_block_before_transport(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([])
        client = DataLensApiClient(DataLensConfig(request_interval_sec=0), transport=transport)

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1})

        self.assertIn("BLOCKED_LIVE_CREDENTIALS", str(raised.exception))
        self.assertEqual(transport.requests, [])

    def test_retry_auth_failure_after_refresh_is_actionable(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport(
            [
                http_error(401, {"message": "expired"}),
                http_error(401, {"message": "still expired"}),
            ]
        )
        client = DataLensApiClient(
            DataLensConfig(iam_token="old-token-value", org_id="org_synthetic", api_version="2", request_interval_sec=0),
            transport=transport,
            token_refresher=lambda: "new-token-value",
        )

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc("updateEditorChart", {"entryId": "entry_synthetic"})

        text = str(raised.exception)
        self.assertIn("auth_retry_failed_after_refresh", text)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0][0], transport.requests[1][0])

    def test_400_validation_error_reports_sanitized_payload_keys(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([http_error(400, {"code": "VALIDATION_ERROR", "message": "bad field"})])
        client = DataLensApiClient(
            DataLensConfig(iam_token="token-value", org_id="org_synthetic", api_version="2", request_interval_sec=0),
            transport=transport,
        )

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc("updateEditorChart", {"entryId": "entry_synthetic", "password": "should-not-echo"})

        text = str(raised.exception)
        self.assertIn("VALIDATION_ERROR", text)
        self.assertIn("compacted_payload_keys", text)
        self.assertNotIn("should-not-echo", text)

    def test_non_json_error_details_are_redacted(self):
        from datalens_dev_mcp.api.client import short_error_detail

        header_value = "abcdefghijklmnopqrstuvwxyz" + "123456"
        dsn = "postgres://user:" + "password1234567890" + "@db.example.local/app"
        detail = short_error_detail(
            f"X-Api-Key: {header_value} "
            f"{dsn}"
        )

        self.assertNotIn(header_value, detail)
        self.assertNotIn("password1234567890", detail)
        self.assertIn("<redacted>", detail)

    def test_auto_api_version_uses_compiled_version_without_probe(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([{"ok": True}])
        client = DataLensApiClient(
            DataLensConfig(iam_token="token-value", org_id="org_synthetic", request_interval_sec=0),
            transport=transport,
        )

        self.assertEqual(client.rpc("updateEditorChart", {"entry": {"entryId": "chart_1"}}), {"ok": True})

        self.assertEqual([request[0].rsplit("/", 1)[-1] for request in transport.requests], ["updateEditorChart"])
        self.assertEqual([request[2]["x-dl-api-version"] for request in transport.requests], ["2"])

    def test_auto_api_version_does_not_fallback_for_readonly_version_failure(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([http_error(400, {"message": "unsupported api version"})])
        client = DataLensApiClient(
            DataLensConfig(iam_token="token-value", org_id="org_synthetic", request_interval_sec=0),
            transport=transport,
        )

        with self.assertRaises(DataLensApiError):
            client.rpc_readonly("getDashboard", {"dashboardId": "dash_1"})

        self.assertEqual([request[0].rsplit("/", 1)[-1] for request in transport.requests], ["getDashboard"])
        self.assertEqual([request[2]["x-dl-api-version"] for request in transport.requests], ["2"])

    def test_explicit_v1_readonly_compatibility_is_user_controlled(self):
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([{"ok": True}])
        client = DataLensApiClient(
            DataLensConfig(
                iam_token="token-value",
                org_id="org_synthetic",
                api_version="1",
                request_interval_sec=0,
            ),
            transport=transport,
        )

        self.assertEqual(client.rpc_readonly("getDashboard", {"dashboardId": "dash_1"}), {"ok": True})

        self.assertEqual([request[0].rsplit("/", 1)[-1] for request in transport.requests], ["getDashboard"])
        self.assertEqual([request[2]["x-dl-api-version"] for request in transport.requests], ["1"])

    def test_auto_api_version_does_not_fallback_for_write_mutations(self):
        from datalens_dev_mcp.api.client import DataLensApiClient, DataLensApiError
        from datalens_dev_mcp.config import DataLensConfig

        transport = FakeTransport([http_error(400, {"message": "unsupported api version"})])
        client = DataLensApiClient(
            DataLensConfig(iam_token="token-value", org_id="org_synthetic", request_interval_sec=0),
            transport=transport,
        )

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc("updateEditorChart", {"entry": {"entryId": "chart_1"}})

        self.assertIn("writes are not retried under another API version", str(raised.exception))
        self.assertEqual([request[0].rsplit("/", 1)[-1] for request in transport.requests], ["updateEditorChart"])
        self.assertEqual([request[2]["x-dl-api-version"] for request in transport.requests], ["2"])


if __name__ == "__main__":
    unittest.main()
