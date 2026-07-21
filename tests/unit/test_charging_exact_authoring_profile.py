import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from datalens_dev_mcp.editor.authoring_profiles import (
    apply_authoring_profile_bundle,
    authoring_profile_route_decision,
    resolve_authoring_profile,
)
from datalens_dev_mcp.mcp.tools.pipeline import dl_generate_editor_bundle
from datalens_dev_mcp.mcp.tools.runtime import dl_validate_editor_runtime_contract
from datalens_dev_mcp.pipeline.project_live_workflows import (
    run_project_live_dry_run,
)
from datalens_dev_mcp.runtime_resources import resource_text


class ChargingExactAuthoringProfileTests(unittest.TestCase):
    def test_profile_alias_selects_registered_editor_route_and_blocks_conflicts(self):
        profile = resolve_authoring_profile(requested_profile="charging")

        selected = authoring_profile_route_decision(profile=profile, family="line_chart")
        conflict = authoring_profile_route_decision(
            profile=profile,
            family="line_chart",
            explicit_route="wizard_native",
        )

        self.assertTrue(profile["active"])
        self.assertEqual(profile["id"], "charging_v2_exact")
        self.assertEqual(selected["route"], "editor_advanced")
        self.assertEqual(
            selected["source_template"],
            "templates/datalens/authoring_profiles/charging_v2_exact/prepare_adapter.js#line_chart",
        )
        self.assertEqual(
            selected["runtime_sha256"],
            "5f37bbd6a7012e90d0567787f006629019a852623b833eb112debe5f8f50ebf3",
        )
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["error"]["category"], "authoring_profile_route_conflict")

        unsupported = authoring_profile_route_decision(profile=profile, family="pie")
        self.assertFalse(unsupported["ok"])
        self.assertEqual(unsupported["error"]["category"], "exact_template_not_registered")

    def test_project_profile_reuses_one_fingerprinted_template_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifacts").mkdir()
            (root / ".datalens-mcp.json").write_text(
                json.dumps({"authoring_profile": {"id": "charging_v2_exact"}}),
                encoding="utf-8",
            )
            brief = {
                "dashboard_name": "Exact time series",
                "dashboard_type": "operational",
                "audience": ["operator"],
                "requirements": [{"text": "Show the trend"}],
                "data_contract": {"fields": []},
                "chart_decisions": [
                    {
                        "decision_id": "trend",
                        "title": "Exact chart title",
                        "family": "line_chart",
                        "route": "wizard_native",
                        "renderer_visual_spec": {},
                        "chart_decision_record": {
                            "selected_family": "line_chart",
                            "selected_route": "wizard_native",
                            "renderer_visual_spec": {},
                        },
                    }
                ],
            }
            (root / "artifacts" / "dashboard_brief.json").write_text(json.dumps(brief), encoding="utf-8")

            first = dl_generate_editor_bundle(
                project_root=str(root),
                widget_id="trend",
                dataset_alias="dataset",
                columns=["bucket", "value"],
            )
            second = dl_generate_editor_bundle(
                project_root=str(root),
                widget_id="trend",
                dataset_alias="dataset",
                columns=["bucket", "value"],
            )

        self.assertEqual(first["route"], "editor_advanced")
        self.assertEqual(first["display_title"], "Exact chart title")
        self.assertIn('"title":"Exact chart title"', first["tabs"]["prepare.js"])
        self.assertTrue(first["authoring_profile"]["exact_template_reused"])
        self.assertEqual(first["template_provenance"]["policy"], "exact_registered_asset")
        self.assertFalse(first["template_provenance"]["approximate_fallback_used"])
        self.assertTrue(first["template_provenance"]["canonical_runtime_embedded_verbatim"])
        self.assertEqual(first["template_provenance"]["canonical_runtime_bytes"], 93916)
        self.assertEqual(
            first["template_provenance"]["canonical_runtime_sha256"],
            "5f37bbd6a7012e90d0567787f006629019a852623b833eb112debe5f8f50ebf3",
        )
        canonical_runtime = resource_text(
            "templates/datalens/authoring_profiles/charging_v2_exact/advanced_editor_runtime.js"
        )
        self.assertEqual(first["tabs"]["prepare.js"].count(canonical_runtime), 1)
        self.assertEqual(
            first["template_provenance"]["template_asset_sha256"],
            second["template_provenance"]["template_asset_sha256"],
        )
        self.assertEqual(
            first["template_provenance"]["compiled_tabs_sha256"],
            second["template_provenance"]["compiled_tabs_sha256"],
        )

    def test_validator_accepts_javascript_paths_directories_comparisons_and_tooltips(self):
        javascript = (
            "const value = index < numericValues.length ? numericValues[index] : total > 0 ? 1 : 0;\n"
            "const chart = {tooltip: {enabled: true}};\n"
            "module.exports = {value, chart};\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            widget = root / "widgets" / "trend"
            widget.mkdir(parents=True)
            (widget / "prepare.js").write_text(javascript, encoding="utf-8")
            (widget / "meta.json").write_text('{"links": {}}', encoding="utf-8")

            direct = dl_validate_editor_runtime_contract(
                project_root=str(root),
                artifact_paths=["widgets/trend/prepare.js"],
            )
            directory = dl_validate_editor_runtime_contract(
                project_root=str(root),
                artifact_paths=["widgets/trend"],
            )

        direct_rules = {item["rule"] for item in direct.get("findings_preview") or []}
        directory_rules = {item["rule"] for item in directory.get("findings_preview") or []}
        self.assertTrue(direct["ok"])
        self.assertTrue(directory["ok"])
        self.assertNotIn("unsupported_html_tag", direct_rules | directory_rules)
        self.assertNotIn("inline_hint_ui", direct_rules | directory_rules)

    @unittest.skipUnless(shutil.which("node"), "node is required for exact Charging render probe")
    def test_exact_runtime_renders_profile_adapter_rows(self):
        profile = resolve_authoring_profile(requested_profile="charging")
        decision = authoring_profile_route_decision(profile=profile, family="line_chart")
        bundle = apply_authoring_profile_bundle(
            bundle={
                "route": "editor_advanced",
                "family": "line_chart",
                "source_template": "base",
                "tabs": {},
            },
            profile=profile,
            route_decision=decision,
            title="Canonical Charging line",
        )
        probe = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
global.Editor = {
  getLoadedData: () => ({rows: payload.rows}),
  getParam: () => [],
  getParams: () => ({}),
  wrapFn: (value) => value,
  generateHtml: (value) => value,
};
const moduleObject = {exports: {}};
new Function('module', 'exports', 'Editor', payload.source)(moduleObject, moduleObject.exports, global.Editor);
const renderer = moduleObject.exports.render;
const html = renderer.fn({width: 700, height: 320}, ...renderer.args);
process.stdout.write(html);
"""
        completed = subprocess.run(
            [str(shutil.which("node")), "-e", probe],
            input=json.dumps(
                {
                    "source": bundle["tabs"]["prepare.js"],
                    "rows": [
                        {"event": "metadata", "data": {"names": ["bucket", "value"]}},
                        {"event": "row", "data": ["2026-07-20", 12]},
                        {"event": "row", "data": ["2026-07-21", 18]},
                    ],
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Canonical Charging line", completed.stdout)
        self.assertIn("<svg", completed.stdout)

    def test_long_project_command_returns_execution_id_and_polls_without_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            (root / "scripts" / "dry.py").write_text(
                "from pathlib import Path\n"
                "import json, time\n"
                "with Path('reports/starts.txt').open('a') as handle: handle.write('start\\n')\n"
                "time.sleep(0.15)\n"
                "json.dump({'branch_status': 'dry_run', 'changed_object_counts': {'charts': 0}}, "
                "open('reports/dry.json', 'w'))\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
                "project_name": "async_test",
                "workbook_id": "workbook_1",
                "dashboard_ids": ["dashboard_1"],
                "workflows": [
                    {
                        "name": "dry",
                        "may_execute_command": True,
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry.py"],
                            "summary_path": "reports/dry.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")

            started = time.monotonic()
            first = run_project_live_dry_run(root, workflow_name="dry", execute_now=True, timeout_sec=121)
            launch_duration = time.monotonic() - started
            final = first
            for _ in range(80):
                if final["status"] != "running":
                    break
                time.sleep(0.025)
                final = run_project_live_dry_run(root, execution_id=first["execution_id"])
            replay = run_project_live_dry_run(root, execution_id=first["execution_id"])
            starts = (root / "reports" / "starts.txt").read_text(encoding="utf-8").splitlines()

        self.assertLess(launch_duration, 1.0)
        self.assertEqual(first["status"], "running")
        self.assertEqual(final["status"], "completed")
        self.assertTrue(final["ok"])
        self.assertEqual(replay["status"], "completed")
        self.assertTrue(replay["execution"]["resumed_from_state"])
        self.assertEqual(starts, ["start"])


if __name__ == "__main__":
    unittest.main()
