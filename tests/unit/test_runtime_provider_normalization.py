from __future__ import annotations

import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.config import DataLensConfig


class _SequenceTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post_json(self, url, body, headers):
        self.requests.append((url, json.loads(body.decode("utf-8")), dict(headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response).encode("utf-8")


def _http_error(status: int) -> HTTPError:
    return HTTPError(
        url="https://api.example.invalid/rpc/method",
        code=status,
        msg="error",
        hdrs={},
        fp=BytesIO(b'{"message":"temporary"}'),
    )


class RuntimeProviderNormalizationTests(unittest.TestCase):
    def test_http_500_retries_only_a_bounded_read(self):
        config = DataLensConfig(
            iam_token="synthetic-token",
            org_id="synthetic-org",
            request_interval_sec=0,
            read_transient_retries=1,
        )
        read_transport = _SequenceTransport([_http_error(500), {"entries": []}])
        with patch("datalens_dev_mcp.api.client._transient_retry_pause", return_value=None):
            result = DataLensApiClient(config, transport=read_transport).rpc_readonly(
                "getWorkbookEntries", {"workbookId": "workbook_1"}
            )
        self.assertEqual(result, {"entries": []})
        self.assertEqual(len(read_transport.requests), 2)

        write_transport = _SequenceTransport([_http_error(500), {"ok": True}])
        with patch("datalens_dev_mcp.api.client._transient_retry_pause", return_value=None):
            with self.assertRaises(DataLensApiError):
                DataLensApiClient(config, transport=write_transport).rpc(
                    "createDashboard", {"entry": {"data": {}, "meta": {}}}
                )
        self.assertEqual(len(write_transport.requests), 1)

    def test_create_identity_prefers_strong_response_root(self):
        from datalens_dev_mcp.pipeline.safe_apply import _object_identity, _revision_id

        response = {
            "id": "dataset_created_1",
            "revId": "revision_2",
            "savedId": "revision_2",
            "publishedId": "revision_1",
            "dataset": {"name": "Synthetic dataset", "result_schema": []},
        }
        identity = _object_identity(response)

        self.assertEqual(identity["object_id"], "dataset_created_1")
        self.assertEqual(_revision_id(response), "revision_2")

    def test_structural_editor_and_dashboard_defaults_are_minimal(self):
        from datalens_dev_mcp.api.request_compiler import _adapt_entry_envelope

        editor = _adapt_entry_envelope(
            "createEditorChart",
            {"entry": {"type": "advanced-chart_node", "data": {"prepare": "module.exports = {};"}}},
            mode="save",
        )
        self.assertEqual(editor["entry"]["data"]["controls"], "module.exports = {};\n")
        self.assertNotIn("mode", editor)

        dashboard = _adapt_entry_envelope(
            "createDashboard",
            {
                "entry": {
                    "data": {
                        "tabs": [
                            {
                                "items": [
                                    {"id": "control_1", "type": "control"},
                                    {"id": "chart_1", "type": "widget"},
                                ]
                            }
                        ]
                    },
                    "meta": {},
                }
            },
            mode="save",
        )
        items = dashboard["entry"]["data"]["tabs"][0]["items"]
        self.assertEqual(items[0]["defaults"], {})
        self.assertNotIn("defaults", items[1])

    def test_wizard_comparison_ignores_only_provider_managed_defaults(self):
        from datalens_dev_mcp.pipeline.safe_apply import _write_payload_readback_comparison

        expected = {
            "entryId": "chart_1",
            "template": "datalens",
            "data": {
                "version": 1,
                "visualization": {"id": "indicator"},
                "extraSettings": {"indicatorTitleMode": None},
            },
        }
        actual = {
            "entry": {
                "entryId": "chart_1",
                "template": "provider-template",
                "data": {
                    "version": 9,
                    "visualization": {"id": "indicator"},
                    "extraSettings": {"indicatorTitleMode": "default"},
                },
            }
        }
        comparison = _write_payload_readback_comparison(
            method="updateWizardChart", write_payload=expected, readback=actual
        )
        self.assertTrue(comparison["equivalent"], comparison)

        expected["data"]["extraSettings"]["indicatorTitleMode"] = "show"
        comparison = _write_payload_readback_comparison(
            method="updateWizardChart", write_payload=expected, readback=actual
        )
        self.assertFalse(comparison["equivalent"])
        self.assertIn("$.data.extraSettings.indicatorTitleMode", comparison["diff_paths"])

    def test_empty_required_editor_controls_are_semantically_transparent(self):
        from datalens_dev_mcp.pipeline.safe_apply import _write_payload_readback_comparison

        expected = {
            "entry": {
                "entryId": "chart_1",
                "data": {
                    "prepare": "module.exports = {value: 1};",
                    "controls": "module.exports = {};\n",
                },
            }
        }
        actual = {
            "entry": {
                "entryId": "chart_1",
                "data": {"prepare": "module.exports = {value: 1};"},
            }
        }
        comparison = _write_payload_readback_comparison(
            method="updateEditorChart",
            write_payload=expected,
            readback=actual,
        )
        self.assertTrue(comparison["equivalent"], comparison)

    def test_publish_matches_write_revision_not_pre_publish_revision(self):
        from datalens_dev_mcp.pipeline.safe_apply import _post_write_readback_verification

        verification = _post_write_readback_verification(
            action={"action_type": "publish", "method": "updateWizardChart", "expected_revision": "revision_1"},
            payload={"mode": "publish", "entryId": "chart_1", "revId": "revision_1", "data": {"visualization": {"id": "line"}}},
            fresh={"entry": {"entryId": "chart_1", "revId": "revision_1", "data": {"visualization": {"id": "line"}}}},
            write_payload={"mode": "publish", "entryId": "chart_1", "revId": "revision_1", "data": {"visualization": {"id": "line"}}},
            write_result={"id": "chart_1", "revId": "revision_2", "savedId": "revision_2", "publishedId": "revision_2"},
            readback={
                "entry": {
                    "entryId": "chart_1",
                    "revId": "revision_2",
                    "savedId": "revision_2",
                    "publishedId": "revision_2",
                    "data": {"visualization": {"id": "line"}},
                }
            },
        )

        self.assertTrue(verification["verified"], verification)
        self.assertTrue(verification["publish_source_revision_matched"])
        self.assertEqual(verification["readback_revision"], "revision_2")

    def test_public_task_context_advertises_supported_structured_fields(self):
        from datalens_dev_mcp.server import list_tools

        tool = next(item for item in list_tools("autonomous-v2") if item["name"] == "dl_task_start")
        context = tool["inputSchema"]["properties"]["context"]
        self.assertFalse(context["additionalProperties"])
        self.assertTrue(
            {
                "semantic_changes",
                "acceptance",
                "scope",
                "portfolio_root",
                "max_discovery_objects",
                "create_manifest",
            }.issubset(context["properties"])
        )


if __name__ == "__main__":
    unittest.main()
