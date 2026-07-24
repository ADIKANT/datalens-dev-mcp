import tempfile
import unittest
from pathlib import Path


class RequirementsWorkflowTests(unittest.TestCase):
    def test_initialize_creates_all_workspace_files(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import REQUIREMENTS_FILES, initialize_requirements_workspace

        with tempfile.TemporaryDirectory() as tmp:
            result = initialize_requirements_workspace(tmp)
            self.assertEqual(sorted(Path(item).name for item in result["files"]), sorted(REQUIREMENTS_FILES))
            for file_name in REQUIREMENTS_FILES:
                self.assertTrue((Path(tmp) / "requirements" / file_name).is_file(), file_name)

    def test_ingest_extracts_dashboard_sections_and_updates_plan(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        markdown = """
# Order quality dashboard
- Dataset table: mart.order_events
- Connector: analytics-prod
- Join by order_id and event_date
- Field attribute: order_type
- Metric KPI: active orders
- Page tab: Quality
- Chart visual: line trend
- Selector filter control: environment
"""
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name="REQ-017", role="dashboard")
            root = Path(tmp) / "requirements"

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["extracted"]["metrics.md"], 1)
            self.assertGreaterEqual(result["extracted"]["fields.md"], 1)
            self.assertGreaterEqual(result["extracted"]["selectors.md"], 1)
            self.assertGreaterEqual(result["extracted"]["data_architecture.md"], 1)
            self.assertIn("active orders", (root / "metrics.md").read_text(encoding="utf-8"))
            self.assertIn("order_type", (root / "fields.md").read_text(encoding="utf-8"))
            self.assertIn("environment", (root / "selectors.md").read_text(encoding="utf-8"))
            self.assertIn("Source of truth", (root / "implementation_plan.md").read_text(encoding="utf-8"))
            self.assertIn("REQ-017", (root / "change_log.md").read_text(encoding="utf-8"))

    def test_ingest_updates_chart_catalog_and_relation_docs(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        markdown = """
# Revenue dashboard
- Audience/users: regional managers
- Decision/action: rebalance regional pipeline weekly
- Dataset table: mart.sales
- Source/freshness: daily
- Data quality risks/caveats: late uploads
- Metric KPI: revenue
- Field dimension: region
- Selector filter control: sales_channel
- Chart visual: top region comparison
"""
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name="REQ-catalog", role="dashboard")
            root = Path(tmp) / "requirements"
            charts = (root / "charts.md").read_text(encoding="utf-8")
            relations = (root / "object_relations.md").read_text(encoding="utf-8")

            self.assertTrue(result["ok"])
            for column in (
                "Route",
                "Dataset",
                "Metrics",
                "Dimensions",
                "Filters",
                "Selectors",
                "Native title",
                "Native hint",
                "Source requirement",
            ):
                self.assertIn(column, charts)
            self.assertIn("Metric KPI: revenue", charts)
            self.assertIn("Field dimension: region", charts)
            self.assertIn("Selector filter control: sales_channel", charts)
            self.assertIn("<DATASET_ID>", charts)
            self.assertIn("REQ-catalog", charts)
            self.assertIn("Relation Plan From REQ-catalog", relations)
            self.assertIn("<FIELD_LIST>", relations)

    def test_user_decision_updates_decision_log_and_change_log(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import update_user_decision

        with tempfile.TemporaryDirectory() as tmp:
            result = update_user_decision(tmp, decision_text="Use saved branch readback first.", decision_id="DEC-001")
            root = Path(tmp) / "requirements"

            self.assertTrue(result["ok"])
            self.assertIn("DEC-001", (root / "user_decisions.md").read_text(encoding="utf-8"))
            self.assertIn("DEC-001", (root / "change_log.md").read_text(encoding="utf-8"))

    def test_mcp_tools_are_registered_without_sync_tools(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"] for tool in list_tools("all")}
        default_tools = {tool["name"] for tool in list_tools()}
        for required in {
            "dl_init_requirements_workspace",
            "dl_ingest_requirements_markdown",
            "dl_summarize_implementation_plan",
            "dl_validate_chart_plan_against_requirements",
        }:
            self.assertIn(required, tools)
            self.assertNotIn(required, default_tools)
        self.assertIn("dl_update_user_decision", default_tools)
        self.assertFalse(any("cache_sync" in name or name.startswith("dl_sync_") for name in default_tools))

    def test_governance_and_generation_use_persisted_requirements(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_governance_brief,
            dl_generate_editor_bundle,
            dl_ingest_requirements_markdown,
            dl_start_pipeline,
        )

        with tempfile.TemporaryDirectory() as tmp:
            dl_start_pipeline(tmp, dashboard_name="Initial")
            dl_ingest_requirements_markdown(
                tmp,
                markdown_text="# Persistent Ops Dashboard\nMetric KPI: conversion rate\nField attribute: segment\nChart visual: KPI card",
                source_name="REQ-persisted",
            )
            brief = dl_build_governance_brief(tmp)
            bundle = dl_generate_editor_bundle(tmp, widget_id="kpi_widget")

            self.assertEqual(brief["dashboard_name"], "Persistent Ops Dashboard")
            self.assertIn("requirements_context", bundle)
            self.assertIn("conversion rate", bundle["requirements_context"]["summary_preview"])
            self.assertEqual(bundle["generation_status"], "blocked_missing_source")
            self.assertFalse(bundle["ok"])
            serialized = __import__("json").dumps(bundle, sort_keys=True)
            self.assertNotIn("synthetic_dataset", serialized)
            self.assertNotIn("field_dimension", serialized)
            self.assertIn("dataset is required", bundle["validation"]["errors"])

    def test_chart_plan_validation_returns_targeted_question_for_missing_items(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown, validate_chart_plan_against_requirements

        with tempfile.TemporaryDirectory() as tmp:
            ingest_requirements_markdown(tmp, markdown_text="Metric KPI: revenue\nField attribute: month", source_name="REQ")
            result = validate_chart_plan_against_requirements(
                tmp,
                chart_plan={"metrics": ["revenue", "margin"], "fields": ["month"], "selectors": ["region"]},
            )

            self.assertFalse(result["ok"])
            self.assertIn("margin", {item["value"] for item in result["missing"]})
            self.assertIn("Missing", result["question"])

    def test_blueprint_plan_blocks_unclear_requirements_with_questions(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import build_dashboard_blueprint_plan, ingest_requirements_markdown

        with tempfile.TemporaryDirectory() as tmp:
            ingest_requirements_markdown(tmp, markdown_text="Make a dashboard with a chart.", source_name="REQ-unclear")
            plan = build_dashboard_blueprint_plan(tmp)

            self.assertTrue(plan["execution_blocked"])
            self.assertEqual(plan["block_reason"], "missing_required_requirements")
            self.assertGreater(len(plan["critical_questions"]), 0)
            self.assertIn("audience", " ".join(plan["critical_questions"]).lower())

    def test_ingest_preserves_bilingual_brd_table_rows(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        markdown = (
            """
# order operations dashboard requirements

| Dashboard name | Order Operations Dashboard |
| Main contact |  |

| Источник | Витрина | Комментарий |
| Orders | analytics.order_events | Источник для контроля качества и свежести. |

| № | tab / order | chart / use case | description | visualization type | metrics | поля / источники |
"""
            "| OPR-01 | Overview / 1 | Orders with activity | "
            "Показать заказы с событиями и оценить покрытие. | KPI card | uniqExact(order_id) | "
            "order_id; event_dttm; analytics.order_events |\n"
            "| OPR-02 | Data Quality / 1 | Attribute coverage | "
            "Проверить качество заполнения атрибутов. | editor_table | filled_rows / total_rows | "
            "attribute_nm; status_cd; analytics.order_events |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name="BRD-orders")
            root = Path(tmp) / "requirements"

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["extracted"]["charts.md"], 2)
            self.assertGreaterEqual(result["extracted"]["metrics.md"], 2)
            self.assertGreaterEqual(result["extracted"]["fields.md"], 2)
            self.assertGreaterEqual(result["extracted"]["datasets.md"], 3)
            self.assertGreaterEqual(result["extracted"]["dashboard_pages.md"], 2)
            self.assertIn("OPR-01", (root / "charts.md").read_text(encoding="utf-8"))
            self.assertIn("analytics.order_events", (root / "datasets.md").read_text(encoding="utf-8"))
            self.assertEqual(result["critical_questions"], ["Who is the audience and owner for this dashboard?"])
            self.assertEqual(result["requirement_table_diagnostics"]["chart_row_count"], 2)
            self.assertTrue(result["requirement_table_diagnostics"]["ok"])

    def test_brd_blank_metric_source_and_visualization_cells_are_blockers(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        markdown = """
- Audience users: operations owner
- Decision action: investigate missing order coverage
- Data quality risk: late events
| № | chart / use case | visualization type | metrics | поля / источники |
| CH-01 | Coverage by order |  |  |  |
"""
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name="BRD-missing")

        diagnostics = result["requirement_table_diagnostics"]
        self.assertFalse(diagnostics["ok"])
        self.assertEqual(diagnostics["chart_row_count"], 1)
        self.assertEqual(
            {item["field"] for item in diagnostics["issues"]},
            {"visualization_type", "metric", "field_or_source"},
        )
        self.assertTrue(any("CH-01" in question for question in result["critical_questions"]))

    def test_brd_field_or_source_alternatives_accept_either_populated_column(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        markdown = """
- Audience users: operations owner
- Decision action: investigate coverage
- Data quality risk: late events
| № | chart / use case | visualization type | metrics | fields | source |
| CH-01 | Coverage by order | KPI card | order_count |  | analytics.orders |
| CH-02 | Coverage by region | bar | order_count | region |  |
"""
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name="BRD-alternatives")

        diagnostics = result["requirement_table_diagnostics"]
        self.assertTrue(diagnostics["ok"], diagnostics["issues"])
        self.assertEqual(diagnostics["chart_row_count"], 2)
        self.assertFalse(any(item["field"] == "field_or_source" for item in diagnostics["issues"]))

    def test_brd_chart_tables_without_id_columns_are_still_diagnosed(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import ingest_requirements_markdown

        for source_name, header in (
            ("BRD-no-id-en", "| chart / use case | visualization type | metrics | source |"),
            ("BRD-no-id-ru", "| чарт / сценарий | тип визуализации | метрика | источник |"),
        ):
            markdown = f"""
- Audience users: operations owner
- Decision action: investigate coverage
- Data quality risk: late events
{header}
| Coverage by order |  |  |  |
"""
            with self.subTest(source_name=source_name), tempfile.TemporaryDirectory() as tmp:
                result = ingest_requirements_markdown(tmp, markdown_text=markdown, source_name=source_name)
                diagnostics = result["requirement_table_diagnostics"]

                self.assertFalse(diagnostics["ok"])
                self.assertEqual(diagnostics["chart_row_count"], 1)
                self.assertEqual(
                    {item["field"] for item in diagnostics["issues"]},
                    {"visualization_type", "metric", "field_or_source"},
                )

    def test_public_docs_and_packaged_templates_exist(self):
        for rel in [
            "docs/datalens/project_documentation_workflow.md",
            "docs/mcp/tools.md",
            "src/datalens_dev_mcp/assets/templates/requirements/README.md",
            "src/datalens_dev_mcp/assets/templates/requirements/dashboard_requirements.md",
            "src/datalens_dev_mcp/assets/templates/requirements/implementation_plan.md",
            "src/datalens_dev_mcp/assets/templates/requirements/object_relations.md",
        ]:
            self.assertTrue(Path(rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
