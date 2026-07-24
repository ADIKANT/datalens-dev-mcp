from __future__ import annotations

import json
import unittest


class IncidentLogHardeningV3Tests(unittest.TestCase):
    def test_negated_whole_object_delete_is_not_destructive_in_ru_or_en(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        for text in (
            "Implement the dashboard update, but do not delete objects in this step.",
            "Обнови дашборд, но не удаляй объекты на этом шаге.",
        ):
            with self.subTest(text=text):
                normalized = normalize_user_request(text)
                self.assertNotIn("delete", normalized.destructive_actions)

        self.assertIn(
            "delete",
            normalize_user_request("Delete dashboard dashboard:dashboard_12345").destructive_actions,
        )

    def test_create_readback_maps_name_to_display_key_basename(self):
        from datalens_dev_mcp.pipeline.safe_apply import (
            _write_payload_readback_comparison,
        )

        comparison = _write_payload_readback_comparison(
            method="createEditorChart",
            write_payload={
                "entry": {
                    "workbookId": "workbook_1",
                    "name": "synthetic_chart",
                    "type": "advanced-chart_node",
                    "data": {"meta": "{}", "params": "{}", "sources": "{}", "controls": "{}", "prepare": "{}"},
                }
            },
            readback={
                "entry": {
                    "entryId": "chart_1",
                    "key": "folder-id/synthetic_chart",
                    "type": "advanced-chart_node",
                    "data": {"meta": "{}", "params": "{}", "sources": "{}", "controls": "{}", "prepare": "{}"},
                }
            },
        )

        self.assertTrue(comparison["equivalent"], comparison)
        self.assertEqual(comparison["diff_paths"], [])

    def test_create_readback_reports_bounded_semantic_diff_paths(self):
        from datalens_dev_mcp.pipeline.safe_apply import (
            _write_payload_readback_comparison,
        )

        comparison = _write_payload_readback_comparison(
            method="createEditorChart",
            write_payload={"entry": {"name": "chart", "type": "advanced-chart_node", "data": {"prepare": "old"}}},
            readback={"entry": {"key": "folder/chart", "type": "advanced-chart_node", "data": {"prepare": "new"}}},
        )

        self.assertFalse(comparison["equivalent"])
        self.assertIn("$.data.prepare", comparison["diff_paths"])
        self.assertLessEqual(len(comparison["diff_paths"]), 20)

    def test_schema_projection_removes_readback_only_dashboard_fields(self):
        from datalens_dev_mcp.api.request_compiler import project_method_request

        result = project_method_request(
            "updateDashboard",
            {
                "entry": {
                    "entryId": "dashboard_1",
                    "revId": "revision_2",
                    "data": {
                        "schemeVersion": 8,
                        "counter": 1,
                        "salt": "salt",
                        "settings": {
                            "autoupdateInterval": None,
                            "maxConcurrentRequests": None,
                            "silentLoading": False,
                            "dependentSelectors": True,
                            "expandTOC": False,
                        },
                        "tabs": [],
                    },
                    "meta": {},
                    "version": 7,
                    "scope": "dashboard",
                    "key": "folder/dashboard",
                    "savedId": "saved_1",
                    "publishedId": "published_1",
                    "tenantId": "tenant_1",
                    "hidden": False,
                    "workbookId": "workbook_1",
                },
                "mode": "save",
                "tenantId": "tenant_1",
            },
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(
            set(result["payload"]["entry"]),
            {"entryId", "revId", "data", "meta"},
        )
        self.assertNotIn("tenantId", result["payload"])
        self.assertIn("/entry/version", result["dropped_paths"])
        self.assertRegex(result["final_request_sha256"], r"^[0-9a-f]{64}$")

    def test_layout_list_replacement_does_not_keep_old_items(self):
        from datalens_dev_mcp.pipeline.safe_apply import (
            apply_desired_overlay_to_fresh_readback,
        )

        result = apply_desired_overlay_to_fresh_readback(
            action={
                "action": "update_dashboard",
                "method": "updateDashboard",
                "change_scope": "layout",
                "desired_overlay": {
                    "layout": [{"i": "new_widget", "x": 0, "y": 0, "w": 12, "h": 6}]
                },
                "overlay_merge_contract": {
                    "schema_version": "2026-07-23.safe_apply_overlay_merge.v2",
                    "list_policies": {"/layout": "replace"},
                },
                "geometry_expectations": [],
            },
            planned_payload={"layout": [{"i": "new_widget", "x": 0, "y": 0, "w": 12, "h": 6}]},
            fresh_readback={"layout": [{"i": "old_widget", "x": 0, "y": 0, "w": 12, "h": 6}]},
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(
            [item["i"] for item in result["payload"]["layout"]],
            ["new_widget"],
        )
        self.assertEqual(result["summary"]["list_policies_applied"]["/layout"], "replace")

    def test_http_validation_rejection_is_confirmed_no_write(self):
        from datalens_dev_mcp.api.errors import DataLensApiError
        from datalens_dev_mcp.pipeline.safe_apply import _classify_safe_apply_error

        classified = _classify_safe_apply_error(
            DataLensApiError(
                "updateDashboard failed with HTTP 400 VALIDATION_ERROR",
                http_status=400,
                remote_code="VALIDATION_ERROR",
                request_phase="response",
                response_received=True,
            ),
            write_attempted=True,
        )

        self.assertEqual(classified["category"], "remote_rejected_no_write")
        self.assertEqual(classified["write_outcome"], "no_write")
        self.assertFalse(classified["reconciliation_required"])
        self.assertEqual(classified["http_status"], 400)

    def test_tool_boundary_rejects_unknown_arguments_before_python_call(self):
        from datalens_dev_mcp.server import JsonRpcServer

        result = JsonRpcServer(project_root=".")._call_tool(
            {
                "name": "dl_validate_object",
                "arguments": {
                    "object_type": "dashboard",
                    "payload": {},
                    "delivery_intent_text": "implement",
                },
            }
        )
        body = json.loads(result["content"][0]["text"])

        self.assertTrue(result["isError"])
        self.assertEqual(body["error"]["category"], "invalid_tool_arguments")
        self.assertEqual(body["error"]["unknown"], ["delivery_intent_text"])
        self.assertIn("payload", body["error"]["allowed"])


if __name__ == "__main__":
    unittest.main()
