import json
import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply
from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload


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


class Rotating401Transport:
    def __init__(self, env_file: Path) -> None:
        self.env_file = env_file
        self.headers = []

    def post_json(self, url, body, headers):
        self.headers.append(dict(headers))
        if len(self.headers) == 1:
            self.env_file.write_text(
                "DATALENS_IAM_TOKEN=placeholder_b\nDATALENS_ORG_ID=org_from_file\n",
                encoding="utf-8",
            )
            raise HTTPError(url, 401, "Unauthorized", hdrs={}, fp=None)
        return json.dumps({"ok": True, "url": url}).encode("utf-8")


class Refresh401Transport:
    def __init__(self) -> None:
        self.headers = []

    def post_json(self, url, body, headers):
        self.headers.append(dict(headers))
        if "expired" in headers["Authorization"]:
            raise HTTPError(url, 401, "Unauthorized", hdrs={}, fp=None)
        return json.dumps({"ok": True}).encode("utf-8")


class LiveHardeningV2AuthTransactionTests(unittest.TestCase):
    def test_canonical_env_file_overrides_stale_process_token_and_reloads_on_401(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "datalens.env"
            env_file.write_text(
                "DATALENS_IAM_TOKEN=placeholder_a\nDATALENS_ORG_ID=org_from_file\n",
                encoding="utf-8",
            )
            with patched_env(
                {
                    "DATALENS_ENV_FILE": str(env_file),
                    "DATALENS_IAM_TOKEN": "stale_process_value",
                    "DATALENS_ORG_ID": "stale_process_org",
                }
            ):
                cfg = DataLensConfig.from_env()
                transport = Rotating401Transport(env_file)
                client = DataLensApiClient(cfg, transport=transport)
                response = client.rpc_readonly("getWorkbooksList", {"page": 1, "pageSize": 1})
                report = client.config.credential_report()

        self.assertEqual(response["ok"], True)
        self.assertEqual(client.config.credential_source, "env_file")
        self.assertEqual(client.config.env_file_reload_state, "reloaded_after_401")
        self.assertIn("Bearer placeholder_a", transport.headers[0]["Authorization"])
        self.assertIn("Bearer placeholder_b", transport.headers[-1]["Authorization"])
        self.assertNotIn("placeholder_", json.dumps(report))
        self.assertNotIn("stale_process", json.dumps(report))

    def test_refresh_success_persists_0600_and_retries_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "datalens.env"
            env_file.write_text(
                "DATALENS_IAM_TOKEN=expired\nDATALENS_ORG_ID=org_from_file\n",
                encoding="utf-8",
            )
            cfg = DataLensConfig.from_env(env_file)
            transport = Refresh401Transport()
            client = DataLensApiClient(cfg, transport=transport, token_refresher=lambda: "fresh")
            response = client.rpc_readonly("getWorkbooksList", {"page": 1, "pageSize": 1})
            file_text = env_file.read_text(encoding="utf-8")
            file_mode = stat.S_IMODE(env_file.stat().st_mode)

        self.assertTrue(response["ok"])
        self.assertEqual(transport.headers[0]["Authorization"], "Bearer expired")
        self.assertEqual(transport.headers[-1]["Authorization"], "Bearer fresh")
        self.assertEqual([header["Authorization"] for header in transport.headers].count("Bearer fresh"), 1)
        self.assertIn("DATALENS_IAM_TOKEN=fresh", file_text)
        self.assertEqual(file_mode, 0o600)

    def test_refresh_failure_is_secret_safe_and_not_looped(self):
        class Always401Transport:
            def __init__(self):
                self.calls = 0

            def post_json(self, url, body, headers):
                self.calls += 1
                raise HTTPError(url, 401, "Unauthorized", hdrs={}, fp=None)

        transport = Always401Transport()
        cfg = DataLensConfig(iam_token="expired_token", org_id="org")
        client = DataLensApiClient(
            cfg,
            transport=transport,
            token_refresher=lambda: (_ for _ in ()).throw(RuntimeError("DATALENS_IAM_TOKEN leaked_token")),
        )

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc_readonly("getWorkbooksList", {"page": 1, "pageSize": 1})

        message = str(raised.exception)
        self.assertEqual(transport.calls, 1)
        self.assertIn("token_refresh_failed", message)
        self.assertNotIn("leaked_token", message)

    def test_yc_refresh_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_yc = Path(tmp) / "yc"
            fake_yc.write_text(
                "#!/bin/sh\n"
                "sleep 2\n"
                "printf 'fresh-token\\n'\n",
                encoding="utf-8",
            )
            fake_yc.chmod(0o755)

            with self.assertRaises(DataLensApiError) as raised:
                refresh_iam_token_with_yc(yc_binary=str(fake_yc), timeout_sec=0.01)

        self.assertIn("timed out", str(raised.exception))

    def test_safe_apply_failed_action_marks_batch_failed_not_success(self):
        class FailingThirdClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                object_id = payload.get("chartId") or payload.get("dashboardId") or (payload.get("entry") or {}).get("entryId")
                if method == "updateEditorChart" and object_id == "chart_2":
                    raise RuntimeError("write failed")
                return {"status": "ok", "entry": {"entryId": object_id, "revId": f"rev_{object_id}", "savedId": "saved"}}

        with tempfile.TemporaryDirectory() as tmp:
            actions = []
            for index in range(4):
                chart_id = f"chart_{index}"
                actions.append(
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": chart_id, "revId": f"rev_{chart_id}"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": chart_id, "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": chart_id, "branch": "saved"},
                    }
                )
            client = FailingThirdClient()
            plan = create_safe_apply_plan(project_root=tmp, actions=actions, approved=True)
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["completed_action_count"], 2)
        self.assertEqual(result["completed_action_indices"], [0, 1])
        self.assertEqual(result["failed_action_index"], 2)
        self.assertEqual(result["failed_action_indices"], [2])
        self.assertEqual(result["skipped_action_indices"], [3])
        self.assertEqual(len(result["actions"]), 3)
        self.assertNotIn("chart_3", json.dumps(client.calls))
        self.assertIn("rollback", result)
        self.assertTrue(result["rollback"]["compensation_plan"])
        self.assertEqual(result["retry_resume"]["completed_action_indices"], [0, 1])
        self.assertEqual(result["retry_resume"]["failed_action_index"], 2)
        self.assertTrue(result["retry_resume"]["failed_action_write_attempted"])
        self.assertEqual(result["retry_resume"]["safe_unfinished_action_indices"], [])
        self.assertEqual(result["retry_resume"]["resume_policy"], "write_outcome_unknown_blocks_automatic_resume")

    def test_safe_apply_stale_revision_blocks_before_write_and_is_retryable(self):
        class StaleRevisionClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "getEditorChart":
                    return {"entry": {"entryId": "chart_1", "revId": "rev_new", "savedId": "saved"}}
                raise AssertionError("write must not be attempted")

        with tempfile.TemporaryDirectory() as tmp:
            client = StaleRevisionClient()
            plan = create_safe_apply_plan(
                project_root=tmp,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_old"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                    }
                ],
                approved=True,
            )
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_action_index"], 0)
        self.assertEqual(result["completed_action_indices"], [])
        self.assertEqual(result["failed_action_indices"], [0])
        self.assertEqual(result["skipped_action_indices"], [])
        self.assertEqual(result["actions"][0]["error"]["category"], "stale_revision")
        self.assertFalse(result["actions"][0]["write_attempted"])
        self.assertEqual([method for method, _payload in client.calls], ["getEditorChart"])
        self.assertEqual(result["retry_resume"]["safe_unfinished_action_indices"], [0])

    def test_dashboard_root_tabs_do_not_require_native_title_hint(self):
        payload = {
            "tabs": [
                {"id": "overview", "title": "Overview", "items": ["widget_1"]},
                {"id": "details", "title": "Details", "items": ["widget_2"]},
            ],
            "items": [
                {"id": "widget_1", "type": "chart", "chartId": "chart_1"},
                {"id": "widget_2", "type": "chart", "chartId": "chart_2"},
            ],
        }

        result = validate_dashboard_payload(payload)

        self.assertEqual([issue.to_dict() for issue in result.issues if issue.severity == "error"], [])


if __name__ == "__main__":
    unittest.main()
