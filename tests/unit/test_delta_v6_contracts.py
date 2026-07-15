import unittest
from pathlib import Path


class DeltaV6BaselinePreservationTests(unittest.TestCase):
    def test_baseline_diff_blocks_active_drop_and_table_feature_loss(self):
        from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract

        baseline = {
            "tabs": [
                {
                    "id": "requests",
                    "items": [
                        {
                            "type": "widget",
                            "chartId": "request_list",
                            "title": "Request list table",
                            "links": [{"field": "request_cd", "url": "https://tracker.example/{request_cd}"}],
                            "actions": [{"kind": "open"}],
                        }
                    ],
                },
                {
                    "id": "pivot",
                    "items": [{"type": "pivot_table", "chartId": "working_pivot", "conditional_formatting": {}}],
                },
            ]
        }
        proposed = {
            "tabs": [
                {
                    "id": "requests",
                    "items": [{"type": "widget", "chartId": "request_list", "title": "Request list table"}],
                }
            ]
        }

        contract = build_baseline_diff_contract(
            dashboard_id="dash",
            workbook_id="workbook",
            baseline_source={
                "kind": "backup",
                "path": str(Path("backup") / "dashboard__dash"),
            },
            baseline_dashboard=baseline,
            proposed_dashboard=proposed,
        )

        diff_types = {row["diff_type"] for row in contract["unexpected_layout_diff"]}
        self.assertIn("removed_active_object", diff_types)
        self.assertIn("lost_table_or_pivot_features", diff_types)
        self.assertIn("broad_rebuild_or_object_drop_requires_explicit_authorization", contract["blocked_reasons"])
        self.assertIn("table_or_pivot_actionability_regressed", contract["blocked_reasons"])
        self.assertTrue(contract["preservation_policy"]["existing_object_update_first"])

    def test_create_plan_adds_creation_necessity_proof(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan

        plan = create_safe_apply_plan(
            project_root="/tmp/delta-v6",
            approved=True,
            actions=[
                {
                    "action": "create_wizard_chart",
                    "method": "createWizardChart",
                    "payload": {"mode": "save", "workbookId": "workbook"},
                }
            ],
        )

        proof = plan["actions"][0]["creation_necessity_proof"]
        self.assertEqual(proof["schema_version"], "datalens.object-creation-necessity.delta-v6")
        self.assertTrue(proof["preserve_existing_ids_default"])
        self.assertTrue(proof["cleanup_report_required_if_created"])
        self.assertIn("existing object", proof["update_insufficient_reason"])


class DeltaV6RuntimeGateTests(unittest.TestCase):
    def test_runtime_gate_fails_on_runtime_errors_and_visibility_regressions(self):
        from datalens_dev_mcp.pipeline.browser_qa import build_runtime_publish_gate, delivery_status_from_runtime_gate

        gate = build_runtime_publish_gate(
            status="passed",
            dashboard_id="dash",
            changed_object_ids=["chart_ok", "chart_missing"],
            visible_object_ids=["chart_ok"],
            proof_artifacts=["/tmp/runtime.png"],
            runtime_messages=["ERR.DS_API.FIELD.NOT_FOUND: Using non-existent field local_formula"],
            selector_statuses=[{"selector_id": "selector_a", "status": "502 Bad Gateway"}],
        )

        markers = {row["marker"] for row in gate["blocking_errors"]}
        self.assertEqual(gate["status"], "failed")
        self.assertIn("ERR.DS_API.FIELD.NOT_FOUND", markers)
        self.assertIn("changed_object_not_visible", markers)
        self.assertIn("selector_load_status", markers)
        self.assertEqual(delivery_status_from_runtime_gate(gate), "blocked")

    def test_runtime_blocker_downgrades_done_to_runtime_not_verified(self):
        from datalens_dev_mcp.pipeline.browser_qa import build_runtime_publish_gate, delivery_status_from_runtime_gate

        gate = build_runtime_publish_gate(status="browser_auth_required", dashboard_id="dash", blocked_reason="auth")

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(delivery_status_from_runtime_gate(gate), "runtime_not_verified")


class DeltaV6WizardVisualDatasetTests(unittest.TestCase):
    def test_wizard_contract_blocks_missing_partial_fields_local_formulas_and_select_star(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_visual_dataset_contract

        result = validate_wizard_visual_dataset_contract(
            {
                "route": "wizard",
                "chart_intent": "grouped side-by-side bar",
                "datasetsPartialFields": [{"guid": "used", "local_formula": True}],
                "labels": [{"guid": "missing_label"}],
                "tooltips": [{"fieldGuid": "used"}],
                "sort": [{"fieldGuid": "missing_sort"}],
                "sql": "SELECT * FROM source",
                "measures": ["planned", "actual"],
            }
        )

        rules = {finding.rule for finding in result.findings}
        self.assertFalse(result.ok)
        self.assertIn("wizard_field_ref_missing_from_datasets_partial_fields", rules)
        self.assertIn("chart_local_formula_in_datasets_partial_fields", rules)
        self.assertIn("wizard_sql_select_star_forbidden", rules)
        self.assertIn("grouped_bar_requires_tidy_category_model", rules)

    def test_renderer_defaults_satisfy_delta_v6_visual_quality(self):
        from datalens_dev_mcp.editor.visual_spec import build_renderer_visual_spec
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        spec = build_renderer_visual_spec(
            family="line_chart",
            route="editor_advanced",
            analytical_task="time_trend",
        ).to_dict()
        result = validate_visual_quality_contract(spec)

        self.assertTrue(spec["labels"]["direct_labels"])
        self.assertFalse(spec["gridlines"]["show"])
        self.assertFalse(spec["axes"]["measure_axis_title"])
        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])

    def test_visual_quality_blocks_delta_v6_label_gridline_axis_defaults(self):
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        result = validate_visual_quality_contract(
            {
                "family": "bar_chart",
                "labels": {"direct_labels": False},
                "axes": {"show": True, "zero_baseline": True, "measure_axis_title": True},
                "gridlines": {"show": True},
            }
        )

        rules = {finding.rule for finding in result.findings}
        self.assertFalse(result.ok)
        self.assertIn("delta_v6_labels_required", rules)
        self.assertIn("delta_v6_gridlines_default_off", rules)
        self.assertIn("delta_v6_measure_axis_title_default_off", rules)


