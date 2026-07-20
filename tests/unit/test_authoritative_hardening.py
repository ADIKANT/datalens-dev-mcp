"""Regression coverage for authoritative API and Editor contracts."""

import tempfile
import unittest

from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.tools.object_lifecycle import (
    dl_plan_object_update,
    dl_plan_guarded_dataset_update,
    dl_validate_object_payload,
)
from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract


def dataset_payload():
    return {
        "fields": [
            {"name": "vehicle_id", "guid": "vehicle_id_guid", "type": "DIMENSION"},
            {"name": "trip_count", "guid": "trip_count_guid", "type": "MEASURE"},
        ],
        "sources": [{"connectionId": "conn_1", "sourceType": "table"}],
    }


def documented_editor_runtime_entry():
    return {
        "entry": {
            "entryId": "chart_events",
            "scope": "editor_chart",
            "data": {
                "javascript": """
module.exports = {
  render: Editor.wrapFn({
    args: [],
    fn: function(options, data) {
      Editor.setRawData([{id: 'v1', value: 10}]);
      return Editor.generateHtml(`
        <svg viewBox="0 0 100 40">
          <defs>
            <marker id="arrow"></marker>
          </defs>
          <path data-id="route_1" d="M0 20 L90 20"></path>
        </svg>
        <dl-tooltip data-tooltip-content="Trip count" data-tooltip-placement="top">?</dl-tooltip>
      `);
    }
  })
};
""",
            },
        }
    }


def roadmap_negative_entry():
    return {
        "entry": {
            "entryId": "chart_bad",
            "scope": "editor_chart",
            "data": {
                "javascript": """
module.exports = {
  render: Editor.wrapFn({
    args: [],
    fn: function(options, data) {
      return Editor.generateHtml(`
        <a rel="noopener">Bad link</a>
        <svg><marker markerWidth="8" markerHeight="8"></marker><path marker-end="url(#m)"></path></svg>
        <script>alert(1)</script>
      `);
    }
  }),
  events: {click: Editor.wrapFn({args: [], fn: function() { Editor.unsupportedCall(); }})}
};
""",
            },
        }
    }


class AuthoritativeHardeningEventsTests(unittest.TestCase):
    def test_raw_dataset_payload_is_rejected_for_update_contract(self):
        raw_payload = {"datasetId": "ds", **dataset_payload()}

        result = dl_validate_object_payload("dataset", raw_payload, operation="update")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["category"], "datalens_validation_error")

    def test_dataset_update_plan_uses_authoritative_nested_request_body(self):
        implicit = dl_plan_object_update("dataset", {"datasetId": "ds", **dataset_payload()})
        plan = dl_plan_object_update("dataset", {"datasetId": "ds", **dataset_payload()}, source_adapter="canonical_object_payload")

        self.assertFalse(implicit["ok"])
        self.assertEqual(implicit["error"]["category"], "explicit_adapter_required")
        self.assertTrue(plan["ok"])
        self.assertEqual(
            plan["payload"],
            {"datasetId": "ds", "data": {"dataset": dataset_payload()}},
        )

    def test_guarded_dataset_plan_exposes_validate_and_update_payload_contracts(self):
        plan = dl_plan_guarded_dataset_update(
            "ds",
            {"revId": "rev_dataset_1", "fields": [{"name": "vehicle_id", "guid": "vehicle_id_guid"}]},
            dataset_payload(),
            workbook_id="wb",
            validate_only=False,
            delivery_intent_text="update this dataset",
        )

        self.assertTrue(plan["ok"])
        self.assertEqual(
            plan["validate_request_payload"],
            {"datasetId": "ds", "workbookId": "wb", "data": {"dataset": dataset_payload()}},
        )
        self.assertEqual(
            plan["update_request_payload"],
            {"datasetId": "ds", "data": {"dataset": dataset_payload()}},
        )

    def test_dataset_workflow_runs_validate_then_guarded_safe_apply_with_fake_client(self):
        class FakeClient:
            def __init__(self):
                self.calls = []
                self.saved = False

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "validateDataset":
                    return {"status": "ok", "datasetId": payload["datasetId"]}
                if method == "getDataset":
                    return {
                        "dataset": {
                            "datasetId": payload["datasetId"],
                            "revId": "rev_dataset_2" if self.saved else "rev_dataset_1",
                            **dataset_payload(),
                        }
                    }
                if method == "updateDataset":
                    self.saved = True
                    return {"status": "saved", "datasetId": payload["datasetId"]}
                raise AssertionError(method)

        client = FakeClient()
        with tempfile.TemporaryDirectory() as project_root:
            plan = dl_plan_guarded_dataset_update(
                "ds",
                {"revId": "rev_dataset_1", "fields": [{"name": "vehicle_id", "guid": "vehicle_id_guid"}]},
                dataset_payload(),
                workbook_id="wb",
                validate_only=False,
                execute_validation=True,
                delivery_intent_text="update this dataset",
                project_root=project_root,
                client=client,
            )
            execution = execute_safe_apply(
                plan["safe_apply_plan"], config=DataLensConfig(write_enabled=True), client=client
            )

        self.assertTrue(plan["ok"], plan.get("blocked_reasons"))
        self.assertTrue(plan["validation_result"]["ok"])
        self.assertTrue(execution["executed"], execution.get("blocked_reasons"))
        self.assertEqual(
            [method for method, _payload in client.calls],
            ["validateDataset", "getDataset", "updateDataset", "getDataset"],
        )

    def test_editor_runtime_accepts_documented_svg_tooltip_and_raw_data_api(self):
        result = validate_editor_runtime_contract(documented_editor_runtime_entry(), source="documented_runtime")

        self.assertTrue(result["ok"], result["findings"])

    def test_editor_runtime_still_blocks_roadmap_negative_runtime_code(self):
        result = validate_editor_runtime_contract(roadmap_negative_entry(), source="roadmap_negative")
        rules = {finding["rule"] for finding in result["findings"]}

        self.assertFalse(result["ok"])
        for rule in (
            "unsupported_rel",
            "svg_marker_width",
            "svg_marker_height",
            "svg_marker_end",
            "inline_script_tag",
            "unknown_runtime_call",
        ):
            self.assertIn(rule, rules)


if __name__ == "__main__":
    unittest.main()
