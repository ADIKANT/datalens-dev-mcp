import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.knowledge.compiler import measure_tool_budget
from datalens_dev_mcp.knowledge.recipes import compact_recipe_for_payload, get_recipe, select_authoring_recipe
from datalens_dev_mcp.mcp.tools.pipeline import dl_build_payload_plan
from datalens_dev_mcp.mcp.tools.runtime import dl_validate_editor_runtime_contract
from datalens_dev_mcp.runtime_resources import resource_json
from datalens_dev_mcp.server import JsonRpcServer, list_tools


class FullCorpusRuntimeIntegrationTests(unittest.TestCase):
    def test_default_surface_includes_one_reference_tool_with_budget(self):
        server = JsonRpcServer(project_root=".")
        result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]
        names = {tool["name"] for tool in result["tools"]}
        schemas = {tool["name"]: tool["inputSchema"] for tool in result["tools"]}
        all_schemas = {tool["name"]: tool["inputSchema"] for tool in list_tools("all")}
        payload_chars = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

        self.assertIn("dl_reference", names)
        self.assertLessEqual(len(names), 40)
        self.assertLessEqual(payload_chars, 25000)
        self.assertIn("recipe", schemas["dl_reference"]["properties"]["mode"]["enum"])
        self.assertEqual(all_schemas["dl_update_dashboard_plan"]["properties"]["mode"]["enum"], ["save", "publish"])

    def test_compiled_capability_matrices_embed_the_current_tool_budget(self):
        expected = measure_tool_budget()

        for resource_name in (
            "schemas/datalens-knowledge/capability-matrix.json",
            "schemas/datalens-knowledge/route-capability-matrix.json",
        ):
            with self.subTest(resource_name=resource_name):
                self.assertEqual(resource_json(resource_name)["tool_budget"], expected)

    def test_reference_tool_returns_bounded_source_traced_recipe(self):
        server = JsonRpcServer(project_root=".")
        result = server._call_tool(
            {"name": "dl_reference", "arguments": {"mode": "recipe", "query": "table_pivot_js", "max_chars": 6000}}
        )
        body = json.loads(result["content"][0]["text"])

        self.assertFalse(result["isError"])
        self.assertTrue(body["ok"])
        self.assertLessEqual(body["response_chars"], 6000)
        self.assertEqual(body["results"][0]["recipe_id"], "table_pivot_js")
        self.assertTrue(body["results"][0]["source_traces"])

    def test_recipe_selector_prefers_native_pivot_until_advanced_evidence_exists(self):
        native = select_authoring_recipe("pivot table with totals and dynamic columns", route="editor_table")
        advanced = select_authoring_recipe("pivot sticky grouped html advanced exception", route="editor_table")

        self.assertEqual(native["recipe_id"], "table_pivot_js")
        self.assertIn("table_node is insufficient", native["blocked_advanced_exception_reason"])
        self.assertEqual(advanced["recipe_id"], "table_pivot_js")
        self.assertEqual(advanced["reference_only_recipe_id"], "table_pivot_advanced_exception")
        self.assertIn("reference-only", advanced["blocked_advanced_exception_reason"])

    def test_payload_plan_carries_recipe_metadata_without_changing_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_dir = root / "dashboard" / "widget_001"
            bundle_dir.mkdir(parents=True)
            recipe = compact_recipe_for_payload(get_recipe("table_pivot_js"))
            bundle = {
                "widget_id": "widget_001",
                "route": "editor_table",
                "entry_type": "table_node",
                "name": "js - table pivot",
                "knowledge_recipe": recipe,
                "tabs": {
                    "meta.json": '{"links":{}}',
                    "params.js": "module.exports = {};",
                    "sources.js": "module.exports = {};",
                    "config.js": "module.exports = {};",
                    "prepare.js": "module.exports = {head: [], rows: []};",
                },
            }
            (bundle_dir / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

            plan = dl_build_payload_plan(project_root=str(root), workbook_id="workbook_local")

        self.assertEqual(plan["payloads"][0]["recipe_id"], "table_pivot_js")
        self.assertEqual(plan["payloads"][0]["source_contract"], "database_sql_or_dataset")
        self.assertIn("runtime_contract_valid", plan["payloads"][0]["validation_checklist"])

    def test_runtime_validation_includes_editor_source_references(self):
        result = dl_validate_editor_runtime_contract(sections={"prepare": "module.exports = {render: () => ''};"})

        self.assertNotIn("corpus_references", result)
        self.assertTrue(result["corpus_reference_set"]["source_urls"])
        expanded = dl_validate_editor_runtime_contract(
            sections={"prepare": "module.exports = {render: () => ''};"},
            include_references=True,
        )
        self.assertTrue(expanded["corpus_references"])
        self.assertTrue(expanded["validation_cache"]["hit"])


if __name__ == "__main__":
    unittest.main()