class DeltaV6SourceAvailabilityTests(unittest.TestCase):
    def test_source_matrix_keeps_no_table_no_data_and_error_semantics_distinct(self):
        from datalens_dev_mcp.pipeline.source_availability import (
            build_source_availability_contract,
            effective_availability,
            source_status_label,
            validate_source_consumer_consistency,
        )

        matrix = build_source_availability_contract(
            dashboard_id="dash",
            environments=["stage", "prod"],
            sources={
                "stage_event_log": {
                    "physical_tables": ["analytics.event_log"],
                    "environments": {"stage": {"static_supported": True, "table_present": True}},
                },
                "prod_optional_events": {
                    "physical_tables": ["analytics.optional_events"],
                    "environments": {
                        "prod": {"static_supported": False, "table_present": False, "expected_exception": True}
                    },
                },
            },
        )

        empty_stage = effective_availability(matrix, "stage_event_log", "stage", row_count=0)
        prod_disabled = effective_availability(matrix, "prod_optional_events", "prod", runtime_param=["1"])
        errored = effective_availability(matrix, "stage_event_log", "stage", error="DB::Exception")
        consistency = validate_source_consumer_consistency(
            matrix,
            [{"source_key": "stage_event_log", "environment": "stage", "row_count": 0, "status": "NO TABLE"}],
        )

        self.assertEqual(source_status_label(empty_stage), "NO DATA")
        self.assertTrue(empty_stage.effective_available)
        self.assertEqual(source_status_label(prod_disabled), "NO TABLE")
        self.assertFalse(prod_disabled.runtime_available)
        self.assertEqual(source_status_label(errored), "ERROR")
        self.assertFalse(consistency["ok"])
        self.assertEqual(consistency["issues"][0]["expected_status"], "NO DATA")


