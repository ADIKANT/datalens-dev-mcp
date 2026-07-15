import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.mcp.response_projection import (
    dashboard_summary,
    editor_chart_summary,
    project_dataset_response,
    project_dashboard_response,
    project_editor_chart_response,
    project_workbook_entries_response,
    sanitize_response,
    stable_sha256,
)
from datalens_dev_mcp.mcp.tools import discovery
from datalens_dev_mcp.mcp.tools.rpc import dl_list_api_methods
from datalens_dev_mcp.server import JsonRpcServer


def dashboard_fixture():
    return {
        "branch": "saved",
        "entry": {
            "entryId": "dash_1",
            "revId": "rev_1",
            "savedId": "saved_1",
            "workbookId": "workbook_1",
            "displayKey": "Sales dashboard",
            "data": {
                "title": "Sales dashboard",
                "sources": [{"name": "source_1", "Authorization": "Bearer fixtureTokenValue12345"}],
                "tabs": [{"id": "tab_1", "title": "Main", "items": ["item_1", "item_2"]}],
                "items": [
                    {"id": "item_1", "type": "chart", "chartId": "chart_1"},
                    {"id": "item_2", "type": "control", "field": "segment"},
                ],
                "links": [{"from": "selector_1", "to": "chart_1", "param": "segment"}],
            },
        },
    }


def editor_chart_fixture():
    return {
        "entry": {
            "entryId": "chart_1",
            "revId": "rev_1",
            "savedId": "saved_1",
            "workbookId": "workbook_1",
            "scope": "editor_chart",
            "data": {
                "title": "Editor chart",
                "annotation": "Synthetic annotation",
                "sources": [{"id": "source_1", "query": "select 1"}],
                "prepare": [{"body": "const x = 1;"}],
                "controls": [{"name": "segment"}],
                "config": {"api_token": "fixture-secret-token-value"},
            },
        },
        "links": [{"id": "link_1", "target": "dash_1"}],
    }


