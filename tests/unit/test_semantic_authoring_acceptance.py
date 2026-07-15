import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.knowledge.formulas import parse_formula_expression, validate_formula_expression
from datalens_dev_mcp.knowledge.reference import build_reference_response
from datalens_dev_mcp.knowledge.recipes import build_recipe_bundle, load_recipe_registry
from datalens_dev_mcp.runtime_resources import resource_json


class SemanticAuthoringAcceptanceTests(unittest.TestCase):
    def test_formula_parser_required_regressions(self):
        registry = resource_json("schemas/datalens-knowledge/formula-registry.json")

        self.assertEqual(len(registry["functions"]), 221)
        self.assertEqual(parse_formula_expression('CONCAT("a,b", "(x)", [name])')["type"], "call")

        for expression in [
            "AGO([sales], [date])",
            "IF([x] > 0, 1, 0)",
            "FIXED [Region] : SUM([Sales])",
            'CONCAT("a,b", "(x)", [name])',
            "SUM([Sales] BEFORE FILTER BY [Region])",
            "AVG(SUM([Orders]) WITHIN [City])",
        ]:
            with self.subTest(expression=expression):
                self.assertTrue(validate_formula_expression(expression, registry)["ok"])

        self.assertFalse(validate_formula_expression("SUM()", registry)["ok"])
        self.assertFalse(validate_formula_expression("AVG()", registry)["ok"])
        self.assertFalse(validate_formula_expression("UNKNOWN_FUNC([x])", registry)["ok"])
        self.assertFalse(validate_formula_expression("SUM(AVG([Orders]))", registry)["ok"])
        sum_record = next(item for item in registry["functions"] if item["name"] == "SUM")
        self.assertEqual(sum_record["window_status"], "not_window")

    def test_editor_contracts_and_route_matrix_are_evidence_based(self):
        contracts = resource_json("schemas/datalens-knowledge/editor-visualization-contracts.json")["contracts"]
        routes = resource_json("schemas/datalens-knowledge/route-capability-matrix.json")["routes"]
        by_path = {item["mirror_path"]: item for item in contracts}
        by_route = {item["route_id"]: item for item in routes}

        methods = by_path["datalens/charts/editor/methods.md"]
        table = by_path["datalens/charts/editor/widgets/table.md"]
        self.assertIn("Editor.setRawData", methods["methods"])
        self.assertIn("data-tooltip-content", methods["html_tags_or_attributes"])
        self.assertIn("Prepare", table["required_tabs"])
        self.assertEqual(by_route["table_node"]["executable_fixture_tested"], True)
        self.assertEqual(by_route["gravity_ui_chart"]["create_supported"], False)
        self.assertIn("missing safe MCP route contract", by_route["gravity_ui_chart"]["blocked_reason"])
        self.assertEqual(by_route["wizard_native"]["create_supported"], True)
        self.assertEqual(by_route["wizard_native"]["executable_fixture_tested"], True)
        self.assertEqual(by_route["ql_explicit"]["create_supported"], True)
        self.assertEqual(by_route["ql_delete"]["create_supported"], False)

    def test_every_implemented_recipe_has_executable_bundle_and_pivot_runs(self):
        registry = load_recipe_registry()
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required for executable recipe checks")
        for recipe in registry["recipes"]:
            if not str(recipe["implementation_status"]).startswith("implemented"):
                continue
            with self.subTest(recipe=recipe["recipe_id"]):
                bundle = build_recipe_bundle(recipe["recipe_id"])
                self.assertTrue(bundle["ok"], bundle)
                self.assertIn("meta.json", bundle["files"])
                self.assertIn("fixture_input.json", bundle["files"])
                if "prepare.js" in bundle["files"]:
                    self._node_check(bundle["files"]["prepare.js"], node)

        pivot = build_recipe_bundle("table_pivot_js")
        output = self._node_execute_prepare(pivot["files"]["prepare.js"], pivot["files"]["fixture_input.json"], node)
        self.assertEqual([cell["value"] for cell in output["footer"]["cells"]][-1], 25)
        self.assertEqual(output["head"][0]["pinned"], True)
        self.assertIn("sub", output["head"][2])

    def test_spilled_authoring_guidance_preserves_plan_and_inline_results(self):
        response = build_reference_response(
            mode="authoring_plan",
            query="сделай сводную таблицу план факт с итогами и кросс фильтром",
            max_chars=1200,
            project_root=str(Path(__file__).resolve().parents[2]),
        )
        self.assertTrue(response["spilled"])
        self.assertIn("authoring_plan", response)
        self.assertIn("recipes", response)
        self.assertTrue(response["recipes"])
        plan = response["authoring_plan"]
        self.assertIn("recommended_route", plan)
        self.assertIn("required_files_or_tabs", plan)
        self.assertIn("validation_checklist", plan)
        self.assertIn("exact_source_traces", plan)

    def test_formula_expression_reference_preserves_function_source_traces(self):
        response = build_reference_response(mode="formula", query="COUNTD([ClientID])", max_chars=12000)

        self.assertTrue(response["validation"]["ok"])
        self.assertGreaterEqual(response["result_count"], 1)
        self.assertEqual(response["results"][0]["name"], "COUNTD")
        self.assertTrue(response["results"][0].get("source_trace") or response["results"][0].get("source_traces"))

    def _node_check(self, source: str, node: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prepare.js"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run([node, "--check", str(path)], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def _node_execute_prepare(self, source: str, fixture: dict, node: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prepare.js"
            path.write_text(source, encoding="utf-8")
            script = (
                "const prepare = require(process.argv[1]);"
                "const input = JSON.parse(process.argv[2]);"
                "console.log(JSON.stringify(prepare(input)));"
            )
            result = subprocess.run(
                [node, "-e", script, str(path), json.dumps(fixture)],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)


if __name__ == "__main__":
    unittest.main()