class DeltaV6SelectorPerformanceTests(unittest.TestCase):
    def test_high_fanout_selector_requires_sql_filter_pushdown_and_business_grain_dedupe(self):
        from datalens_dev_mcp.pipeline.performance_budget import build_editor_source_budget_evidence

        evidence = build_editor_source_budget_evidence(
            [
                {
                    "source_key": "weekly_events",
                    "consumer_type": "selector",
                    "physical_rows_before": 10_000_000,
                    "business_grain_rows_after": 100,
                    "estimated_single_source_bytes": 1024,
                    "estimated_source_time_ms": 1000,
                }
            ],
            dashboard_id="dashboard_synthetic",
        )

        row = evidence["sources"][0]
        self.assertEqual(row["source_budget_status"], "fail")
        self.assertIn("high_fanout_selector_requires_sql_filter_pushdown", row["blocked_reasons"])
        self.assertIn("high_fanout_selector_requires_business_grain_dedupe", row["blocked_reasons"])

        fixed = build_editor_source_budget_evidence(
            [
                {
                    "source_key": "weekly_events",
                    "consumer_type": "selector",
                    "physical_rows_before": 10_000_000,
                    "business_grain_rows_after": 100,
                    "bounded_in_sql": True,
                    "deduped_to_business_grain": True,
                    "estimated_single_source_bytes": 1024,
                    "estimated_source_time_ms": 1000,
                }
            ],
            dashboard_id="dashboard_synthetic",
        )
        self.assertEqual(fixed["sources"][0]["source_budget_status"], "warn")
        self.assertEqual(fixed["sources"][0]["blocked_reasons"], [])

    def test_selector_source_without_row_budget_evidence_fails(self):
        from datalens_dev_mcp.pipeline.performance_budget import build_editor_source_budget_evidence

        evidence = build_editor_source_budget_evidence(
            [{"source_key": "weekly_events", "consumer_type": "selector", "estimated_single_source_bytes": 1024}],
            dashboard_id="dashboard_synthetic",
        )

        self.assertEqual(evidence["sources"][0]["source_budget_status"], "fail")
        self.assertIn("selector_source_budget_evidence_required", evidence["sources"][0]["blocked_reasons"])


class DeltaV6CleanupAndHandoffTests(unittest.TestCase):
    def test_cleanup_blocks_active_created_objects_and_requires_delete_readback(self):
        from datalens_dev_mcp.pipeline.object_cleanup import build_object_cleanup_report

        active = build_object_cleanup_report(
            dashboard_id="dash",
            created_objects=[{"object_id": "created_chart", "object_type": "wizard_chart", "reason": "new chart"}],
            saved_graph={"entries": [{"entry_id": "created_chart", "role": "active"}]},
            published_graph={"entries": []},
        )

        self.assertEqual(active["cleanup_actions"][0]["action"], "blocked")
        self.assertIn("active", active["cleanup_actions"][0]["error"])

        inactive = build_object_cleanup_report(
            dashboard_id="dash",
            created_objects=[{"object_id": "unused_chart", "object_type": "wizard_chart", "reason": "bad create"}],
            saved_graph={"entries": []},
            published_graph={"entries": []},
            cleanup_results=[{"object_id": "unused_chart", "action": "delete", "empty_body": True}],
        )
        self.assertEqual(inactive["cleanup_actions"][0]["action"], "delete")
        self.assertFalse(inactive["cleanup_actions"][0]["verified_absent"])
        self.assertIn("follow-up readback", inactive["cleanup_actions"][0]["error"])

        verified = build_object_cleanup_report(
            dashboard_id="dash",
            created_objects=[{"object_id": "unused_chart", "object_type": "wizard_chart", "reason": "bad create"}],
            saved_graph={"entries": []},
            published_graph={"entries": []},
            cleanup_results=[{"object_id": "unused_chart", "action": "delete", "empty_body": True, "followup_absent": True}],
        )
        self.assertTrue(verified["cleanup_actions"][0]["verified_absent"])

    def test_final_handoff_done_requires_passed_runtime_gate(self):
        from datalens_dev_mcp.pipeline.object_cleanup import build_final_handoff_contract

        not_verified = build_final_handoff_contract(
            status="done",
            dashboard_id="dash",
            changed_objects=[{"object_id": "chart", "object_type": "wizard_chart"}],
            saved_readback="artifacts/readback/saved.json",
            published_readback="artifacts/readback/published.json",
            runtime_gate={"status": "blocked", "artifact_path": "artifacts/runtime/gate.json"},
        )
        done = build_final_handoff_contract(
            status="done",
            dashboard_id="dash",
            changed_objects=[{"object_id": "chart", "object_type": "wizard_chart"}],
            saved_readback="artifacts/readback/saved.json",
            published_readback="artifacts/readback/published.json",
            runtime_gate={"status": "passed", "artifact_path": "artifacts/runtime/gate.json"},
        )

        self.assertEqual(not_verified["status"], "runtime_not_verified")
        self.assertIn("browser/runtime verification", not_verified["limitations"][0])
        self.assertEqual(done["status"], "done")


if __name__ == "__main__":
    unittest.main()
