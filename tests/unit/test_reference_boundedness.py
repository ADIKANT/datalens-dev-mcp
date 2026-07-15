import tempfile
import unittest


class ReferenceBoundednessTests(unittest.TestCase):
    def test_new_reference_modes_are_bounded_and_do_not_spill_for_compact_limits(self):
        from datalens_dev_mcp.knowledge.reference import build_reference_response

        modes = [
            "chart_selection",
            "route_selection",
            "renderer_contract",
            "datalens_editor_runtime",
            "dashboard_system_type",
            "negative_requirements",
            "delivery_intent",
            "delivery_approval",
            "target_lock",
            "object_granularity",
            "selector_layout",
            "native_table",
            "kpi_indicator",
            "source_route",
            "visual_quality",
            "performance_budget",
            "repo_size",
            "api_contract",
            "current_docs_delta",
            "tool_selection",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for mode in modes:
                with self.subTest(mode=mode):
                    response = build_reference_response(mode=mode, query="kpi", max_chars=6000, project_root=tmp)
                    self.assertTrue(response["ok"])
                    self.assertEqual(response["mode"], mode)
                    self.assertLessEqual(response["response_chars"], 6000)
                    self.assertIn("summary", response)
                    self.assertIn("exact_next_tools", response)
                    self.assertIn("artifact_paths", response)
                    self.assertLessEqual(len(response["rules"]), 5)
                    self.assertEqual(response["reference_date"], "2026-06-30")
                    self.assertNotIn("spilled", response)

    def test_project_context_compatibility_path_never_reads_or_spills(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_load_project_context, dl_start_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            dl_start_pipeline(tmp, dashboard_name="Bounded Context")
            response = dl_load_project_context(tmp)
            artifact_response = dl_load_project_context(tmp, response_mode="artifact")

        self.assertTrue(response["deprecated"])
        self.assertTrue(response["internal_compatibility_only"])
        self.assertEqual(artifact_response["response_mode"], "artifact")
        self.assertNotIn("startup_packet", artifact_response)

    def test_current_docs_reference_modes_return_artifact_pointers(self):
        from datalens_dev_mcp.knowledge.reference import build_reference_response

        with tempfile.TemporaryDirectory() as tmp:
            docs_delta = build_reference_response(mode="current_docs_delta", max_chars=6000, project_root=tmp)
            api_contract = build_reference_response(mode="api_contract", max_chars=6000, project_root=tmp)

        self.assertIn("docs/datalens/current_docs_reconciliation.md", docs_delta["artifact_paths"])
        self.assertIn("config/datalens_docs_feature_policy.json", docs_delta["documentation_paths"])
        self.assertIn("dl_reference(mode='api_contract')", docs_delta["exact_next_tools"])
        self.assertIn("docs/datalens/api_contract_coverage.md", api_contract["artifact_paths"])
        self.assertIn("config/datalens_api_operation_policy.json", api_contract["documentation_paths"])
        self.assertIn("dl_get_api_method_schema", api_contract["exact_next_tools"])


if __name__ == "__main__":
    unittest.main()
