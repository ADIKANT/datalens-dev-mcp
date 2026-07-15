import json
import unittest
from pathlib import Path

from datalens_dev_mcp.knowledge.compiler import MANDATORY_RECIPE_IDS


RECIPE_REGISTRY = Path("templates/datalens/recipes/recipe-registry.json")


class FullCorpusEditorRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(RECIPE_REGISTRY.read_text(encoding="utf-8"))
        cls.recipes = {item["recipe_id"]: item for item in cls.registry["recipes"]}

    def test_all_mandatory_recipes_are_source_traced(self):
        self.assertEqual(set(MANDATORY_RECIPE_IDS), set(self.recipes))
        for recipe in self.recipes.values():
            self.assertTrue(recipe["source_traces"], recipe["recipe_id"])
            for trace in recipe["source_traces"]:
                self.assertIn("source_url", trace)
                self.assertIn("mirror_path", trace)
                self.assertIn("sha256", trace)

    def test_flat_table_recipes_emit_native_table_contract(self):
        for recipe_id in ("table_flat_sql", "table_flat_dataset", "table_flat_api_connector"):
            recipe = self.recipes[recipe_id]
            with self.subTest(recipe=recipe_id):
                self.assertEqual(recipe["route"], "editor_table")
                self.assertEqual(recipe["widget_contract"], "table_node")
                self.assertFalse(recipe["uses_generate_html"])
                self.assertLessEqual({"head", "rows", "footer_optional"}, set(recipe["output_contract"]))
                self.assertIn("Prepare", recipe["required_tabs"])

    def test_pivot_recipe_has_grouped_output_and_bounded_algorithm(self):
        recipe = self.recipes["table_pivot_js"]

        self.assertEqual(recipe["route"], "editor_table")
        self.assertFalse(recipe["uses_generate_html"])
        self.assertIn("head.sub", recipe["output_contract"])
        self.assertIn("totals_subtotals", recipe["output_contract"])
        self.assertEqual(recipe["algorithmic_bound"], "O(n log n)")
        self.assertLessEqual(recipe["cardinality_limits"]["columns"], 200)

    def test_advanced_pivot_exception_is_reference_only_and_non_executable(self):
        recipe = self.recipes["table_pivot_advanced_exception"]

        self.assertEqual(recipe["route"], "editor_advanced")
        self.assertTrue(recipe["uses_generate_html"])
        self.assertIn("requires_explicit_exception_reason", recipe["output_contract"])
        self.assertEqual(recipe["implementation_status"], "documented_reference_blocked_by_local_policy")
        self.assertEqual(recipe["local_policy_status"], "blocked")
        self.assertEqual(recipe["executable_bundle"]["status"], "not_executable_reference_only")

    def test_resource_schedule_is_explicit_only_and_bounded(self):
        recipe = self.recipes["resource_schedule_exception"]

        self.assertEqual(recipe["route"], "editor_advanced")
        self.assertEqual(recipe["local_policy_status"], "allowed_explicit_only")
        self.assertEqual(recipe["cardinality_limits"]["rows"], 1000)
        self.assertEqual(recipe["cardinality_limits"]["lanes_per_resource"], 8)
        self.assertEqual(recipe["cardinality_limits"]["span_days"], 90)
        self.assertIn("bounded_table_node_fallback", recipe["output_contract"])

    def test_gravity_chart_is_documented_reference_not_runtime_route(self):
        recipe = self.recipes["gravity_chart"]

        self.assertEqual(recipe["route"], "documented_reference")
        self.assertEqual(recipe["official_status"], "documented_reference")
        self.assertEqual(recipe["local_policy_status"], "blocked")
        self.assertEqual(recipe["implementation_status"], "documented_reference_blocked_by_local_policy")


if __name__ == "__main__":
    unittest.main()
