import json
import unittest


class ToolSurfaceBudgetTests(unittest.TestCase):
    def test_autonomous_tool_surface_stays_bounded_and_policy_driven(self):
        from datalens_dev_mcp.server import AUTONOMOUS_TOOL_NAMES, list_tools

        tools = list_tools("autonomous-v2")
        all_tools = list_tools("all")
        names = {tool["name"] for tool in tools}
        payload_bytes = len(
            json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        all_payload_bytes = len(
            json.dumps({"tools": all_tools}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )

        self.assertEqual(names, AUTONOMOUS_TOOL_NAMES)
        self.assertEqual(len(names), 8)
        self.assertLessEqual(len(names), 9)
        self.assertLessEqual(payload_bytes, 9_000)
        self.assertLessEqual(all_payload_bytes, 65_000)
        self.assertIn("dl_task_start", names)
        self.assertIn("dl_execute", names)
        self.assertNotIn("dl_execute_safe_apply", names)
        self.assertNotIn("dl_rpc_expert", names)

    def test_practical_surface_audit_records_rev4_metrics(self):
        from scripts.check_autonomous_tool_surface import build_report

        report = build_report(
            {
                "public_call_count": 12,
                "invalid_call_count": 0,
                "extra_contract_reads": 0,
                "evidence_refs": ["synthetic-ledger.jsonl"],
            }
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["tool_count"], 8)
        self.assertEqual(report["raw_tools_list_bytes"], report["tools_list_utf8_bytes"])
        self.assertGreater(report["client_rendered_bytes"], report["raw_tools_list_bytes"])
        self.assertGreater(report["estimated_tokens"], 0)
        self.assertGreaterEqual(report["schema_branch_count"], 0)
        self.assertIn("name", report["largest_tool_schema"])
        self.assertGreater(report["largest_tool_schema"]["utf8_bytes"], 0)
        self.assertGreaterEqual(report["duplicate_description_bytes"], 0)
        self.assertEqual(report["invalid_call_rate"], 0.0)
        self.assertEqual(report["extra_contract_reads"], 0)
        self.assertTrue(report["checks"]["strict_object_validation"])

    def test_compaction_preserves_safety_critical_parameter_descriptions(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"]: tool for tool in list_tools("legacy-v1")}

        def description(tool_name: str, parameter_name: str) -> str:
            return tools[tool_name]["inputSchema"]["properties"][parameter_name]["description"]

        self.assertIn("Must not contain secrets", description("dl_diagnose", "payload"))
        self.assertIn("local MCP config", description("dl_get_local_config", "config_path"))
        self.assertIn("saved-branch readback", description("dl_create_publish_from_saved_plan", "saved_readback_path").lower())
        self.assertIn("Fresh getDataset", description("dl_plan_guarded_dataset_update", "current_dataset"))
        self.assertIn("Proposed dataset payload", description("dl_plan_guarded_dataset_update", "proposed_dataset"))
        self.assertIn("Execute", description("dl_run_project_live_apply", "execute_now"))
        self.assertIn("publish", description("dl_run_project_live_apply", "publish"))
        self.assertIn("retire_legacy_objects IDs", description("dl_run_project_live_apply", "confirm_delete"))


if __name__ == "__main__":
    unittest.main()
