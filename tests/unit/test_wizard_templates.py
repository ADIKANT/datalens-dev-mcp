import json
import unittest
from pathlib import Path


class WizardTemplateTests(unittest.TestCase):
    def _config(self, visualization_id, spec, *, saved_seed=None):
        bindings = {role: f"field_{index}" for index, role in enumerate(spec["required_roles"], start=1)}
        config = {
            "route": "wizard_native",
            "visualization_id": visualization_id,
            "semantic_family": spec["semantic_families"][0],
            "location": {"workbookId": "workbook_fixture", "name": f"chart_{visualization_id}"},
            "dataset": "dataset_fixture",
            "field_bindings": bindings,
        }
        if visualization_id == "geolayer":
            config["geo"] = {"evidence_kind": "geopoint", "field": bindings["geo"]}
        if saved_seed is not None:
            config["saved_seed"] = saved_seed
        return config

    def test_all_canonical_visualizations_compile(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan, load_wizard_template_registry

        registry = load_wizard_template_registry()
        self.assertEqual(len(registry["templates"]), 16)
        for visualization_id, spec in registry["templates"].items():
            with self.subTest(visualization_id=visualization_id):
                plan = build_wizard_payload_plan(self._config(visualization_id, spec))
                self.assertTrue(plan["ok"], plan.get("validation"))
                self.assertEqual(plan["route"], "wizard_native")
                self.assertEqual(plan["visualization_id"], visualization_id)
                self.assertEqual(plan["method"], "createWizardChart")
                self.assertEqual(plan["source_kind"], "committed_canonical_template")
                self.assertFalse(plan["execute_now"])
                self.assertFalse(plan["live_verification"])
                self.assertEqual(
                    plan["compiled_payload"]["data"]["visualization"]["id"],
                    visualization_id,
                )

    def test_unknown_visualization_and_bubble_without_size_are_blocked(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

        unknown = build_wizard_payload_plan(
            {
                "visualization_id": "internal-token-unknown",
                "location": {"key": "folder/chart"},
                "dataset": "dataset_fixture",
                "field_bindings": {"x": "x", "y": "y"},
            }
        )
        bubble = build_wizard_payload_plan(
            {
                "visualization_id": "scatter",
                "semantic_family": "bubble",
                "location": {"key": "folder/bubble"},
                "dataset": "dataset_fixture",
                "field_bindings": {"x": "x", "y": "y"},
            }
        )

        self.assertFalse(unknown["ok"])
        self.assertTrue(any("unsupported" in error for error in unknown["validation"]["errors"]))
        self.assertFalse(bubble["ok"])
        self.assertTrue(any("size" in error for error in bubble["validation"]["errors"]))

    def test_saved_seed_must_be_fresh_saved_and_same_visualization(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan, load_wizard_template_registry

        spec = load_wizard_template_registry()["templates"]["line"]
        base_seed = {
            "branch": "saved",
            "revId": "rev_fixture",
            "entryId": "deployment_entry_removed",
            "workbookId": "deployment_workbook_removed",
            "data": {
                "visualization": {"id": "line", "placeholders": [{"id": "x", "items": []}]},
                "unknownFutureField": {"preserve": True},
            },
        }
        good = build_wizard_payload_plan(self._config("line", spec, saved_seed=base_seed))
        wrong_branch = build_wizard_payload_plan(
            self._config("line", spec, saved_seed={**base_seed, "branch": "published"})
        )
        stale = build_wizard_payload_plan(
            self._config("line", spec, saved_seed={key: value for key, value in base_seed.items() if key != "revId"})
        )
        mismatched = build_wizard_payload_plan(
            self._config(
                "line",
                spec,
                saved_seed={**base_seed, "data": {"visualization": {"id": "bar"}}},
            )
        )

        self.assertTrue(good["ok"], good.get("validation"))
        self.assertEqual(good["source_kind"], "fresh_saved_seed")
        self.assertTrue(good["sanitized_seed"]["used"])
        self.assertNotIn("entryId", json.dumps(good["compiled_payload"]))
        self.assertNotIn("deployment_workbook_removed", json.dumps(good["compiled_payload"]))
        self.assertTrue(good["compiled_payload"]["data"]["unknownFutureField"]["preserve"])
        for blocked in (wrong_branch, stale, mismatched):
            self.assertFalse(blocked["ok"])

    def test_known_binding_types_must_match_wizard_roles(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

        invalid = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "column",
                "location": {"key": "folder/column"},
                "dataset": "dataset_fixture",
                "field_bindings": {
                    "x": {"guid": "category_guid", "type": "string"},
                    "y": {"guid": "value_guid", "type": "string"},
                },
            }
        )
        valid = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "column",
                "location": {"key": "folder/column"},
                "dataset": "dataset_fixture",
                "field_bindings": {
                    "x": {"guid": "category_guid", "type": "string"},
                    "y": {"guid": "value_guid", "type": "float"},
                },
            }
        )
        invalid_geo = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "geolayer",
                "location": {"key": "folder/map"},
                "dataset": "dataset_fixture",
                "field_bindings": {"geo": {"guid": "city_guid", "type": "string"}},
                "geo": {"evidence_kind": "geopoint"},
            }
        )

        self.assertFalse(invalid["ok"])
        self.assertIn("requires a numeric field", "\n".join(invalid["validation"]["errors"]))
        self.assertTrue(valid["ok"], valid.get("validation"))
        self.assertFalse(invalid_geo["ok"])
        self.assertIn("requires a geographic field", "\n".join(invalid_geo["validation"]["errors"]))

    def test_saved_dataset_readback_makes_plan_live_ready_and_is_compacted(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

        plan = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "column",
                "location": {"workbookId": "workbook_fixture", "name": "typed_column"},
                "dataset": "dataset_fixture",
                "field_bindings": {"x": "category_guid", "y": "value_guid"},
                "options": {"labels": [{"guid": "value_guid"}]},
                "dataset_readbacks": [
                    {
                        "datasetId": "dataset_fixture",
                        "result_schema": [
                            {"guid": "category_guid", "type": "string", "title": "Category"},
                            {"guid": "value_guid", "type": "float", "title": "Value"},
                            {"guid": "unused_guid", "type": "integer"},
                        ],
                        "unrelated": {"discard": True},
                    }
                ],
            }
        )

        self.assertTrue(plan["ok"], plan.get("dataset_readback_validation"))
        self.assertTrue(plan["live_execution_ready"])
        self.assertTrue(plan["dataset_readback_validation"]["ok"])
        self.assertEqual(
            plan["dataset_readbacks"][0]["result_schema"],
            [
                {"guid": "category_guid", "data_type": "string"},
                {"guid": "value_guid", "data_type": "float"},
            ],
        )

    def test_saved_dataset_readback_blocks_incompatible_measure_type(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

        plan = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "column",
                "location": {"workbookId": "workbook_fixture", "name": "invalid_column"},
                "dataset": "dataset_fixture",
                "field_bindings": {"x": "category_guid", "y": "value_guid"},
                "options": {"labels": [{"guid": "value_guid"}]},
                "dataset_readbacks": [
                    {
                        "datasetId": "dataset_fixture",
                        "result_schema": [
                            {"guid": "category_guid", "type": "string"},
                            {"guid": "value_guid", "type": "string"},
                        ],
                    }
                ],
            }
        )

        self.assertFalse(plan["ok"])
        self.assertFalse(plan["live_execution_ready"])
        self.assertEqual(plan["status"], "blocked_dataset_readback_validation")
        self.assertIn(
            "requires a numeric field",
            "\n".join(plan["validation"]["errors"]),
        )

    def test_horizontal_bar_uses_string_x_dimension_and_numeric_y_measure(self):
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

        valid = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "bar",
                "location": {"key": "folder/bar"},
                "dataset": "dataset_fixture",
                "field_bindings": {
                    "x": {"guid": "category_guid", "type": "string"},
                    "y": {"guid": "value_guid", "type": "integer"},
                },
            }
        )
        invalid_measure = build_wizard_payload_plan(
            {
                "route": "wizard_native",
                "visualization_id": "bar100p",
                "location": {"key": "folder/bar100p"},
                "dataset": "dataset_fixture",
                "field_bindings": {
                    "x": {"guid": "category_guid", "type": "string"},
                    "y": {"guid": "value_guid", "type": "string"},
                },
            }
        )

        self.assertTrue(valid["ok"], valid.get("validation"))
        self.assertFalse(invalid_measure["ok"])
        self.assertIn(
            "field_bindings.y requires a numeric field",
            "\n".join(invalid_measure["validation"]["errors"]),
        )

    def test_registry_declares_all_templates_creation_supported_and_anonymized(self):
        registry = json.loads(Path("templates/datalens/wizard/wizard_template_registry.json").read_text(encoding="utf-8"))
        templates = json.loads(Path("templates/datalens/wizard/canonical_templates.json").read_text(encoding="utf-8"))

        self.assertEqual(set(registry["templates"]), set(templates["templates"]))
        self.assertFalse(templates["deployment_ids_included"])
        self.assertFalse(registry["live_verification"])
        for visualization_id, spec in registry["templates"].items():
            with self.subTest(visualization_id=visualization_id):
                self.assertTrue(spec["creation_supported"])
                self.assertEqual(spec["visualization_id"], visualization_id)

    def test_mcp_wizard_template_tools_are_registered(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"] for tool in list_tools("dashboard")}
        default_tools = {tool["name"] for tool in list_tools()}

        self.assertIn("dl_list_wizard_templates", tools)
        self.assertIn("dl_build_wizard_payload_template", tools)
        self.assertNotIn("dl_list_wizard_templates", default_tools)

    def test_docs_examples_and_schema_exist(self):
        for rel in [
            "schemas/wizard-chart-config.schema.json",
            "templates/datalens/wizard/native_map/example_input.json",
            "templates/datalens/wizard/native_map/example_output_payload_plan.json",
            "templates/datalens/wizard/canonical_templates.json",
            "examples/wizard/native_map_input.json",
            "examples/wizard/non_map_reference_templates.json",
            "docs/datalens/wizard_chart_templates.md",
            "docs/datalens/template_quality_gate.md",
        ]:
            self.assertTrue(Path(rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