class ResponseProjectionTests(unittest.TestCase):
    def test_dashboard_summary_omits_entry_data_but_keeps_structure(self):
        summary = dashboard_summary(dashboard_fixture())
        serialized = json.dumps(summary, sort_keys=True)

        self.assertEqual(summary["identity"]["id"], "dash_1")
        self.assertEqual(summary["counts"]["tabs"], 1)
        self.assertEqual(summary["counts"]["items"], 2)
        self.assertEqual(summary["counts"]["controls"], 1)
        self.assertEqual(summary["selector_impact_wiring"]["targets"], ["chart_1"])
        self.assertNotIn("sources", serialized)
        self.assertIn("sha256", summary["data_metadata"])

    def test_editor_chart_summary_records_section_hashes_without_inline_sections(self):
        summary = editor_chart_summary(editor_chart_fixture())
        serialized = json.dumps(summary, sort_keys=True)
        section_names = {section["name"] for section in summary["data_sections"]}

        self.assertEqual(summary["identity"]["id"], "chart_1")
        self.assertIn("sources", section_names)
        self.assertIn("prepare", section_names)
        self.assertIn("config", section_names)
        self.assertNotIn("select 1", serialized)
        self.assertNotIn("fixture-secret-token-value", serialized)
        self.assertTrue(all(section["sha256"] for section in summary["data_sections"]))

    def test_workbook_entries_summary_omits_unrelated_hydrated_fields(self):
        projected = project_workbook_entries_response(
            {
                "page": 1,
                "pageSize": 50,
                "total": 1,
                "entries": [
                    {
                        "entryId": "chart_1",
                        "scope": "editor_chart",
                        "displayKey": "Chart",
                        "workbookId": "workbook_1",
                        "data": {"large": "not returned"},
                    }
                ],
            },
            response_mode="summary",
        )
        serialized = json.dumps(projected["summary"], sort_keys=True)

        self.assertEqual(projected["summary"]["count"], 1)
        self.assertNotIn("not returned", serialized)
        self.assertEqual(projected["summary"]["entries"][0]["entry_id"], "chart_1")

    def test_workbook_entries_summary_is_bounded_and_artifact_backed(self):
        entries = [
            {
                "entryId": f"chart_{index}",
                "scope": "editor_chart" if index % 2 else "dataset",
                "displayKey": "Very long workbook entry title " + ("x" * 240),
                "workbookId": "workbook_1",
                "data": {"large": "not returned"},
            }
            for index in range(200)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            projected = project_workbook_entries_response(
                {"entries": entries},
                response_mode="summary",
                inline_char_budget=6000,
                project_root=tmp,
                run_id="workbook-summary-budget",
            )

        serialized = json.dumps(projected, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        self.assertLessEqual(len(serialized), 6000)
        self.assertEqual(projected["summary"]["count"], 200)
        self.assertEqual(len(projected["summary"]["entries"]), 12)
        self.assertTrue(projected["summary"]["entries_truncated"])
        self.assertEqual(projected["summary"]["type_counts"]["dataset"], 100)
        self.assertIn("artifact", projected)

    def test_api_method_catalog_is_compact_and_validates_bool_input(self):
        compact = dl_list_api_methods(include_guarded_writes=False)
        serialized = json.dumps(compact, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

        self.assertTrue(compact["ok"])
        self.assertLessEqual(len(serialized), 6000)
        self.assertIn("dl_get_api_method_schema", compact["detail_tool"])
        self.assertEqual(dl_list_api_methods(include_guarded_writes="bad")["error"]["category"], "invalid_input")

    def test_dataset_rpc_wrapper_summary_preserves_identity_revision_and_bounded_shape(self):
        projected = project_dataset_response(
            {
                "result": {
                    "dataset": {
                        "datasetId": "dataset_1",
                        "fields": [
                            {
                                "name": "amount",
                                "guid": "guid_amount",
                                "type": "float",
                                "aggregation": "sum",
                                "formula": "SUM([amount])",
                            }
                        ],
                        "sources": [{"type": "sql", "connectionId": "connection_1", "sql": "select * from table"}],
                    }
                },
                "metadata": {"revId": "rev_dataset_1"},
            },
            response_mode="summary",
        )
        summary = projected["summary"]
        serialized = json.dumps(summary, sort_keys=True)

        self.assertEqual(summary["identity"]["id"], "dataset_1")
        self.assertEqual(summary["identity"]["rev_id"], "rev_dataset_1")
        self.assertEqual(summary["fields"]["count"], 1)
        self.assertEqual(summary["fields"]["items"][0]["guid"], "guid_amount")
        self.assertEqual(summary["sources"]["count"], 1)
        self.assertEqual(summary["connection_ids"], ["connection_1"])
        self.assertEqual(summary["sql_fragments"][0]["serialized_chars"], len("select * from table"))
        self.assertNotIn("select * from table", serialized)

    def test_summary_spills_oversized_full_response_to_redacted_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            projected = project_dashboard_response(
                dashboard_fixture(),
                response_mode="summary",
                inline_char_budget=1,
                project_root=tmp,
                run_id="projection-test",
            )
            artifact_path = Path(projected["artifact"]["path"])
            artifact_text = artifact_path.read_text(encoding="utf-8")

        self.assertEqual(projected["response_mode"], "summary")
        self.assertTrue(artifact_path.name.endswith(".full.json"))
        self.assertIn("<redacted>", artifact_text)
        self.assertNotIn("Bearer fixtureTokenValue12345", artifact_text)

    def test_sanitizer_redacts_api_keys_and_dsns_in_text_values(self):
        header_value = "abcdefghijklmnopqrstuvwxyz" + "123456"
        dsn = "postgres://user:" + "password1234567890" + "@db.example.local/app"
        payload = sanitize_response(
            {
                "message": f"X-Api-Key: {header_value}",
                "dsn": dsn,
            }
        )

        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(header_value, dumped)
        self.assertNotIn("password1234567890", dumped)
        self.assertIn("<redacted>", dumped)

    def test_summary_projection_redacts_secret_like_display_titles(self):
        fixture = dashboard_fixture()
        fixture["entry"]["displayKey"] = "Bearer fixtureSummaryTokenValue12345"
        fixture["entry"]["data"]["title"] = "Bearer fixtureSummaryTokenValue12345"

        projected = project_dashboard_response(fixture, response_mode="summary")
        dumped = json.dumps(projected["summary"], ensure_ascii=False)

        self.assertNotIn("fixtureSummaryTokenValue12345", dumped)
        self.assertIn("<redacted>", dumped)

    def test_stable_hashes_ignore_dictionary_order(self):
        self.assertEqual(stable_sha256({"b": 1, "a": 2}), stable_sha256({"a": 2, "b": 1}))

    def test_explicit_full_mode_preserves_full_access_when_within_budget(self):
        projected = project_editor_chart_response(
            editor_chart_fixture(),
            response_mode="full",
            inline_char_budget=100_000,
        )

        self.assertEqual(projected["response_mode"], "full")
        self.assertIn("response", projected)
        self.assertEqual(projected["response"]["entry"]["data"]["sources"][0]["query"], "select 1")
        self.assertEqual(projected["response"]["entry"]["data"]["config"]["api_token"], "<redacted>")

    def test_discovery_tool_defaults_to_summary_and_allows_full(self):
        original = discovery.call_read
        try:
            discovery.call_read = lambda method, payload: dashboard_fixture()
            summary = discovery.dl_get_dashboard("dash_1")
            full = discovery.dl_get_dashboard("dash_1", response_mode="full", inline_char_budget=100_000)
        finally:
            discovery.call_read = original

        self.assertEqual(summary["response_mode"], "summary")
        self.assertNotIn("response", summary)
        self.assertEqual(full["response_mode"], "full")
        self.assertIn("response", full)

    def test_mcp_tool_text_responses_are_compact_json(self):
        server = JsonRpcServer(project_root=".")
        result = server._call_tool({"name": "dl_runtime_status", "arguments": {}})
        text = result["content"][0]["text"]

        self.assertFalse(result["isError"])
        self.assertNotIn("\n", text)
        self.assertEqual(json.loads(text)["ok"], True)


if __name__ == "__main__":
    unittest.main()
