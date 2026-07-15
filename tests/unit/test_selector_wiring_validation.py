import json
import unittest
from unittest.mock import patch

from datalens_dev_mcp.mcp.tools.local_planning import dl_build_selector_wiring_summary
from datalens_dev_mcp.mcp.tool_registry_policy import HIDDEN_TOOL_CALLS_ENV, TEST_ONLY_REGISTRY_ENV
from datalens_dev_mcp.server import JsonRpcServer


def entry_fixture():
    return {
        "entryId": "dash_1",
        "data": {
            "tabs": [
                {
                    "id": "main",
                    "items": [
                        {"id": "selector_paid_date", "type": "control"},
                        {"id": "paid_orders", "type": "chart", "chartId": "chart_paid_orders"},
                    ],
                }
            ]
        },
    }


def widget_plan():
    return [
        {
            "widget_id": "selector_paid_date",
            "selector_definition": {
                "affected_components": [
                    {"widget_id": "paid_orders"},
                ]
            },
        }
    ]


class SelectorWiringValidationTests(unittest.TestCase):
    def test_entry_shaped_saved_and_published_fixtures_pass(self):
        saved = entry_fixture()
        published = entry_fixture()

        result = dl_build_selector_wiring_summary(saved, published, widget_plan())

        self.assertEqual(result["remote"]["status"], "pass")
        self.assertEqual(result["proposed"]["status"], "pass")

    def test_compact_summary_shape_returns_structured_validation_error(self):
        with patch.dict("os.environ", {HIDDEN_TOOL_CALLS_ENV: "1", TEST_ONLY_REGISTRY_ENV: "1"}):
            server = JsonRpcServer(project_root=".")
            result = server._call_tool(
                {
                    "name": "dl_build_selector_wiring_summary",
                    "arguments": {
                        "remote_entry": {"summary": {"identity": {"id": "dash_1"}}},
                        "proposed_entry": entry_fixture(),
                        "widget_plan": widget_plan(),
                    },
                }
            )
        payload = json.loads(result["content"][0]["text"])

        self.assertTrue(result["isError"])
        self.assertEqual(payload["error"]["category"], "datalens_validation_error")
        self.assertIn("data.tabs", payload["error"]["message"])
        self.assertNotEqual(payload["error"]["category"], "unknown_runtime_error")


if __name__ == "__main__":
    unittest.main()
