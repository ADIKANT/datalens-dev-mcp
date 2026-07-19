import unittest


class ChartDecisionSchemaTests(unittest.TestCase):
    def test_packaged_schema_requires_visual_decision_contract_fields(self):
        from datalens_dev_mcp.runtime_resources import resource_json

        schema = resource_json("schemas/dataviz_chart_decision.schema.json")

        for field in ("business_question", "analytical_task", "selected_family", "selected_route", "renderer_visual_spec"):
            self.assertIn(field, schema["required"])
        self.assertEqual(
            schema["properties"]["renderer_visual_spec"]["required"],
            [
                "schema_version",
                "style_tokens",
                "encoding",
                "value_semantics",
                "formatting",
                "comparison_context",
                "responsive_layout",
                "hint_contract",
                "layout_contract",
                "runtime_constraints",
            ],
        )
        self.assertIn("negative_requirement_concepts", schema["properties"])

    def test_validator_rejects_negative_requirement_delta_selection(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        payload = decide_chart(
            chart_id="kpi",
            business_question="Current KPI metric from source dataset.",
            audience=["owner"],
            data_shape={"has_date": True},
        ).to_dict()
        self.assertTrue(validate_chart_decision_record(payload)["ok"])

        payload["selected_family"] = "kpi_value_delta"
        payload["negative_requirements_applied"] = ["NEG-implicit_period_comparison-test"]
        result = validate_chart_decision_record(payload)

        self.assertFalse(result["ok"])
        self.assertIn("previous-period negative requirement selected a comparator KPI family", result["issues"])

    def test_validator_rejects_generalized_negative_requirement_leaks(self):
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        payload = decide_chart(
            chart_id="share",
            business_question="Share of orders by status from source dataset.",
            audience=["owner"],
        ).to_dict()

        pie_payload = dict(payload)
        pie_payload["selected_family"] = "pie"
        pie_payload["negative_requirement_concepts"] = ["chart_family_pie_donut"]
        self.assertIn(
            "pie/donut negative requirement selected a forbidden family",
            validate_chart_decision_record(pie_payload)["issues"],
        )

        table_payload = dict(payload)
        table_payload["selected_family"] = "horizontal_bar"
        table_payload["selected_route"] = "editor_advanced"
        table_payload["negative_requirement_concepts"] = ["table_only_output"]
        self.assertIn(
            "table-only negative requirement selected a chart family",
            validate_chart_decision_record(table_payload)["issues"],
        )

        legend_payload = dict(payload)
        legend_payload["legend_spec"] = {"show": True}
        legend_payload["negative_requirement_concepts"] = ["legend"]
        self.assertIn(
            "legend negative requirement kept legend visible",
            validate_chart_decision_record(legend_payload)["issues"],
        )

        color_payload = dict(payload)
        color_payload["color_spec"] = {"positive": "#2e7d32", "negative": "#c62828"}
        color_payload["negative_requirement_concepts"] = ["red_green_palette"]
        self.assertIn(
            "red/green negative requirement kept semantic red-green colors",
            validate_chart_decision_record(color_payload)["issues"],
        )


if __name__ == "__main__":
    unittest.main()
