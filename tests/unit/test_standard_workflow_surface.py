import unittest


class StandardWorkflowSurfaceTests(unittest.TestCase):
    def test_representative_workflows_plan_with_default_surface_only(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_plan_guarded_dataset_update,
            dl_plan_object_create,
            dl_plan_object_update,
            dl_validate_object,
        )
        from datalens_dev_mcp.server import STANDARD_TOOL_NAMES

        default_tools = set(STANDARD_TOOL_NAMES)
        workflows = {
            "event_source_repair": {
                "dl_read_object",
                "dl_snapshot_dashboard",
                "dl_validate_object",
                "dl_plan_guarded_dataset_update",
                "dl_create_safe_apply_plan",
                "dl_readback_and_report",
            },
            "roadmap_publish": {
                "dl_snapshot_dashboard",
                "dl_plan_dashboard_tab_update",
                "dl_plan_object_update",
                "dl_create_safe_apply_plan",
                "dl_create_publish_from_saved_plan",
                "dl_readback_and_report",
            },
            "quality_table_creation": {
                "dl_reference",
                "dl_validate_editor_runtime_contract",
                "dl_plan_object_create",
                "dl_validate_project",
                "dl_build_payload_plan",
            },
            "order_kpi_lifecycle": {
                "dl_read_object",
                "dl_validate_object",
                "dl_plan_object_update",
                "dl_create_safe_apply_plan",
                "dl_readback_and_report",
            },
        }
        for name, required in workflows.items():
            with self.subTest(name=name):
                self.assertLessEqual(required, default_tools)

        self.assertNotIn("dl_rpc_readonly", default_tools)
        self.assertNotIn("dl_rpc_expert", default_tools)
        self.assertNotIn("dl_get_dataset", default_tools)

        dataset_plan = dl_plan_guarded_dataset_update(
            "dataset_events",
            {"fields": [{"name": "entity_id", "guid": "entity_id_g"}]},
            {"fields": [{"name": "entity_id", "guid": "entity_id_g"}]},
        )
        table_plan = dl_plan_object_create(
            "table",
            {
                "entry": {
                    "workbookId": "workbook_quality",
                    "name": "quality_table",
                    "type": "table_node",
                    "data": {},
                }
            },
        )
        dashboard_plan = dl_plan_object_update(
            "dashboard",
            {"entry": {"entryId": "dash_roadmap", "revId": "rev_1", "data": {"tabs": []}, "meta": {}}},
        )
        dataset_validation = dl_validate_object(
            "dataset",
            {"datasetId": "dataset_orders", "data": {"dataset": {"fields": [{"name": "returned_orders"}]}}},
        )

        self.assertTrue(dataset_plan["ok"], dataset_plan.get("blocked_reasons"))
        self.assertTrue(table_plan["ok"], table_plan.get("error"))
        self.assertTrue(dashboard_plan["ok"], dashboard_plan.get("error"))
        self.assertTrue(dataset_validation["ok"], dataset_validation.get("error"))


if __name__ == "__main__":
    unittest.main()
