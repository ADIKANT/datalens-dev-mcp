import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.mcp.response_projection import dashboard_summary
from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan
from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload


def nested_tab_items_dashboard():
    return {
        "branch": "saved",
        "entry": {
            "entryId": "dash_nested_tabs",
            "workbookId": "workbook_live_hardening",
            "displayKey": "Nested tab dashboard",
            "data": {
                "tabs": [
                    {
                        "id": "tab_a",
                        "title": "Tab A",
                        "items": [
                            {"id": "widget_a_1", "type": "chart", "chartId": "chart_a_1"},
                            {"id": "widget_a_2", "type": "chart", "chartId": "chart_a_2"},
                        ],
                    },
                    {
                        "id": "tab_b",
                        "title": "Tab B",
                        "items": [
                            {"id": "widget_b_1", "type": "chart", "chartId": "chart_b_1"},
                            {"id": "widget_b_2", "type": "chart", "chartId": "chart_b_2"},
                        ],
                    },
                ],
                "links": [{"from": "selector_region", "to": "chart_b_2", "param": "region"}],
            },
        },
    }


def saved_readback_with_non_action_chart_order():
    return {
        "target": "dashboard",
        "branch": "saved",
        "dashboard": {"entry": {"entryId": "dash_saved", "revId": "dash_rev", "savedId": "dash_saved_id"}},
        "charts": [
            {
                "entry": {
                    "entryId": f"chart_{index}",
                    "scope": "editor_chart",
                    "displayKey": f"Chart {index}",
                    "revId": f"rev_{index}",
                    "savedId": f"saved_{index}",
                    "data": {"title": f"Chart {index}", "javascript": f"module.exports = {index};"},
                }
            }
            for index in (3, 1, 7, 2, 6, 5, 4)
        ],
    }


def saved_editor_chart_readback():
    return {
        "branch": "saved",
        "entry": {
            "entryId": "chart_publish",
            "scope": "editor_chart",
            "displayKey": "Publish me",
            "revId": "rev_saved",
            "savedId": "saved_snapshot",
            "data": {
                "title": "Publish me",
                "sources": [{"id": "source_1", "query": "select 1"}],
                "javascript": "module.exports = {render: () => null};",
                "css": ".root { color: #111; }",
            },
        },
    }


def failing_third_action_batch():
    return [
        {"action": "update", "method": "updateDashboard", "payload": {"dashboardId": "dash_1"}},
        {"action": "update", "method": "updateEditorChart", "payload": {"chartId": "chart_1"}},
        {"action": "update", "method": "updateEditorChart", "payload": {"chartId": "chart_2", "fail": True}},
        {"action": "update", "method": "updateEditorChart", "payload": {"chartId": "chart_3"}},
    ]


def dashboard_root_tab_and_widget_tab_fixture():
    return {
        "tabs": [{"id": "shared_tab_id", "title": "Dashboard tab", "items": ["widget_1"]}],
        "items": [
            {
                "id": "widget_1",
                "type": "chart",
                "chartId": "chart_1",
                "widgetTabs": [{"id": "shared_tab_id", "title": "Widget tab", "chartId": "chart_1"}],
            }
        ],
    }


def datalens_source_request_error():
    return {
        "ok": False,
        "stage": "request",
        "query": None,
        "status": 400,
        "message": "Source request failed before query text was available.",
    }


def advanced_editor_code_fixture():
    return {
        "html": (
            '<svg><defs><marker id="arrow" markerWidth="8" markerHeight="8">'
            '</marker></defs><path data-series="sales" marker-end="url(#arrow)" rel="noopener" /></svg>'
            "<script>console.log('inline script must be rejected')</script>"
        ),
        "javascript": "window.open('https://example.test'); document.cookie = 'x=1';",
    }


class LiveHardeningV2ReconcileTests(unittest.TestCase):
    def test_dashboard_summary_counts_items_nested_inside_dashboard_tabs(self):
        summary = dashboard_summary(nested_tab_items_dashboard())

        self.assertEqual(summary["counts"]["tabs"], 2)
        self.assertEqual(summary["counts"]["items"], 4)
        self.assertEqual(summary["counts"]["linked_objects"], 4)
        self.assertEqual(
            summary["linked_object_ids"],
            ["chart_a_1", "chart_a_2", "chart_b_1", "chart_b_2"],
        )

    def test_publish_editor_chart_plan_uses_complete_saved_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            readback_path = Path(tmp) / "chart.saved.latest.json"
            readback_path.write_text(json.dumps(saved_editor_chart_readback()), encoding="utf-8")
            plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="chart",
                object_type="editor_chart",
                saved_readback_path=str(readback_path),
                approved=True,
            )

        action = plan["actions"][0]
        self.assertEqual(action["method"], "updateEditorChart")
        self.assertEqual(action["payload"]["mode"], "publish")
        self.assertEqual(action["payload"]["entry"]["entryId"], "chart_publish")
        self.assertEqual(action["payload"]["entry"]["displayKey"], "Publish me")
        self.assertEqual(action["payload"]["entry"]["data"]["sources"][0]["query"], "select 1")

    def test_root_dashboard_tabs_do_not_collide_with_widget_tabs(self):
        result = validate_dashboard_payload(dashboard_root_tab_and_widget_tab_fixture())
        errors = [issue.to_dict() for issue in result.issues if issue.severity == "error"]

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
