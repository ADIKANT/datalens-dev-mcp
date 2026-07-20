import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from datalens_dev_mcp.editor.bundle import generate_editor_bundle
from datalens_dev_mcp.knowledge.recipes import build_recipe_bundle, get_recipe, select_authoring_recipe
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract
from datalens_dev_mcp.pipeline.requirements_workspace import _critical_requirement_questions, select_dashboard_blueprint
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text
from datalens_dev_mcp.validators.uri_safety import assess_uri


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_DIR = ROOT / "templates/datalens/advanced_editor/resource_schedule_exception"


class PracticalAuthoringHardeningTests(unittest.TestCase):
    maxDiff = None

    def test_python_and_shared_js_uri_policy_match_malicious_fixtures(self):
        fixtures = [
            "https://example.test/path",
            "/local/path",
            "relative/path?x=1",
            "http://example.test/path",
            "https" + "://user:pass@example.test/path",
            "https" + "://[::1",
            "https" + "://example.test:99999/path",
            "ht^tp://example.test/path",
            "javascript:alert(1)",
            "javascript&colon;alert(1)",
            "//example.test/path",
            "https://exam\nple.test/path",
            "https://example.test\\path",
        ]
        python_allowed = [assess_uri(value).allowed for value in fixtures]
        helper = ROOT / "templates/datalens/advanced_editor/_shared/render_helpers.js"
        script = (
            "const h=require(process.argv[1]);"
            "const v=JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(v.map(x=>Boolean(h.safeUri(x)))));"
        )
        result = subprocess.run(
            ["node", "-e", script, str(helper), json.dumps(fixtures)],
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), python_allowed)
        self.assertEqual(python_allowed[:3], [True, True, True])
        self.assertTrue(all(not value for value in python_allowed[3:]))

        self.assertFalse(assess_uri("http://example.test", allow_http=False).allowed)
        self.assertTrue(assess_uri("http://example.test", allow_http=True).allowed)
        self.assertEqual(assess_uri("https" + "://user@example.test").reason, "userinfo_not_allowed")
        self.assertEqual(assess_uri("https" + "://[::1").reason, "malformed_uri")

    def test_dynamic_uri_sanitizer_must_wrap_each_expression(self):
        raw = "const unused=safeUri(other); const html=`<a href=\"${row.url}\">open</a>`;"
        mixed = "const html=`<a href=\"${safeUri(other) || row.url}\">open</a>`;"
        safe = "const html=`<a href=\"${safeUri(row.url)}\">open</a>`;"
        raw_result = validate_editor_runtime_contract({"sections": {"prepare.js": raw}})
        mixed_result = validate_editor_runtime_contract({"sections": {"prepare.js": mixed}})
        safe_result = validate_editor_runtime_contract({"sections": {"prepare.js": safe}})
        self.assertIn("dynamic_uri_without_sanitizer", {item["rule"] for item in raw_result["findings"]})
        self.assertIn("dynamic_uri_without_sanitizer", {item["rule"] for item in mixed_result["findings"]})
        self.assertNotIn("dynamic_uri_without_sanitizer", {item["rule"] for item in safe_result["findings"]})

    def test_native_table_caps_use_source_rows_and_page_size_is_strict_integer(self):
        base = {
            "route": "table_node",
            "columns": [{"id": "item", "name": "Item", "type": "text"}],
            "rows": [{"cells": [{"value": "one"}]}],
        }
        large = validate_native_table_contract(base, source_rows=20_001)
        fractional = validate_native_table_contract({**base, "page_size": 1.5})
        default = validate_native_table_contract(base)
        self.assertFalse(large.ok)
        self.assertEqual(large.checked_cell_count, 20_001)
        self.assertIn("table_cell_cap_exceeded", {item.rule for item in large.findings})
        self.assertFalse(fractional.ok)
        self.assertIn("invalid_table_page_size", {item.rule for item in fractional.findings})
        self.assertEqual(default.effective_page_size, 100)

    def test_pivot_flattens_third_header_level_and_preserves_complex_semantics(self):
        source = build_recipe_bundle("table_pivot_js")["files"]["prepare.js"]
        fixture = {
            "rows": [
                {
                    "team": "Team 10",
                    "sprint": "S1",
                    "column_group": "Release 2",
                    "metric": "v1.10.0",
                    "value": None,
                    "version": "v1.0.0",
                    "status": "open",
                },
                {
                    "team": "Team 2",
                    "sprint": "S1",
                    "column_group": "Release 2",
                    "metric": "v1.2.0",
                    "value": 0,
                    "version": "v1.0.0",
                    "status": "open",
                    "url": "javascript:alert(1)",
                    "semantic_state": "warning",
                },
                {
                    "team": "Team 2",
                    "sprint": "S1",
                    "column_group": "Release 2",
                    "metric": "v1.2.0",
                    "value": 5,
                    "version": "v1.9.0",
                    "status": "done",
                    "url": "https://example.test/v1",
                    "semantic_state": "positive",
                },
                {
                    "team": "Team 2",
                    "sprint": "S1",
                    "column_group": "Release 2",
                    "metric": "v1.2.0",
                    "value": 7,
                    "version": "v1.10.0",
                    "status": "done",
                    "url": "https://example.test/v2",
                    "semantic_state": "critical",
                },
                {
                    "team": "Team 2",
                    "sprint": "S1",
                    "column_group": "Release 2",
                    "metric": "v2.0.0",
                    "value": 3,
                    "version": "v1.0.0",
                    "status": "open",
                    "url": "javascript&colon;alert(1)",
                },
                {
                    "team": "Team 2",
                    "sprint": "S1",
                    "column_group": "Release 2",
                    "metric": "v3.0.0",
                    "value": 4,
                    "version": "v1.0.0",
                    "status": "open",
                    "url": "ht^tp://example.test/item",
                },
            ],
            "config": {},
        }
        output = self._execute_prepare(source, fixture)
        group = output["head"][2]
        self.assertTrue(group["sub"])
        self.assertTrue(all("sub" not in leaf for leaf in group["sub"]))
        self.assertEqual(
            [leaf["name"] for leaf in group["sub"]],
            ["v1.2.0 · Value", "v1.10.0 · Value", "v2.0.0 · Value", "v3.0.0 · Value"],
        )
        self.assertEqual(output["head"][0]["pinned"], True)
        self.assertEqual(output["pagination"], {"default_page_size": 100, "minimum": 1, "maximum": 200})
        self.assertEqual(output["rows"][0]["cells"][2]["value"], 7)
        self.assertEqual(output["rows"][0]["cells"][2]["link"]["href"], "https://example.test/v2")
        self.assertEqual(output["rows"][0]["cells"][2]["semanticState"], "critical")
        self.assertNotIn("link", output["rows"][0]["cells"][4])
        self.assertEqual(output["rows"][0]["cells"][4]["linkFallback"]["render_as"], "plain_text")
        self.assertNotIn("link", output["rows"][0]["cells"][5])
        self.assertEqual(output["rows"][0]["cells"][5]["linkFallback"]["render_as"], "plain_text")
        self.assertEqual(output["rows"][1]["cells"][3]["value"], "—")

    def test_reference_only_tables_are_discoverable_but_not_generated(self):
        for family in ("grouped_sticky_table_exception", "table_pivot_advanced_exception"):
            with self.subTest(family=family):
                resolution = resolve_chart_family(family)
                self.assertEqual(resolution.status, "reference_only")
                self.assertEqual(resolution.approved_alternative, "table_node")
                with self.assertRaisesRegex(ValueError, "reference-only"):
                    generate_editor_bundle(widget_id="blocked", route="editor_advanced", title="Blocked", family=family)
        selection = select_authoring_recipe("pivot sticky grouped html advanced exception", route="editor_table")
        self.assertEqual(selection["recipe_id"], "table_pivot_js")
        self.assertEqual(selection["reference_only_recipe_id"], "table_pivot_advanced_exception")

    def test_schedule_determinism_conflicts_dst_links_and_plain_text_fallback(self):
        params = self._schedule_params()
        rows = [
            self._schedule_row(
                "r2",
                "Resource 2",
                "z",
                "2026-10-25T01:30:00+02:00",
                "2026-10-25T02:30:00+01:00",
            ),
            self._schedule_row(
                "r1",
                "Resource 1",
                "b",
                "2026-10-25T02:00:00+02:00",
                "2026-10-25T03:00:00+02:00",
                link="javascript:alert(1)",
            ),
            self._schedule_row(
                "r1",
                "Resource 1",
                "a",
                "2026-10-25T01:30:00+02:00",
                "2026-10-25T02:30:00+02:00",
                link="https://example.test/a",
            ),
            self._schedule_row(
                "r1",
                "Resource 1",
                "c",
                "2026-10-25T03:00:00+02:00",
                "2026-10-25T04:00:00+02:00",
            ),
            self._schedule_row(
                "r1",
                "Resource 1",
                "cancel",
                "2026-10-25T03:15:00+02:00",
                "2026-10-25T03:45:00+02:00",
                status="cancelled",
            ),
        ]
        result = self._schedule_cases({"main": {"params": params, "rows": rows}})["main"]
        model = result["model"]
        self.assertFalse(model["required"])
        self.assertEqual([item["id"] for item in model["resources"]], ["r1", "r2"])
        r1 = model["resources"][0]["items"]
        self.assertEqual([item["itemId"] for item in r1], ["a", "b", "c", "cancel"])
        self.assertEqual([item["lane"] for item in r1[:3]], [0, 1, 0])
        self.assertEqual([item["conflict"] for item in r1], [True, True, False, False])
        self.assertEqual(r1[0]["href"], "https://example.test/a")
        self.assertEqual(r1[1]["href"], "")
        dst_item = model["resources"][1]["items"][0]
        self.assertEqual(dst_item["endMs"] - dst_item["startMs"], 2 * 60 * 60 * 1000)
        self.assertNotIn("javascript:", result["html"])
        self.assertIn("<b>b</b>", result["html"])
        self.assertNotIn('href=""', result["html"])

        http_rows = [self._schedule_row("r", "R", "http", "2026-07-13T08:00:00Z", "2026-07-13T09:00:00Z", link="http://example.test/item")]
        http_params = {**params, "allow_http_links": True}
        http = self._schedule_cases({"http": {"params": http_params, "rows": http_rows}})["http"]
        self.assertIn('href="http://example.test/item"', http["html"])

    def test_schedule_exact_default_caps_and_fail_closed_cases(self):
        params = self._schedule_params()
        self.assertEqual(
            {key: params[key] for key in ("max_rows", "max_lanes_per_resource", "max_span_days", "max_model_bytes")},
            {
                "max_rows": ["1000"],
                "max_lanes_per_resource": ["8"],
                "max_span_days": ["90"],
                "max_model_bytes": ["120000"],
            },
        )
        start = datetime(2026, 7, 13, tzinfo=timezone.utc)
        overlapping = [
            self._schedule_row("r", "R", f"item_{index}", "2026-07-13T08:00:00Z", "2026-07-13T10:00:00Z")
            for index in range(9)
        ]
        too_many = [
            self._schedule_row("r", "R", f"row_{index}", "2026-07-13T08:00:00Z", "2026-07-13T09:00:00Z")
            for index in range(1001)
        ]
        large_model = []
        for index in range(1000):
            row_start = start + timedelta(minutes=index)
            row_end = row_start + timedelta(minutes=1)
            row = self._schedule_row(
                "r",
                "R",
                f"large_{index}",
                row_start.isoformat().replace("+00:00", "Z"),
                row_end.isoformat().replace("+00:00", "Z"),
            )
            row["owner"] = "Ж" * 100
            large_model.append(row)
        cases = {
            "lane": {"params": params, "rows": overlapping},
            "rows": {"params": params, "rows": too_many},
            "span": {"params": params, "rows": [self._schedule_row("r", "R", "long", "2026-07-13T00:00:00Z", "2026-10-12T00:00:00Z")]},
            "model": {"params": params, "rows": large_model},
            "timezone": {"params": {**params, "timezone": "UTC+3"}, "rows": []},
            "interval": {"params": params, "rows": [self._schedule_row("r", "R", "bad", "2026-07-13T10:00:00Z", "2026-07-13T10:00:00Z")]},
        }
        output = self._schedule_cases(cases)
        self.assertEqual(output["lane"]["model"]["reason"], "lane_cap_exceeded")
        self.assertEqual(output["lane"]["model"]["observed"], {"resource_id": "r", "lanes": 9, "maximum": 8})
        self.assertEqual(output["rows"]["model"]["reason"], "row_cap_exceeded")
        self.assertEqual(output["span"]["model"]["reason"], "span_cap_exceeded")
        self.assertEqual(output["model"]["model"]["reason"], "model_cap_exceeded")
        self.assertGreater(output["model"]["model"]["observed"]["model_bytes"], 120000)
        self.assertEqual(output["timezone"]["model"]["reason"], "invalid_or_missing_iana_timezone")
        self.assertEqual(output["interval"]["model"]["reason"], "invalid_interval_row")

    def test_schedule_selection_is_explicit_only(self):
        explicit = select_authoring_recipe("explicit resource schedule", route="editor_advanced")
        generic = select_authoring_recipe("timeline by resource", route="editor_advanced")
        self.assertEqual(explicit["recipe_id"], "resource_schedule_exception")
        self.assertNotEqual(generic["recipe_id"], "resource_schedule_exception")

    def test_schedule_recipe_bundle_has_required_tabs_and_passes_advanced_validator(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_validate_project

        recipe = get_recipe("resource_schedule_exception")
        bundle = build_recipe_bundle("resource_schedule_exception")
        tab_names = {
            "Meta": "meta.json",
            "Params": "params.js",
            "Sources": "sources.js",
            "Controls": "controls.js",
            "Prepare": "prepare.js",
        }
        self.assertTrue(bundle["ok"], bundle)
        for required in recipe["required_tabs"]:
            self.assertIn(tab_names[required], bundle["files"])
        tabs = {name: bundle["files"][name] for name in tab_names.values()}
        validation = validate_editor_runtime_contract({"sections": tabs}, source="resource_schedule_exception")
        self.assertTrue(validation["ok"], validation["findings"])
        generated_lint = lint_editor_sql_text(
            bundle["files"]["prepare.js"],
            path="resource_schedule_exception/prepare.js",
        )
        self.assertNotIn(
            "unsafe_single_quote_regex_escape",
            {issue.rule for issue in generated_lint.issues},
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_dir = root / "dashboard" / "resource_schedule_exception"
            bundle_dir.mkdir(parents=True)
            project_bundle = {
                "route": "editor_advanced",
                "entry_type": "advanced-chart_node",
                "tabs": tabs,
            }
            (bundle_dir / "bundle.json").write_text(
                json.dumps(project_bundle, ensure_ascii=False),
                encoding="utf-8",
            )
            report = dl_validate_project(str(root))

        project_lint = report["static_sql_lint"]
        self.assertTrue(project_lint["checked_paths"], project_lint)
        self.assertNotIn(
            "unsafe_single_quote_regex_escape",
            {issue["rule"] for issue in project_lint["issues"]},
        )

    def test_operational_lifecycle_and_ux_acceptance_are_conditional(self):
        ordinary = select_dashboard_blueprint("One-off overview for a quarterly decision")
        ad_hoc = select_dashboard_blueprint("Temporary project status dashboard for a milestone and deadline")
        long_lived = select_dashboard_blueprint("Long-lived system dashboard for monthly governance")
        operational = select_dashboard_blueprint(
            "Production self-service detail table export with status alerts, mobile users, and an external API source",
            data_profile={"fields": [f"field_{index}" for index in range(10)]},
        )
        self.assertFalse(ordinary["operational_lifecycle"]["required"])
        self.assertEqual(ad_hoc["dashboard_type"], "project_ad_hoc")
        self.assertFalse(ad_hoc["operational_lifecycle"]["required"])
        self.assertTrue(long_lived["operational_lifecycle"]["required"])
        self.assertTrue(operational["operational_lifecycle"]["required"])
        self.assertEqual(operational["dashboard_type"], "self_service")
        self.assertEqual(
            {item["condition_id"] for item in operational["conditional_ux_acceptance"]["conditions"]},
            {"dense_table_or_export", "mobile_or_touch", "status_alert_or_conflict", "slow_or_external_source"},
        )
        self.assertIn("promotion_deprecation_and_retirement_rule_is_declared", operational["acceptance_checklist"])
        self.assertLessEqual(
            {"usage_analytics_mode", "adoption_metric", "review_cadence", "feedback_and_documentation_links"},
            set(operational["operational_lifecycle"]["fields"]),
        )
        ux_tokens = set(operational["conditional_ux_acceptance"]["acceptance_checklist"])
        self.assertLessEqual(
            {
                "last_refresh_is_visible",
                "owner_support_and_methodology_links_are_visible",
                "multi_filter_reset_is_available",
                "active_filter_and_cross_filter_state_are_visible",
                "navigation_targets_are_safe_and_declared",
                "limitations_and_errors_are_readable",
            },
            ux_tokens,
        )
        ordinary_questions = _critical_requirement_questions(
            "Audience owner decision metric source freshness quality overview"
        )
        self.assertFalse(any("retirement" in item.lower() for item in ordinary_questions))
        lifecycle_questions = _critical_requirement_questions(
            "Audience owner decision metric source freshness quality self-service production dashboard"
        )
        self.assertTrue(any("retirement" in item.lower() for item in lifecycle_questions))

    def _execute_prepare(self, source, fixture):
        script = (
            "const p=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "const m={exports:{}};"
            "new Function('module','exports',p.source)(m,m.exports);"
            "console.log(JSON.stringify(m.exports(p.fixture)));"
        )
        result = subprocess.run(
            ["node", "-e", script],
            input=json.dumps({"source": source, "fixture": fixture}),
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _schedule_params(self):
        return json.loads((SCHEDULE_DIR / "params.json").read_text(encoding="utf-8"))

    def _schedule_cases(self, cases):
        source = (SCHEDULE_DIR / "prepare.js").read_text(encoding="utf-8")
        source = source.replace(
            "/* __DATALENS_SHARED_STYLE_TOKENS__ */",
            (ROOT / "templates/datalens/advanced_editor/_shared/style_tokens.js").read_text(encoding="utf-8"),
        ).replace(
            "/* __DATALENS_SHARED_RENDER_HELPERS__ */",
            (ROOT / "templates/datalens/advanced_editor/_shared/render_helpers.js").read_text(encoding="utf-8"),
        )
        script = """
const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));
const output={};
for (const [name,testCase] of Object.entries(payload.cases)) {
  global.Editor={getParams:()=>testCase.params,getLoadedData:()=>({rows:testCase.rows}),wrapFn:(value)=>value,generateHtml:(value)=>value};
  const moduleObject={exports:{}};
  new Function('module','exports','Editor',payload.source)(moduleObject,moduleObject.exports,global.Editor);
  const model=moduleObject.exports.render.args[0];
  output[name]={model,html:moduleObject.exports.render.fn({},model)};
}
console.log(JSON.stringify(output));
"""
        result = subprocess.run(
            ["node", "-e", script],
            input=json.dumps({"source": source, "cases": cases}),
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def _schedule_row(resource_id, resource_name, item_id, start_at, end_at, *, status="confirmed", link=""):
        return {
            "resource_id": resource_id,
            "resource_name": resource_name,
            "item_id": item_id,
            "start_at": start_at,
            "end_at": end_at,
            "status": status,
            "owner": "owner",
            "link": link,
        }


if __name__ == "__main__":
    unittest.main()
