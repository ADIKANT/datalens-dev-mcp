import unittest

from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.response_projection import (
    project_connection_response,
    project_dataset_response,
    project_wizard_chart_response,
)
from datalens_dev_mcp.mcp.tools import discovery
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply, validate_safe_apply_plan
from datalens_dev_mcp.server import STANDARD_TOOL_NAMES, list_tools
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.source_diagnostics import classify_datalens_source_error


def compatible_d3_dom_entry():
    return {
        "entry": {
            "entryId": "chart_ok",
            "scope": "editor_chart",
            "data": {
                "javascript": """
module.exports = {
  render: Editor.wrapFn({
    args: [],
    fn: function(options, data) {
      const root = document.createElement('div');
      d3.select(root).append('svg').append('g').attr('class', 'layer');
      return Editor.generateHtml(root);
    }
  })
};
""",
                "html": "<div class=\"root\"></div>",
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
const html = '<h1>Roadmap</h1>'
  + '<svg><marker markerWidth="8" markerHeight="8"></marker>'
  + '<path data-series="x" marker-end="url(#m)" rel="noopener"/></svg>'
  + '<script>alert(1)</script>';
window.open('https://example.test');
ChartEditor.getSecretRuntime();
""",
            },
        }
    }


class LiveHardeningV2RuntimeContractTests(unittest.TestCase):
    def test_runtime_contract_accepts_known_compatible_d3_dom_pattern(self):
        result = validate_editor_runtime_contract(compatible_d3_dom_entry(), source="positive_fixture")

        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["rule_version"], "2026-07-21.datalens_advanced_editor_runtime.v3")
        self.assertEqual(result["performance_budgets_ms"]["ordinary_wrap_fn"], 100)

    def test_runtime_contract_blocks_roadmap_fixture_with_paths_and_lines(self):
        result = validate_editor_runtime_contract(roadmap_negative_entry(), source="roadmap_fixture")
        rules = {finding["rule"] for finding in result["findings"]}

        self.assertFalse(result["ok"])
        for required in (
            "inline_script_tag",
            "svg_marker_width",
            "svg_marker_height",
            "svg_marker_end",
            "unsupported_rel",
            "window_open",
            "unknown_runtime_call",
            "duplicate_inline_title",
        ):
            self.assertIn(required, rules)
        self.assertTrue(all(finding["path"].startswith("$.") for finding in result["findings"]))
        self.assertTrue(all(finding["line"] >= 1 for finding in result["findings"]))

    def test_runtime_contract_accepts_official_data_attrs_marker_and_set_raw_data(self):
        entry = {
            "entry": {
                "data": {
                    "javascript": """
module.exports = {
  render: Editor.wrapFn({
    args: [],
    fn: function(options, data) {
      Editor.setRawData([{id: 'route_1'}]);
      d3.select(document.createElement('svg')).append('path').attr('data-id', 'route_1').attr('d', 'M0 0');
      return Editor.generateHtml(
        '<svg><defs><marker id="arrow"></marker></defs>'
        + '<path data-id="route_1" d="M0 0"></path></svg>'
        + '<dl-tooltip data-tooltip-content="Trip count" data-tooltip-placement="top">?</dl-tooltip>'
      );
    }
  })
};
""",
                    "object_html": {
                        "tag": "svg",
                        "attrs": {"viewBox": "0 0 10 10"},
                        "children": [{"tag": "path", "attrs": {"data-id": "route_1", "d": "M0 0"}}],
                    },
                }
            }
        }

        result = validate_editor_runtime_contract(entry, source="official_positive")

        self.assertTrue(result["ok"], result["findings"])
        self.assertGreaterEqual(result["official_sanitizer"]["supported_method_count"], 18)

    def test_runtime_contract_blocks_d3_and_object_form_for_observed_runtime_attrs(self):
        entry = {
            "entry": {
                "data": {
                    "javascript": """
module.exports = {
  render: Editor.wrapFn({
    args: [],
    fn: function() {
      d3.select(document.createElement('path')).attr('marker-end', 'url(#m)').attr('rel', 'noopener');
      return Editor.generateHtml('<svg><marker markerWidth="8" markerHeight="8"></marker></svg>');
    }
  })
};
""",
                    "object_html": {"tag": "path", "attrs": {"marker-end": "url(#m)", "rel": "noopener"}},
                }
            }
        }

        result = validate_editor_runtime_contract(entry, source="observed_negative")
        rules = {finding["rule"] for finding in result["findings"]}

        self.assertFalse(result["ok"])
        self.assertLessEqual({"svg_marker_width", "svg_marker_height", "svg_marker_end", "unsupported_rel"}, rules)

    def test_runtime_contract_reports_static_performance_diagnostics(self):
        large_arg = "x" * 7000
        entry = {
            "entry": {
                "data": {
                    "javascript": f"""
module.exports = {{
  render: Editor.wrapFn({{
    args: ['{large_arg}'],
    fn: function() {{
      for (let i = 0; i < 1000000; i++) {{}}
      const rows = data.rows.flatMap((row) => [row, row]);
      return Editor.generateHtml('<div></div>');
    }}
  }})
}};
"""
                }
            }
        }

        result = validate_editor_runtime_contract(entry, source="performance_fixture")
        rules = {finding["rule"] for finding in result["findings"]}
        layers = {finding["layer"] for finding in result["findings"]}

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["blocking_findings"], 0)
        self.assertIn("performance_diagnostics", layers)
        self.assertLessEqual({"wrapfn_argument_bytes", "heavy_loop_budget_risk", "data_multiplication_budget_risk"}, rules)
        self.assertTrue(
            all(
                finding["blocking"] is False
                for finding in result["findings"]
                if finding["rule"] in rules
            )
        )

    def test_safe_apply_preflight_blocks_forbidden_editor_runtime_even_with_warning_override(self):
        plan = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {"mode": "save", **roadmap_negative_entry()},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_bad", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_bad", "branch": "saved"},
                    "runtime_contract_warning_override": True,
                    "runtime_contract_override_note": "audited unknown warning only",
                }
            ],
        )
        validation = validate_safe_apply_plan(plan)
        execution = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=object())

        self.assertFalse(validation.ok)
        self.assertIn("inline_script_tag", "\n".join(validation.issues))
        self.assertFalse(execution["executed"])
        self.assertEqual(execution["status"], "blocked")

    def test_source_request_null_query_is_not_sql_error(self):
        diagnostic = classify_datalens_source_error({"stage": "request", "query": None, "message": "Connection refused"})

        self.assertEqual(diagnostic["category"], "connection_request_refusal")
        self.assertFalse(diagnostic["is_sql_error"])

    def test_remaining_high_volume_reads_default_to_summary_projection(self):
        wizard = project_wizard_chart_response({"entry": {"entryId": "wiz_1", "data": {"large": "x" * 1000}}})
        dataset = project_dataset_response({"dataset": {"id": "ds_1", "data": {"fields": [{"name": "a"}]}}})
        connection = project_connection_response({"connection": {"id": "conn_1", "data": {"secret_token": "y0_secret"}}})

        self.assertEqual(wizard["response_mode"], "summary")
        self.assertEqual(dataset["summary_kind"], "dataset")
        self.assertEqual(connection["summary_kind"], "connection")
        self.assertNotIn("response", wizard)

    def test_discovery_wizard_dataset_connection_allow_full_mode(self):
        original = discovery.call_read
        try:
            def fake_read(method, payload):
                return {
                    "entry": {
                        "entryId": payload.get("chartId") or payload.get("datasetId") or payload.get("connectionId"),
                        "data": {"value": 1},
                    }
                }

            discovery.call_read = fake_read
            wizard = discovery.dl_get_wizard_chart("wiz_1")
            dataset = discovery.dl_get_dataset("ds_1", response_mode="full", inline_char_budget=100_000)
            connection = discovery.dl_get_connection("conn_1", response_mode="full", inline_char_budget=100_000)
        finally:
            discovery.call_read = original

        self.assertNotIn("response", wizard)
        self.assertIn("response", dataset)
        self.assertIn("response", connection)

    def test_standard_surface_contains_runtime_validation_and_compact_reads(self):
        names = {tool["name"] for tool in list_tools()}

        self.assertEqual(names, STANDARD_TOOL_NAMES)
        for required in (
            "dl_runtime_status",
            "dl_auth_probe",
            "dl_validate_editor_runtime_contract",
            "dl_snapshot_dashboard",
            "dl_read_object",
            "dl_validate_project",
            "dl_create_safe_apply_plan",
            "dl_execute_safe_apply",
            "dl_readback_and_report",
        ):
            self.assertIn(required, names)


if __name__ == "__main__":
    unittest.main()
