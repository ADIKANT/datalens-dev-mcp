import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.pipeline.render_contract_harness import (
    build_render_contract_fixture,
    run_render_contract_fixture,
)


def prepare_source(*, header="'#ffffff'", legend="['actual']", partial="true", page_size=10):
    return f"""
module.exports = ({{Editor, loadedData, viewport, theme, state}}) => ({{
  header: {{sticky: true, background: {header}}},
  legend: {legend},
  series: [{{id: 'actual', visible: true}}],
  pagination: {{pageSize: {page_size}, pageCount: Math.ceil(loadedData.length / 10)}},
  selectors: [{{id: 'period', value: Editor.getParam('period')}}],
  emptyState: {{visible: loadedData.length === 0, expected: state.expectedEmpty === true}},
  indicators: {{partialVisible: {partial}}},
  environment: {{width: viewport.width, height: viewport.height, theme}}
}});
"""


def fixture(source):
    return build_render_contract_fixture(
        fixture_id="synthetic-editor-contract",
        prepare_source=source,
        params={"period": "current"},
        expectations={
            "legend_series": ["actual"],
            "sticky_header_opaque": True,
            "pagination_page_size": 10,
            "partial_indicator_visible": True,
            "selector_ids": ["period"],
        },
    )


class EditorContractHarnessIntegrationTests(unittest.TestCase):
    def test_light_dark_all_viewports_and_data_states_pass_without_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_render_contract_fixture(fixture(prepare_source()), project_root=tmp)
            self.assertTrue(Path(result["artifact_path"]).is_file())
        self.assertTrue(result["ok"], result["issues"][:10])
        self.assertEqual(result["case_count"], 72)
        self.assertEqual(result["proof_level"], "contract_runtime")
        self.assertFalse(result["browser_rendered"])
        self.assertTrue(any(item["state"] == "empty-expected" and item["passed"] for item in result["results"]))

    def test_transparent_sticky_header_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_render_contract_fixture(fixture(prepare_source(header="'transparent'")), project_root=tmp)
        self.assertFalse(result["ok"])
        self.assertTrue(any("sticky_header_opaque" in item for item in result["issues"]))

    def test_extra_legend_series_and_hidden_partial_indicator_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            legend = run_render_contract_fixture(
                fixture(prepare_source(legend="['actual', 'extra']")), project_root=tmp, artifact_name="legend"
            )
            partial = run_render_contract_fixture(
                fixture(prepare_source(partial="false")), project_root=tmp, artifact_name="partial"
            )
        self.assertTrue(any("legend_series_exact" in item for item in legend["issues"]))
        self.assertTrue(any("partial_indicator_visible" in item for item in partial["issues"]))

    def test_wrong_pagination_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_render_contract_fixture(fixture(prepare_source(page_size=9)), project_root=tmp)
        self.assertFalse(result["ok"])
        self.assertTrue(any("pagination_page_size" in item for item in result["issues"]))


if __name__ == "__main__":
    unittest.main()
