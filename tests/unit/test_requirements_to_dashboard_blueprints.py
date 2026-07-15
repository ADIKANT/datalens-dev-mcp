import tempfile
import unittest
from pathlib import Path


class RequirementsToDashboardBlueprintsTests(unittest.TestCase):
    def test_raw_requirement_produces_type_chart_plan_metrics_selectors_and_plan(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import (
            build_dashboard_blueprint_plan,
            ingest_requirements_markdown,
        )

        markdown = """
# Customer Experiment Dashboard
- Audience users: product owners and analysts
- Decision action: rollout or stop experiment
- Metric KPI: conversion rate
- Metric guardrail: support tickets
- Dataset table: mart.experiment_metrics
- Source freshness: daily
- Data quality caveat: late events can move for 2 days
- Selector filter control: cohort
- Selector filter control: period
- Chart visual: experiment report with cohorts and rollout decision
"""
        with tempfile.TemporaryDirectory() as tmp:
            ingest = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name="REQ-exp")
            plan = build_dashboard_blueprint_plan(tmp)
            root = Path(tmp) / "requirements"
            implementation = (root / "implementation_plan.md").read_text(encoding="utf-8")

            self.assertTrue(ingest["ok"])
            self.assertEqual(ingest["dashboard_blueprint"]["dashboard_type"], "experiment_report")
            self.assertEqual(
                ingest["dashboard_blueprint"]["schema_version"],
                "2026-07-13.dashboard_blueprint_selection.v2",
            )
            self.assertEqual(plan["schema_version"], "2026-07-13.requirements_dashboard_blueprint_plan.v2")
            self.assertEqual(plan["dashboard_type"], "experiment_report")
            self.assertTrue(plan["chart_plan"])
            self.assertIn("conversion rate", (root / "metrics.md").read_text(encoding="utf-8"))
            self.assertIn("cohort", (root / "selectors.md").read_text(encoding="utf-8"))
            self.assertIn("Dashboard Blueprint", implementation)
            self.assertIn("experiment_report", implementation)
            self.assertIn("Draft Chart Plan", implementation)
            self.assertEqual(plan["critical_questions"], [])

    def test_sparse_requirement_returns_critical_questions(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import build_dashboard_blueprint_plan, ingest_requirements_markdown

        with tempfile.TemporaryDirectory() as tmp:
            ingest_requirements_markdown(tmp, markdown_text="Need a dashboard.", source_name="REQ-sparse")
            plan = build_dashboard_blueprint_plan(tmp)

            self.assertGreaterEqual(len(plan["critical_questions"]), 3)
            self.assertTrue(any("audience" in question.lower() for question in plan["critical_questions"]))

    def test_mcp_dashboard_blueprint_tool_is_registered(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"] for tool in list_tools("dashboard")}
        default_tools = {tool["name"] for tool in list_tools()}

        self.assertIn("dl_build_dashboard_blueprint_plan", tools)
        self.assertNotIn("dl_build_dashboard_blueprint_plan", default_tools)


if __name__ == "__main__":
    unittest.main()
