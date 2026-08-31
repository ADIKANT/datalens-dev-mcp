import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.mcp.tools.pipeline import dl_generate_editor_bundle


class EditorBundleBatchTests(unittest.TestCase):
    COMPARISON_CONTEXT = {
        "method": "Previous equal-length period",
        "selected_range": "2026-07-01 to 2026-07-28",
        "comparison_range": "2026-06-03 to 2026-06-30",
    }

    @staticmethod
    def _write_brief(
        root: Path,
        *,
        decisions: list[dict],
        fields: list[str] | None = None,
    ) -> None:
        artifact_dir = root / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        brief = {
            "dashboard_name": "Synthetic operations dashboard",
            "dashboard_type": "overview",
            "audience": ["analyst"],
            "requirements": [{"text": "Show synthetic operational metrics."}],
            "data_contract": {
                "contract_id": "DATA-001",
                "fields": fields or ["bucket", "category", "value"],
            },
            "chart_decisions": decisions,
        }
        (artifact_dir / "dashboard_brief.json").write_text(
            json.dumps(brief, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _bundle(result: dict) -> dict:
        return json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8"))

    @staticmethod
    def _comparison_decisions(*, second_context: bool = False) -> list[dict]:
        decisions = [
            {
                "widget_id": "period_selector",
                "title": "Synthetic period",
                "family": "date_range_selector",
                "route": "editor_js_control",
            },
            {
                "widget_id": "delta_kpi",
                "title": "Synthetic delta",
                "family": "kpi_value_delta",
                "route": "editor_advanced",
            },
            {
                "widget_id": "comparison_context",
                "title": "Synthetic comparison context",
                "family": "md_methodology_block",
                "route": "editor_markdown",
            },
        ]
        if second_context:
            decisions.append(
                {
                    "widget_id": "comparison_context_duplicate",
                    "title": "Duplicate synthetic comparison context",
                    "family": "md_methodology_block",
                    "route": "editor_markdown",
                }
            )
        return decisions

    @classmethod
    def _comparison_specs(
        cls,
        *,
        context: dict | None = None,
        second_context: bool = False,
    ) -> list[dict]:
        specs = [
            {
                "widget_id": "period_selector",
                "selector_contract": {
                    "param_from": "period_from",
                    "param_to": "period_to",
                    "label": "Period",
                    "option_source": "none",
                    "default_from": "2026-07-01",
                    "default_to": "2026-07-28",
                    "reset_behavior": "initial",
                },
            },
            {
                "widget_id": "comparison_context",
                **(
                    {"comparison_context": dict(context)}
                    if context is not None
                    else {}
                ),
            },
            {
                "widget_id": "delta_kpi",
                "dataset_alias": "metric_source",
                "columns": ["current_value", "comparator_value"],
            },
        ]
        if second_context:
            specs.append(
                {
                    "widget_id": "comparison_context_duplicate",
                    "comparison_context": dict(context or cls.COMPARISON_CONTEXT),
                }
            )
        return specs

    def _assert_no_batch_generation_artifacts(self, root: Path) -> None:
        self.assertEqual(list(root.glob("dashboard/*/bundle.json")), [])
        self.assertEqual(
            list(root.glob("artifacts/*.wizard_payload_plan.json")),
            [],
        )
        self.assertFalse(
            (root / "artifacts" / "dashboard_object_relations.json").exists()
        )
        self.assertFalse(
            (root / "artifacts" / "editor_bundle_batch.json").exists()
        )
        self.assertFalse(
            (root / "artifacts" / "browser_qa" / "dashboard_batch.plan.json").exists()
        )

    def test_batch_uses_exact_decision_and_widget_specific_route_family_dataset(self):
        decisions = [
            {
                "decision_id": "CD-001",
                "widget_id": "trend_widget",
                "title": "Synthetic trend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
            {
                "decision_id": "CD-002",
                "widget_id": "table_widget",
                "title": "Synthetic detail",
                "family": "table_node",
                "route": "editor_table",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(root, decisions=decisions)

            batch = dl_generate_editor_bundle(
                project_root=tmp,
                chart_specs=[
                    {
                        "widget_id": "table_widget",
                        "dataset_alias": "table_source",
                        "columns": ["category", "value"],
                    },
                    {
                        "widget_id": "trend_widget",
                        "dataset_alias": "trend_source",
                        "columns": ["bucket", "value"],
                    },
                ],
            )
            results = {
                item["widget_id"]: item
                for item in batch["results"]
            }
            table_bundle = self._bundle(results["table_widget"])
            trend_bundle = self._bundle(results["trend_widget"])

        self.assertTrue(batch["ok"], batch)
        self.assertEqual(
            [item["widget_id"] for item in batch["results"]],
            ["table_widget", "trend_widget"],
        )
        self.assertEqual(
            (results["table_widget"]["family"], results["table_widget"]["route"]),
            ("table_node", "editor_table"),
        )
        self.assertEqual(
            (results["trend_widget"]["family"], results["trend_widget"]["route"]),
            ("line_chart", "editor_advanced"),
        )
        self.assertEqual(table_bundle["display_title"], "Synthetic detail")
        self.assertEqual(trend_bundle["display_title"], "Synthetic trend")
        self.assertEqual(
            table_bundle["source_contract"]["dataset_alias"],
            "table_source",
        )
        self.assertEqual(
            trend_bundle["source_contract"]["dataset_alias"],
            "trend_source",
        )
        table_tabs = json.dumps(table_bundle["tabs"], ensure_ascii=False)
        trend_tabs = json.dumps(trend_bundle["tabs"], ensure_ascii=False)
        self.assertIn("table_source", table_tabs)
        self.assertNotIn("trend_source", table_tabs)
        self.assertIn("trend_source", trend_tabs)
        self.assertNotIn("table_source", trend_tabs)

    def test_batch_preflight_rejects_duplicate_and_unmatched_ids_without_artifacts(self):
        decisions = [
            {
                "widget_id": "first_widget",
                "family": "line_chart",
                "route": "editor_advanced",
            },
            {
                "widget_id": "second_widget",
                "family": "horizontal_bar",
                "route": "editor_advanced",
            },
        ]
        cases = {
            "duplicate": (
                [
                    {"widget_id": "first_widget"},
                    {"widget_id": "first_widget"},
                ],
                "duplicate widget_id",
            ),
            "unmatched": (
                [
                    {
                        "widget_id": "first_widget",
                        "dataset_alias": "first_source",
                        "columns": ["bucket", "value"],
                    },
                    {"widget_id": "missing_widget"},
                ],
                "no chart decision matches",
            ),
        }
        for case, (specs, error_pattern) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_brief(root, decisions=decisions)

                with self.assertRaisesRegex(ValueError, error_pattern):
                    dl_generate_editor_bundle(
                        project_root=tmp,
                        chart_specs=specs,
                    )

                self.assertEqual(
                    list(root.glob("dashboard/*/bundle.json")),
                    [],
                )
                self.assertEqual(
                    list(root.glob("artifacts/*.wizard_payload_plan.json")),
                    [],
                )
                self.assertFalse(
                    (root / "artifacts" / "dashboard_object_relations.json").exists()
                )
                self.assertFalse(
                    (root / "artifacts" / "editor_bundle_batch.json").exists()
                )
                self.assertFalse(
                    (root / "artifacts" / "browser_qa" / "dashboard_batch.plan.json").exists()
                )

    def test_batch_preserves_widget_specific_render_overrides(self):
        decisions = [
            {
                "widget_id": "compact_widget",
                "title": "Compact synthetic trend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
            {
                "widget_id": "comfortable_widget",
                "title": "Comfortable synthetic trend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                decisions=decisions,
                fields=["bucket", "value"],
            )

            batch = dl_generate_editor_bundle(
                project_root=tmp,
                authoring_profile="standard_dashboard",
                chart_specs=[
                    {
                        "widget_id": "compact_widget",
                        "dataset_alias": "compact_source",
                        "columns": ["bucket", "value"],
                        "render_overrides": {"density": "compact"},
                    },
                    {
                        "widget_id": "comfortable_widget",
                        "dataset_alias": "comfortable_source",
                        "columns": ["bucket", "value"],
                        "render_overrides": {"density": "comfortable"},
                    },
                ],
            )
            results = {
                item["widget_id"]: item
                for item in batch["results"]
            }
            compact_bundle = self._bundle(results["compact_widget"])
            comfortable_bundle = self._bundle(results["comfortable_widget"])

        self.assertTrue(batch["ok"], batch)
        self.assertEqual(
            compact_bundle["render_contract"]["overrides"],
            {"density": "compact"},
        )
        self.assertEqual(
            comfortable_bundle["render_contract"]["overrides"],
            {"density": "comfortable"},
        )
        self.assertEqual(
            compact_bundle["render_contract"]["effective_tokens"]["density"]["active_variant"],
            "compact",
        )
        self.assertEqual(
            comfortable_bundle["render_contract"]["effective_tokens"]["density"]["active_variant"],
            "normal",
        )
        self.assertNotEqual(
            results["compact_widget"]["render_contract_sha256"],
            results["comfortable_widget"]["render_contract_sha256"],
        )
        self.assertNotEqual(
            results["compact_widget"]["compiled_tabs_sha256"],
            results["comfortable_widget"]["compiled_tabs_sha256"],
        )
        self.assertEqual(
            compact_bundle["source_contract"]["dataset_alias"],
            "compact_source",
        )
        self.assertEqual(
            comfortable_bundle["source_contract"]["dataset_alias"],
            "comfortable_source",
        )
        self.assertEqual(
            batch["browser_render_contract"]["per_widget_density"],
            {
                "compact_widget": {
                    "override": "compact",
                    "mode": "compact",
                    "active_variant": "compact",
                },
                "comfortable_widget": {
                    "override": "comfortable",
                    "mode": "comfortable",
                    "active_variant": "normal",
                },
            },
        )

    def test_batch_aggregates_late_horizontal_scroll_contract_into_browser_qa(self):
        decisions = [
            {
                "widget_id": "trend_first",
                "title": "Synthetic trend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
            {
                "widget_id": "ranking_second",
                "title": "Synthetic ranking",
                "family": "horizontal_bar",
                "route": "editor_advanced",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                decisions=decisions,
                fields=["bucket", "label", "value"],
            )

            batch = dl_generate_editor_bundle(
                project_root=tmp,
                authoring_profile="standard_dashboard",
                chart_specs=[
                    {
                        "widget_id": "trend_first",
                        "dataset_alias": "trend_source",
                        "columns": ["bucket", "value"],
                    },
                    {
                        "widget_id": "ranking_second",
                        "dataset_alias": "ranking_source",
                        "columns": ["label", "value"],
                        "render_overrides": {"horizontal_adapter": "scroll"},
                    },
                ],
            )
            qa_plan = json.loads(
                Path(batch["browser_qa_plan"]["artifact_path"]).read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(batch["ok"], batch)
        self.assertEqual(
            batch["browser_render_contract"]["horizontal_scroll_widget_ids"],
            ["ranking_second"],
        )
        self.assertTrue(qa_plan["render_contract"]["horizontal_rank"]["scroll"])
        self.assertTrue(
            qa_plan["render_contract"]["horizontal_rank"][
                "stable_scrollbar_gutter"
            ]
        )
        self.assertEqual(
            qa_plan["render_contract"]["horizontal_rank"]["scroll_object_ids"],
            ["ranking_second"],
        )

    def test_batch_blocks_legacy_legend_override_without_project_overlay(self):
        decisions = [
            {
                "widget_id": "legend_default",
                "title": "Default legend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
            {
                "widget_id": "legend_readable",
                "title": "Readable legend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                decisions=decisions,
                fields=["bucket", "value"],
            )

            batch = dl_generate_editor_bundle(
                project_root=tmp,
                authoring_profile="standard_dashboard",
                chart_specs=[
                    {
                        "widget_id": "legend_default",
                        "dataset_alias": "default_source",
                        "columns": ["bucket", "value"],
                    },
                    {
                        "widget_id": "legend_readable",
                        "dataset_alias": "readable_source",
                        "columns": ["bucket", "value"],
                        "render_overrides": {
                            "legend_typography": "readable",
                        },
                    },
                ],
            )
            bundle_paths = [
                Path(item["bundle_path"])
                for item in batch["results"]
            ]
            bundle_paths_exist = all(path.is_file() for path in bundle_paths)

        self.assertFalse(batch["ok"])
        self.assertEqual(
            batch["status"],
            "blocked_partial_batch",
        )
        self.assertEqual(batch["browser_qa_plan"], {})
        self.assertFalse(bundle_paths_exist)
        self.assertTrue(
            any(
                issue.startswith(
                    "legend_readable:generation_error:invalid_dashboard_render_profile"
                )
                for issue in batch["blocking_issues"]
            ),
            batch,
        )

    def test_comparison_batch_emits_one_exact_context_bundle_and_qa_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                decisions=self._comparison_decisions(),
                fields=[
                    "period_from",
                    "period_to",
                    "current_value",
                    "comparator_value",
                ],
            )

            batch = dl_generate_editor_bundle(
                project_root=tmp,
                authoring_profile="standard_dashboard",
                chart_specs=self._comparison_specs(
                    context=self.COMPARISON_CONTEXT,
                ),
            )
            results = {
                item["widget_id"]: item
                for item in batch["results"]
            }
            bundles = {
                widget_id: self._bundle(result)
                for widget_id, result in results.items()
            }
            qa_plan = json.loads(
                Path(batch["browser_qa_plan"]["artifact_path"]).read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(batch["ok"], batch)
        self.assertEqual(
            [
                (item["widget_id"], item["family"], item["route"])
                for item in batch["results"]
            ],
            [
                (
                    "period_selector",
                    "date_range_selector",
                    "editor_js_control",
                ),
                (
                    "comparison_context",
                    "md_methodology_block",
                    "editor_markdown",
                ),
                ("delta_kpi", "kpi_value_delta", "editor_advanced"),
            ],
        )
        context_bundles = [
            widget_id
            for widget_id, bundle in bundles.items()
            if isinstance(bundle.get("comparison_context_contract"), dict)
        ]
        self.assertEqual(context_bundles, ["comparison_context"])
        self.assertEqual(
            bundles["comparison_context"]["comparison_context_contract"],
            self.COMPARISON_CONTEXT,
        )
        expected_markdown = (
            "**Comparison method:** Previous equal-length period  \n"
            "**Selected period:** 2026-07-01 to 2026-07-28  \n"
            "**Comparison period:** 2026-06-03 to 2026-06-30"
        )
        expected_assignment = (
            "const markdown = "
            + json.dumps(expected_markdown, ensure_ascii=False)
            + ";"
        )
        self.assertIn(
            expected_assignment,
            bundles["comparison_context"]["tabs"]["prepare.js"],
        )
        self.assertNotIn(
            "**Comparison method:** Previous equal-length period",
            json.dumps(bundles["period_selector"]["tabs"], ensure_ascii=False),
        )
        self.assertNotIn(
            "**Comparison method:** Previous equal-length period",
            json.dumps(bundles["delta_kpi"]["tabs"], ensure_ascii=False),
        )
        self.assertTrue(qa_plan["comparison_enabled"])
        self.assertEqual(
            qa_plan["comparison_context_object_ids"],
            ["comparison_context"],
        )
        self.assertEqual(
            qa_plan["selector_contracts"][0]["role"],
            "period",
        )
        self.assertEqual(
            qa_plan["tooltip_comparison_modes"],
            {"delta_kpi": "comparison"},
        )

    def test_comparison_preflight_blocks_invalid_context_before_writes(self):
        cases = [
            {
                "name": "missing_context",
                "decisions": self._comparison_decisions(),
                "specs": self._comparison_specs(),
                "error": "exactly one md_methodology_block",
            },
            {
                "name": "two_contexts",
                "decisions": self._comparison_decisions(second_context=True),
                "specs": self._comparison_specs(
                    context=self.COMPARISON_CONTEXT,
                    second_context=True,
                ),
                "error": "exactly one md_methodology_block",
            },
            {
                "name": "unknown_context_field",
                "decisions": self._comparison_decisions(),
                "specs": self._comparison_specs(
                    context={
                        **self.COMPARISON_CONTEXT,
                        "unexpected_period": "synthetic",
                    },
                ),
                "error": "unsupported fields",
            },
            {
                "name": "missing_context_field",
                "decisions": self._comparison_decisions(),
                "specs": self._comparison_specs(
                    context={
                        "method": self.COMPARISON_CONTEXT["method"],
                        "selected_range": self.COMPARISON_CONTEXT["selected_range"],
                    },
                ),
                "error": "requires non-empty comparison_range",
            },
            {
                "name": "period_selector_not_first",
                "decisions": self._comparison_decisions(),
                "specs": [
                    self._comparison_specs(
                        context=self.COMPARISON_CONTEXT,
                    )[1],
                    self._comparison_specs(
                        context=self.COMPARISON_CONTEXT,
                    )[0],
                    self._comparison_specs(
                        context=self.COMPARISON_CONTEXT,
                    )[2],
                ],
                "error": "date_range_selector as the first chart_spec",
            },
            {
                "name": "context_after_kpi",
                "decisions": self._comparison_decisions(),
                "specs": [
                    self._comparison_specs(
                        context=self.COMPARISON_CONTEXT,
                    )[0],
                    self._comparison_specs(
                        context=self.COMPARISON_CONTEXT,
                    )[2],
                    self._comparison_specs(
                        context=self.COMPARISON_CONTEXT,
                    )[1],
                ],
                "error": "comparison context immediately after the selector prefix",
            },
        ]
        for case in cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_brief(
                    root,
                    decisions=case["decisions"],
                    fields=[
                        "period_from",
                        "period_to",
                        "current_value",
                        "comparator_value",
                    ],
                )

                with self.assertRaisesRegex(ValueError, case["error"]):
                    dl_generate_editor_bundle(
                        project_root=tmp,
                        authoring_profile="standard_dashboard",
                        chart_specs=case["specs"],
                    )

                self._assert_no_batch_generation_artifacts(root)

    def test_period_selector_must_be_first_even_without_comparison(self):
        decisions = [
            {
                "widget_id": "period_selector",
                "title": "Synthetic period",
                "family": "date_range_selector",
                "route": "editor_js_control",
            },
            {
                "widget_id": "trend",
                "title": "Synthetic trend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
        ]
        specs = [
            {
                "widget_id": "trend",
                "dataset_alias": "trend_source",
                "columns": ["bucket", "value"],
            },
            {
                "widget_id": "period_selector",
                "selector_contract": {
                    "param_from": "period_from",
                    "param_to": "period_to",
                    "label": "Period",
                    "option_source": "none",
                    "default_from": "2026-07-01",
                    "default_to": "2026-07-28",
                    "reset_behavior": "initial",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                decisions=decisions,
                fields=["bucket", "value", "period_from", "period_to"],
            )

            with self.assertRaisesRegex(
                ValueError,
                "date_range_selector as the first chart_spec when present",
            ):
                dl_generate_editor_bundle(
                    project_root=tmp,
                    authoring_profile="standard_dashboard",
                    chart_specs=specs,
                )

            self._assert_no_batch_generation_artifacts(root)

    def test_kpi_sparklines_are_all_or_none(self):
        decisions = [
            {
                "widget_id": "plain_kpi",
                "title": "Synthetic KPI",
                "family": "kpi_value_only",
                "route": "editor_advanced",
            },
            {
                "widget_id": "sparkline_kpi",
                "title": "Synthetic KPI with trend",
                "family": "kpi_value_sparkline",
                "route": "editor_advanced",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(root, decisions=decisions)

            with self.assertRaisesRegex(
                ValueError,
                "sparklines on every KPI or on none",
            ):
                dl_generate_editor_bundle(
                    project_root=tmp,
                    authoring_profile="standard_dashboard",
                    chart_specs=[
                        {"widget_id": "plain_kpi"},
                        {"widget_id": "sparkline_kpi"},
                    ],
                )

            self._assert_no_batch_generation_artifacts(root)

    def test_batch_manifest_records_ready_and_blocked_artifact_only_results(self):
        decisions = [
            {
                "widget_id": "ready_widget",
                "title": "Ready synthetic trend",
                "family": "line_chart",
                "route": "editor_advanced",
            },
            {
                "widget_id": "blocked_widget",
                "title": "Blocked synthetic trend",
                "family": "line_chart",
                "route": "wizard_native",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                decisions=decisions,
                fields=["bucket", "value"],
            )

            batch = dl_generate_editor_bundle(
                project_root=tmp,
                chart_specs=[
                    {
                        "widget_id": "ready_widget",
                        "dataset_alias": "ready_source",
                        "columns": ["bucket", "value"],
                    },
                    {"widget_id": "blocked_widget"},
                ],
            )
            manifest = json.loads(
                Path(batch["manifest_path"]).read_text(encoding="utf-8")
            )
            serialized = json.dumps(
                batch,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            artifact_paths_exist = all(
                Path(item["bundle_path"]).is_file()
                for item in batch["results"]
            )

        self.assertFalse(batch["ok"])
        self.assertEqual(batch["status"], "blocked_partial_batch")
        self.assertEqual(
            batch["batch_summary"],
            {
                "requested_count": 2,
                "ready_count": 1,
                "blocked_count": 1,
                "single_call": True,
            },
        )
        self.assertEqual(
            [
                (item["widget_id"], item["generation_status"])
                for item in batch["results"]
            ],
            [
                ("ready_widget", "ready"),
                ("blocked_widget", "blocked_missing_source"),
            ],
        )
        self.assertEqual(manifest["results"], batch["results"])
        self.assertEqual(manifest["batch_summary"], batch["batch_summary"])
        self.assertTrue(artifact_paths_exist)
        self.assertEqual(batch["full_bundles"], "artifact_only")
        self.assertLess(len(serialized), 2_048)
        self.assertNotIn('"tabs"', serialized)
        self.assertNotIn("prepare.js", serialized)


if __name__ == "__main__":
    unittest.main()
