import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


class DashboardObjectRelationsTests(unittest.TestCase):
    def test_relation_model_declares_selector_targets_and_layout_rules(self):
        from datalens_dev_mcp.pipeline.dashboard_relations import (
            build_default_dashboard_relations,
            render_relation_summary_markdown,
            validate_dashboard_relations,
        )

        relations = build_default_dashboard_relations(
            brief={
                "dashboard_name": "Relations",
                "data_contract": {"contract_id": "DATA-001", "fields": ["segment", "value"]},
                "chart_decisions": [{"widget_id": "chart_001", "route": "editor_advanced", "family": "line_chart"}],
            },
            widget_id="widget_001",
            selector_param="segment",
        )

        selector = relations["selectors"][0]
        self.assertEqual(selector["labelPlacement"], "left")
        self.assertEqual(selector["width"], "94%")
        self.assertEqual(selector["targets"][0]["target_id"], "widget_001")
        self.assertEqual(relations["layout_blueprint"]["selector_row_width"], "94%")
        self.assertFalse(relations["widgets"][0]["native_metadata"]["hideTitle"])
        self.assertTrue(relations["widgets"][0]["native_metadata"]["enableHint"])
        self.assertTrue(validate_dashboard_relations(relations).ok)
        summary = render_relation_summary_markdown(relations)
        self.assertIn("Selector Relations", summary)
        self.assertIn("targets `widget_001`", summary)
        self.assertIn("native title", summary)
        self.assertIn("Chart And Navigation Relations", summary)

    def test_relation_validation_rejects_implicit_selector_targets(self):
        from datalens_dev_mcp.pipeline.dashboard_relations import (
            build_default_dashboard_relations,
            validate_dashboard_relations,
        )

        relations = build_default_dashboard_relations(
            brief={"dashboard_name": "Bad", "data_contract": {"fields": []}, "chart_decisions": []},
            widget_id="widget_001",
            selector_param="segment",
        )
        relations["selectors"][0]["targets"] = []
        relations["selectors"][0]["labelPlacement"] = "top"
        relations["selectors"][0]["width"] = "120px"
        relations["dashboard_filters"] = []
        relations["widgets"][0]["native_metadata"] = {"title": "", "hideTitle": True, "enableHint": True}
        result = validate_dashboard_relations(relations)

        self.assertFalse(result.ok)
        self.assertIn("selector must declare target charts/widgets", "\n".join(result.issues))
        self.assertIn("labelPlacement must be left", "\n".join(result.issues))
        self.assertIn("width must be a percentage", "\n".join(result.issues))
        self.assertIn("selector parameters without dashboard filters", "\n".join(result.issues))
        self.assertIn("native_metadata.title is required", "\n".join(result.issues))
        self.assertIn("native_metadata.hideTitle must be false", "\n".join(result.issues))

    def test_relations_do_not_invent_a_selector_without_explicit_contract(self):
        from datalens_dev_mcp.pipeline.dashboard_relations import build_default_dashboard_relations

        relations = build_default_dashboard_relations(
            brief={
                "dashboard_name": "No selector",
                "data_contract": {"fields": ["segment", "value"]},
                "chart_decisions": [{"widget_id": "chart_001", "family": "line_chart"}],
            },
            widget_id="widget_001",
        )

        self.assertEqual(relations["selectors"], [])
        self.assertEqual(relations["dashboard_filters"], [])
        self.assertNotIn("selector_segment", json.dumps(relations))

    def test_paired_date_contract_creates_two_targets_and_two_filters(self):
        from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract
        from datalens_dev_mcp.pipeline.dashboard_relations import (
            build_default_dashboard_relations,
            validate_dashboard_relations,
        )

        contract = normalize_selector_contract(
            family="date_range_selector",
            title="Period",
            selector_contract={
                "param_from": "period_from",
                "param_to": "period_to",
                "label": "Period",
                "option_source": "none",
                "default_from": "2026-01-01",
                "default_to": "__relative_0d",
                "reset_behavior": "initial",
            },
        )
        relations = build_default_dashboard_relations(
            brief={
                "dashboard_name": "Date relations",
                "data_contract": {
                    "contract_id": "DATA-001",
                    "fields": [
                        {"name": "period_from"},
                        {"name": "period_to"},
                        {"name": "value"},
                    ],
                },
                "chart_decisions": [{"widget_id": "chart_001", "family": "line_chart"}],
            },
            widget_id="widget_001",
            selector_contract=contract,
        )

        selector = relations["selectors"][0]
        self.assertEqual(selector["params"], ["period_from", "period_to"])
        self.assertEqual(selector["param_from"], "period_from")
        self.assertEqual(selector["param_to"], "period_to")
        self.assertNotIn("param", selector)
        self.assertEqual(
            [target["param"] for target in selector["targets"]],
            ["period_from", "period_to"],
        )
        self.assertEqual(
            [item["param"] for item in relations["dashboard_filters"]],
            ["period_from", "period_to"],
        )
        self.assertTrue(validate_dashboard_relations(relations).ok)
        schema = json.loads(Path("schemas/dashboard-object-relations.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(relations)), [])

    def test_public_bundle_generation_writes_paired_date_selector_relations(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_generate_editor_bundle,
            dl_start_pipeline,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), dashboard_name="Date control")
            brief = {
                "dashboard_name": "Date control",
                "dashboard_type": "overview",
                "data_contract": {
                    "contract_id": "DATA-001",
                    "fields": ["period_from", "period_to"],
                },
                "chart_decisions": [
                    {
                        "decision_id": "CD-001",
                        "widget_id": "period_control",
                        "route": "editor_js_control",
                        "family": "date_range_selector",
                    }
                ],
            }
            Path(root, "artifacts", "dashboard_brief.json").write_text(
                json.dumps(brief),
                encoding="utf-8",
            )
            bundle = dl_generate_editor_bundle(
                str(root),
                widget_id="period_control",
                route="editor_js_control",
                selector_contract={
                    "param_from": "period_from",
                    "param_to": "period_to",
                    "label": "Period",
                    "option_source": "none",
                    "default_from": "2026-01-01",
                    "default_to": "2026-01-31",
                    "reset_behavior": "initial",
                },
            )
            relations = json.loads(
                Path(root, "artifacts", "dashboard_object_relations.json").read_text(encoding="utf-8")
            )

        self.assertEqual(bundle["generation_status"], "ready")
        self.assertIn('paramFrom: "period_from"', bundle["tabs"]["controls.js"])
        self.assertEqual(relations["selectors"][0]["params"], ["period_from", "period_to"])

    def test_pipeline_writes_relation_artifacts_without_memory_bank(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_governance_brief,
            dl_build_payload_plan,
            dl_generate_editor_bundle,
            dl_ingest_requirements,
            dl_start_pipeline,
            dl_validate_project,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), dashboard_name="Relations")
            dl_ingest_requirements(str(root), requirements_text="Dashboard with trend and segment selector.")
            dl_build_governance_brief(str(root))
            dl_generate_editor_bundle(
                str(root),
                widget_id="widget_001",
                dataset_alias="relations_dataset",
                columns=["bucket", "metric", "value"],
                selector_contract={
                    "param": "segment",
                    "label": "Segment",
                    "option_source": "static",
                    "options": ["all", "new", "returning"],
                    "default_values": ["all"],
                    "reset_behavior": "initial",
                },
            )
            dl_build_payload_plan(str(root))
            (root / "datasets").mkdir()
            (root / "datasets" / "relations_fixture.sql").write_text(
                "SELECT entity_id, event_count FROM entity_events_daily\n",
                encoding="utf-8",
            )
            dashboard_payload_dir = root / "artifacts" / "dashboard_payloads"
            dashboard_payload_dir.mkdir(parents=True, exist_ok=True)
            (dashboard_payload_dir / "relations.dashboard.payload.json").write_text(
                json.dumps({"dashboardId": "dashboard_placeholder", "tabs": [], "items": []}),
                encoding="utf-8",
            )
            validation = dl_validate_project(str(root))

            self.assertEqual(validation["status"], "pass")
            self.assertTrue((root / "artifacts" / "dashboard_object_relations.json").is_file())
            self.assertFalse((root / "memory-bank").exists())

    def test_docs_and_schema_exist(self):
        for rel in [
            "docs/datalens/dashboard_object_relations.md",
            "docs/datalens/dashboard_layout_contract.md",
            "schemas/dashboard-object-relations.schema.json",
            "src/datalens_dev_mcp/assets/templates/requirements/object_relations.md",
        ]:
            with self.subTest(rel=rel):
                self.assertTrue(Path(rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
