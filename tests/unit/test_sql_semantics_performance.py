import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive
from datalens_dev_mcp.pipeline.sql_performance import (
    analyze_aggregation_grain,
    analyze_semantic_graph,
    analyze_sql,
    build_acceptance_summary,
    build_reviewed_sql_semantic_cases,
    build_synthetic_fleet_fixture_assessment,
    build_synthetic_fleet_fixture_payload,
    dl_diagnose_impl,
    import_browser_inspector_evidence,
    plan_optimizations,
    profile_performance,
    run_reviewed_case_corpus,
    validate_payload_sql_performance,
    write_required_reports,
)
from datalens_dev_mcp.server import STANDARD_TOOL_NAMES, list_tools


class SqlSemanticsPerformanceTests(unittest.TestCase):
    def test_code_47_fixture_reports_alias_and_stale_s2t_before_live_execution(self):
        case = build_synthetic_fleet_fixture_payload()["sql_cases"][0]

        result = analyze_sql(case["sql"], source_name=case["name"], schema_contract=case["schema_contract"])
        rules = {issue["rule"] for issue in result["diagnostics"] if issue["severity"] == "error"}

        self.assertEqual(result["parser"], "tokenized_clickhouse_subset")
        self.assertIn("implicit_projected_name", rules)
        self.assertIn("stale_s2t_field", rules)
        self.assertIn("unknown_identifier", rules)
        self.assertTrue(all(issue.get("offset") is not None for issue in result["diagnostics"]))

    def test_code_48_and_wide_cte_stage_risks_are_structured(self):
        cases = build_synthetic_fleet_fixture_payload()["sql_cases"]
        code48 = analyze_sql(cases[1]["sql"], source_name=cases[1]["name"])
        history_chain = analyze_sql(cases[2]["sql"], source_name=cases[2]["name"])

        self.assertIn("correlated_join_subquery", {issue["rule"] for issue in code48["diagnostics"]})
        self.assertGreaterEqual(len(history_chain["cte_dependency_dag"]), 4)
        self.assertIn(
            "broad_history_scan_before_key_reduction",
            {issue["rule"] for issue in history_chain["diagnostics"]},
        )

    def test_aggregation_grain_blocks_code_184_and_distinct_reaggregation(self):
        payload = build_synthetic_fleet_fixture_payload()["grain_case"]

        result = analyze_aggregation_grain(payload)
        rules = {blocker["rule"] for blocker in result["blockers"]}

        self.assertFalse(result["ok"])
        self.assertIn("nested_aggregation", rules)
        self.assertIn("distinct_over_preaggregated_grain", rules)
        self.assertGreaterEqual(len(result["chart_field_matrix"]), 2)
        self.assertFalse(result["automatic_mutation"])

    def test_aggregation_grain_blocks_fanout_join_reaggregation(self):
        payload = {
            "dataset": {
                "dataset_id": "dataset_fanout",
                "fields": [{"name": "amount", "aggregation": "sum"}],
                "joins": [{"cardinality": "one_to_many", "right": "line_items"}],
            },
            "charts": [{"chart_id": "chart_1", "fields": [{"field_name": "amount", "aggregation": "sum"}]}],
        }

        result = analyze_aggregation_grain(payload)

        self.assertFalse(result["ok"])
        self.assertIn("fanout_join_reaggregation", {blocker["rule"] for blocker in result["blockers"]})

    def test_semantic_graph_tracks_guid_resolution_and_stale_source_fields(self):
        payload = build_synthetic_fleet_fixture_payload()["semantic_graph_case"]

        result = analyze_semantic_graph(payload)
        rules = {finding["rule"] for finding in result["findings"]}

        self.assertFalse(result["ok"])
        self.assertIn("unresolved_chart_field_guid", rules)
        self.assertIn("stale_source_field", rules)
        self.assertEqual(result["active_chart_count"], 18)

    def test_semantic_graph_requires_selector_target_coverage(self):
        result = analyze_semantic_graph(
            {
                "datasets": [{"dataset_id": "dataset_1", "fields": [{"name": "segment"}]}],
                "selectors": [{"selector_id": "selector_segment", "field_name": "segment"}],
            }
        )

        self.assertFalse(result["ok"])
        self.assertIn("selector_target_coverage_missing", {finding["rule"] for finding in result["findings"]})

    def test_payload_sql_preflight_runs_editor_lint_rules(self):
        result = validate_payload_sql_performance(
            {"sql": "SELECT tuple_item[1], arrayZip(extractAll(raw, 'a=(\\\\d+)'), extractAll(raw, 'b=(\\\\d+)')) FROM events"},
            source="unit",
        )

        self.assertFalse(result["ok"])
        self.assertIn("tuple_indexing", result["editor_sql_lint"]["error_rules"])
        self.assertIn("arrayzip_independent_regex_lists", result["editor_sql_lint"]["error_rules"])

    def test_performance_profiler_separates_timing_sources_and_import_contract(self):
        payload = build_synthetic_fleet_fixture_payload()["performance_case"]

        result = profile_performance(payload)
        imported = import_browser_inspector_evidence(
            {
                "chart_id": "chart_synthetic_fleet_01",
                "sha256": "fixture-signature",
                "browser_inspector": {"data_fetch_ms": 1200, "render_ms": 300},
                "source_query_sha256": "query-hash",
            }
        )

        self.assertEqual(result["coverage"]["chart_count"], 18)
        self.assertEqual(result["coverage"]["timing_unavailable_count"], 18)
        self.assertTrue(result["timing_sources_are_separated"])
        self.assertTrue(imported["ok"])
        self.assertEqual(imported["timings"][0]["source"], "browser_inspector")

    def test_optimizer_recommends_only_non_mutating_exact_safe_plans(self):
        fixture = build_synthetic_fleet_fixture_assessment()

        result = plan_optimizations(
            {
                "performance": fixture["performance"],
                **build_synthetic_fleet_fixture_payload()["grain_case"],
            }
        )

        self.assertFalse(result["automatic_mutation"])
        self.assertFalse(result["approximate_distinct_allowed"])
        self.assertFalse(result["hard_history_cap_allowed"])
        self.assertTrue(any(item["strategy"] == "blocked_unsafe_preaggregation" for item in result["recommendations"]))
        self.assertTrue(all(item["exact_vs_approximate"] != "approximate" for item in result["recommendations"]))

    def test_dl_diagnose_is_bounded_and_spills_full_evidence(self):
        case = build_synthetic_fleet_fixture_payload()["sql_cases"][0]
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_diagnose_impl(
                mode="sql",
                payload={"sql": case["sql"], "source_name": case["name"], "schema_contract": case["schema_contract"]},
                project_root=tmp,
                max_items=2,
            )
            inline = json.dumps(result, ensure_ascii=False)
            artifact = Path(result["artifact"]["path"])

        self.assertFalse(result["ok"])
        self.assertTrue(artifact.name.endswith(".json"))
        self.assertNotIn("legacy_state\n    FROM", inline)
        self.assertLessEqual(len(result["summary"]["diagnostics"]), 2)

    def test_dl_diagnose_exposes_neutral_synthetic_fixture_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_diagnose_impl(
                mode="synthetic_fleet_fixture",
                project_root=tmp,
                max_items=2,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "synthetic_fleet_fixture")

    def test_safe_apply_blocks_sql_performance_preflight_before_execution(self):
        dataset = build_synthetic_fleet_fixture_payload()["grain_case"]["dataset"]
        chart = build_synthetic_fleet_fixture_payload()["grain_case"]["charts"][0]
        plan = create_safe_apply_plan(
            project_root=".",
            approved=True,
            actions=[
                {
                    "action": "update_dataset",
                    "method": "updateDataset",
                    "payload": {"datasetId": "dataset_synthetic_fleet_events", "data": {"dataset": dataset}},
                    "fresh_read_method": "getDataset",
                    "fresh_read_payload": {"datasetId": "dataset_synthetic_fleet_events"},
                    "readback_method": "getDataset",
                    "readback_payload": {"datasetId": "dataset_synthetic_fleet_events"},
                    "readback_required": True,
                    "affected_chart_payloads": [chart],
                }
            ],
        )

        result = validate_safe_apply_plan_exhaustive(plan)

        self.assertFalse(result["ok"])
        self.assertTrue(any("nested_aggregation" in issue for issue in result["issues"]))

    def test_acceptance_summary_and_required_reports_are_green(self):
        fixture = build_synthetic_fleet_fixture_assessment()
        summary = build_acceptance_summary(
            {
                "sql_reports": fixture["sql"],
                "aggregation": fixture["aggregation"],
                "graph": fixture["semantic_graph"],
                "performance": fixture["performance"],
                "optimization": fixture["optimization"],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            reports = write_required_reports(tmp)
            chart_performance_exists = Path(reports["paths"]["chart_performance.csv"]).is_file()

        self.assertTrue(summary["ok"])
        self.assertTrue(reports["ok"])
        self.assertTrue(chart_performance_exists)

    def test_reviewed_sql_semantic_corpus_has_required_breadth_and_stability(self):
        corpus = build_reviewed_sql_semantic_cases()
        first = run_reviewed_case_corpus(corpus)
        second = run_reviewed_case_corpus(corpus)

        self.assertGreaterEqual(corpus["case_count"], 100)
        self.assertGreaterEqual(first["sql_case_count"], 100)
        self.assertGreaterEqual(first["semantic_case_count"], 20)
        self.assertTrue(first["ok"])
        self.assertEqual(first["stability_hash"], second["stability_hash"])
        self.assertEqual(first["parse_status_counts"], {"ok": first["sql_case_count"]})

    def test_standard_tool_surface_budget_contains_single_diagnostic_tool(self):
        tools = list_tools()
        names = {tool["name"] for tool in tools}

        self.assertEqual(names, STANDARD_TOOL_NAMES)
        self.assertEqual(len(tools), 38)
        compact_payload = json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":"))
        self.assertLessEqual(len(compact_payload), 34_000)
        self.assertIn("dl_diagnose", names)
        self.assertNotIn("dl_list_related_objects", names)


if __name__ == "__main__":
    unittest.main()
