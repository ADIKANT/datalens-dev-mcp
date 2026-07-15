import unittest


class VisualDecisionEngineTests(unittest.TestCase):
    def test_kpi_monitoring_defaults_to_non_delta_sparkline(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart

        record = decide_chart(
            chart_id="kpi_active_users",
            business_question="Current KPI status for active users from the product dataset source.",
            audience=["ops owner"],
            dashboard_type="overview",
            data_shape={"has_date": True},
            metric_semantics={"aggregation": "count", "unit": "users"},
        )

        self.assertEqual(record.analytical_task, "kpi_monitoring")
        self.assertEqual(record.selected_family, "kpi_value_sparkline")
        self.assertEqual(record.selected_route, "editor_advanced")
        self.assertFalse(record.renderer_visual_spec.kpi_context["implicit_comparator_default"])

    def test_negative_previous_period_requirement_blocks_delta_family(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        record = decide_chart(
            chart_id="kpi_no_delta",
            business_question="Current KPI status for completed issues from the dataset source.",
            audience=["delivery lead"],
            dashboard_type="overview",
            data_shape={"has_date": True},
            requested_family="kpi_value_delta_sparkline",
            user_decisions=["Do not show previous period delta or previous value."],
        )
        payload = record.to_dict()

        self.assertEqual(record.selected_family, "kpi_value_sparkline")
        self.assertTrue(any("implicit_period_comparison" in item for item in payload["negative_requirements_applied"]))
        self.assertIn("kpi_value_delta_sparkline", {item["family"] for item in payload["rejected_families"]})
        self.assertTrue(validate_chart_decision_record(payload)["ok"])

    def test_exact_lookup_uses_wizard_flat_table_route(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart

        record = decide_chart(
            chart_id="orders_table",
            business_question="Detail table registry for order rows from the source dataset.",
            audience=["support analyst"],
            dashboard_type="self_service",
        )

        self.assertEqual(record.analytical_task, "exact_lookup")
        self.assertEqual(record.selected_family, "table_node")
        self.assertEqual(record.selected_route, "wizard_native")

    def test_negative_pie_requirement_rejects_pie_and_donut(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        record = decide_chart(
            chart_id="share_no_pie",
            business_question="Share of orders by status from the source dataset.",
            audience=["ops owner"],
            requested_family="pie",
            user_decisions=["Do not use pie for this chart."],
        )
        payload = record.to_dict()
        rejected = {item["family"] for item in payload["rejected_families"]}

        self.assertEqual(record.selected_family, "horizontal_bar")
        self.assertIn("chart_family_pie_donut", payload["negative_requirement_concepts"])
        self.assertIn("pie", rejected)
        self.assertIn("donut", rejected)
        self.assertTrue(validate_chart_decision_record(payload)["ok"])

    def test_negative_legend_requirement_disables_legend(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        record = decide_chart(
            chart_id="trend_no_legend",
            business_question="Monthly metric trend from the source dataset.",
            audience=["ops owner"],
            data_shape={"has_date": True},
            user_decisions=["Remove legend from the trend."],
        )
        payload = record.to_dict()

        self.assertFalse(record.legend_spec["show"])
        self.assertTrue(record.label_spec["direct_labels"])
        self.assertTrue(validate_chart_decision_record(payload)["ok"])

    def test_table_only_requirement_forces_wizard_table(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        record = decide_chart(
            chart_id="ranking_table_only",
            business_question="Compare order count by status from the source dataset.",
            audience=["ops owner"],
            requested_family="horizontal_bar",
            user_decisions=["Only table for this output."],
        )
        payload = record.to_dict()

        self.assertEqual(record.selected_family, "table_node")
        self.assertEqual(record.selected_route, "wizard_native")
        self.assertTrue(validate_chart_decision_record(payload)["ok"])

    def test_red_green_negative_requirement_uses_neutral_blue_orange(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        record = decide_chart(
            chart_id="plan_no_red_green",
            business_question="Current KPI metric against plan from the source dataset.",
            audience=["ops owner"],
            metric_semantics={"comparator": "plan", "semantic_direction": "declared"},
            user_decisions=["Do not use red/green semantic colors."],
        )
        payload = record.to_dict()

        self.assertFalse(record.color_spec["semantic_allowed"])
        self.assertEqual(record.color_spec["positive"], "")
        self.assertEqual(record.color_spec["negative"], "")
        self.assertEqual(record.renderer_visual_spec.style_tokens["colors"]["positive"], "")
        self.assertEqual(record.renderer_visual_spec.style_tokens["colors"]["negative"], "")
        self.assertTrue(validate_chart_decision_record(payload)["ok"])


if __name__ == "__main__":
    unittest.main()
