import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_javascript_cookbook.py"
RUNTIME_SCRIPT = ROOT / "scripts" / "check_javascript_cookbook_runtime.py"
OUTPUT_ROOT = ROOT / "docs" / "cookbook"
NODE = Path(
    os.environ.get("DATALENS_MCP_NODE")
    or shutil.which("node")
    or Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ResourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.resources = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {"script", "img", "link", "iframe"}:
            for name in ("src", "href"):
                if values.get(name):
                    self.resources.append(values[name])


class JavaScriptCookbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_module(BUILD_SCRIPT, "build_javascript_cookbook_test")
        cls.catalog = cls.builder.load_catalog()
        cls.expected = cls.builder.build_expected_files()
        cls.manifest = json.loads(cls.expected["manifest.json"])

    def test_catalog_schema_counts_variants_and_route_tabs(self):
        self.assertEqual(self.catalog["schema_id"], "javascript_cookbook")
        self.assertEqual(self.catalog["locales"], ["ru", "en"])
        self.assertEqual(len(self.catalog["recipes"]), 34)
        self.assertEqual(len(self.catalog["cases"]), 3)
        self.assertEqual(self.manifest["advanced_visualization_count"], 25)
        self.assertEqual(self.manifest["table_recipe_count"], 4)
        self.assertEqual(self.manifest["selector_recipe_count"], 5)
        self.assertEqual(self.manifest["case_count"], 3)
        pairs = {(item["slug"], item["variant"]) for item in self.catalog["recipes"]}
        self.assertEqual(len(pairs), 34)
        for recipe in self.catalog["recipes"]:
            self.assertEqual(recipe["tabs"], self.builder.EXPECTED_TABS[recipe["route"]], recipe["slug"])
        schema = json.loads((ROOT / "config" / "javascript_cookbook.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema_id"]["const"], "javascript_cookbook")
        self.assertEqual(schema["properties"]["recipes"]["minItems"], 34)
        self.assertEqual(schema["properties"]["cases"]["maxItems"], 3)

    def test_generated_tree_is_deterministic_and_manifest_hashes_match(self):
        self.assertEqual(self.builder.compare_expected(self.expected), [])
        for recipe in self.manifest["recipes"]:
            self.assertEqual(len(recipe["canonical_executable_hashes"]), 1, recipe["slug"])
            for locale in recipe["locales"].values():
                for item in locale["files"]:
                    data = (OUTPUT_ROOT / item["path"]).read_bytes()
                    self.assertEqual(len(data), item["bytes"], item["path"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"], item["path"])

    def test_public_readmes_promote_the_interactive_cookbook(self):
        pages_url = self.catalog["pages_url"]
        for lang, root_readme, docs_readme, generated_readme in (
            ("ru", "README.md", "docs/README.md", "README.md"),
            ("en", "README_en.md", "docs/README_en.md", "README_en.md"),
        ):
            interactive_url = f"{pages_url}?lang={lang}"
            self.assertIn(interactive_url, (ROOT / root_readme).read_text(encoding="utf-8"))
            self.assertIn(interactive_url, (ROOT / docs_readme).read_text(encoding="utf-8"))
            generated = self.expected[generated_readme]
            self.assertIn(interactive_url, generated)
            self.assertIn(f"{pages_url}visualizations/?lang={lang}", generated)
            self.assertIn(f"{pages_url}cases/?lang={lang}", generated)

    def test_localized_code_trees_are_structurally_equivalent_and_not_mixed(self):
        for item in self.manifest["recipes"]:
            ru = item["locales"]["ru"]["structure_hashes"]
            en = item["locales"]["en"]["structure_hashes"]
            self.assertEqual(ru, en, item["slug"])
            prefix = f"recipes/{item['slug']}/code"
            for name in item["tabs"]:
                if not name.endswith(".js"):
                    continue
                ru_code = self.expected[f"{prefix}/ru/{name}"]
                en_code = self.expected[f"{prefix}/en/{name}"]
                self.assertNotRegex(en_code, r"[А-Яа-яЁё]", f"{item['slug']}/{name}")
                self.assertNotIn("Change:", ru_code, f"{item['slug']}/{name}")
                self.assertNotIn("Stable row key", ru_code, f"{item['slug']}/{name}")
                self.assertNotIn("@cookbook-locale en", ru_code)
                self.assertNotIn("@cookbook-locale ru", en_code)

    def test_sources_contracts_explain_alias_purpose_format_null_and_bucket(self):
        for recipe in self.catalog["recipes"]:
            for lang in self.builder.LOCALES:
                compiled = self.builder.compile_recipe(self.catalog, recipe, lang)
                aliases = [field["alias"] for field in compiled["source_contract"]]
                schema = json.loads(compiled["support_files"]["schema.json"])
                example = json.loads(compiled["support_files"]["example_input.json"])
                if aliases:
                    self.assertEqual(set(schema["properties"]["rows"]["items"]["properties"]), set(aliases), recipe["slug"])
                    self.assertEqual(example["rows"], compiled["fixture_rows"], recipe["slug"])
                    source = compiled["tabs"]["sources.js"]
                    for alias in aliases:
                        self.assertIn(json.dumps(alias), source, f"{recipe['slug']}: {alias}")
                    for field in compiled["source_contract"]:
                        self.assertTrue(field["meaning"])
                        self.assertTrue(field["format"])
                        self.assertTrue(field["null_behavior"])
        bucket_ru = self.builder.field_contract(self.catalog, "bucket", "ru")
        self.assertIn("Начало отображаемого временного интервала", bucket_ru["meaning"])
        self.assertIn("дня, недели или месяца", bucket_ru["meaning"])

    def test_area_cumulative_heatmap_sankey_and_native_table_contracts_are_present(self):
        area = self.builder.compile_recipe(
            self.catalog, next(item for item in self.catalog["recipes"] if item["slug"] == "area-chart"), "en"
        )
        cumulative = self.builder.compile_recipe(
            self.catalog, next(item for item in self.catalog["recipes"] if item["slug"] == "cumulative-line"), "en"
        )
        heatmap = self.builder.compile_recipe(
            self.catalog, next(item for item in self.catalog["recipes"] if item["slug"] == "matrix-heatmap"), "en"
        )
        sankey = self.builder.compile_recipe(self.catalog, next(item for item in self.catalog["recipes"] if item["slug"] == "sankey"), "en")
        self.assertIn('data-role="area-fill"', area["tabs"]["prepare.js"])
        self.assertNotIn("profileFinite(row.increment)", area["tabs"]["prepare.js"])
        self.assertIn("profileFinite(row.increment)", cumulative["tabs"]["prepare.js"])
        self.assertIn('data-role="heatmap-matrix"', heatmap["tabs"]["prepare.js"])
        self.assertIn("data-x=", heatmap["tabs"]["prepare.js"])
        self.assertIn("data-y=", heatmap["tabs"]["prepare.js"])
        self.assertIn('data-role="sankey-node"', sankey["tabs"]["prepare.js"])
        self.assertIn('data-role="sankey-link"', sankey["tabs"]["prepare.js"])
        table_recipes = [item for item in self.catalog["recipes"] if item["route"] == "editor_table"]
        self.assertEqual({item["variant"] for item in table_recipes}, {"standard", "detail", "status", "grouped_summary"})
        for recipe in table_recipes:
            compiled = self.builder.compile_recipe(self.catalog, recipe, "en")
            self.assertNotIn("render: Editor.wrapFn", compiled["tabs"]["prepare.js"])
            self.assertIn("module.exports = {head, rows", compiled["tabs"]["prepare.js"])

    def test_cases_have_shared_param_graph_and_both_safe_source_modes(self):
        compiled_map = {}
        for recipe in self.catalog["recipes"]:
            for lang in self.builder.LOCALES:
                compiled_map[(recipe["slug"], lang)] = self.builder.compile_recipe(self.catalog, recipe, lang)
        for source_case in self.catalog["cases"]:
            compiled = self.builder.compile_case(self.catalog, source_case, compiled_map)
            object_ids = {item["id"] for item in compiled["objects"]}
            for parameter in compiled["params"]:
                self.assertIn(parameter["owner"], object_ids)
                self.assertTrue(set(parameter["readers"]).issubset(object_ids))
            for item in compiled["objects"]:
                for lang in self.builder.LOCALES:
                    localized = item["localized"][lang]
                    self.assertEqual(set(localized["modes"]), {"dataset", "clickhouse"})
                    clickhouse = localized["modes"]["clickhouse"]["sources.js"]
                    if localized["source_contract"]:
                        self.assertIn("__TABLE__", clickhouse)
                        self.assertIn("WHERE event_date BETWEEN", clickhouse)
                        self.assertIn('split("\'").join("\'\'")', clickhouse)
            page = self.expected[f"cases/{compiled['slug']}/index.html"]
            self.assertIn("updateParams", page)
            self.assertIn("draft.from", page)
            self.assertIn("draft.to", page)
            self.assertIn("days()<=14?'day':days()<=60?'week':'month'", page)

    def test_site_is_multipage_sandboxed_self_contained_and_has_no_removed_blocks(self):
        html_paths = [path for path in self.expected if path.endswith(".html")]
        self.assertGreaterEqual(len(html_paths), 40)
        self.assertLess(len(self.expected["index.html"].encode()), 150_000)
        self.assertIn('"page_type":"tips"', self.expected["index.html"])
        for path in html_paths:
            value = self.expected[path]
            parser = ResourceParser()
            parser.feed(value)
            self.assertEqual(parser.resources, [], path)
            self.assertNotIn("fetch(", value, path)
            self.assertNotIn("XMLHttpRequest", value, path)
            self.assertNotIn("WebSocket(", value, path)
            self.assertNotIn("allow-same-origin", value, path)
            self.assertIn("frame.setAttribute('sandbox', 'allow-scripts')", value, path)
            self.assertNotIn("Возможности", value, path)
            self.assertNotIn('class="chips"', value, path)
            self.assertNotIn("Responsive behavior", value, path)
        for value in self.expected.values():
            self.assertNotIn("/Users/", value)
            self.assertNotIn("car fleet", value.casefold())
            self.assertNotIn("charging app", value.casefold())

    def test_markdown_has_no_per_recipe_generic_responsive_or_capability_sections(self):
        for recipe in self.catalog["recipes"]:
            for name in ("README.md", "README_en.md"):
                value = self.expected[f"recipes/{recipe['slug']}/{name}"]
                self.assertNotIn("## Адаптивность", value)
                self.assertNotIn("## Responsive behavior", value)
                self.assertNotIn("## Возможности", value)
                self.assertNotRegex(value, r"\bзерн\w*")
                self.assertNotRegex(value, r"\bgrain\b")

    def test_all_static_fallbacks_are_valid_svg(self):
        paths = [path for path in self.expected if path.endswith(".svg")]
        self.assertEqual(len(paths), 34 * 2 + 3 * 2)
        for path in paths:
            root = ET.fromstring(self.expected[path])
            self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg", path)
            self.assertGreater(len(list(root)), 2, path)

    def test_canonical_templates_have_paired_locale_annotations(self):
        paths = [
            ROOT / "templates/datalens/authoring_profiles/standard_dashboard/advanced_editor_runtime.js",
            ROOT / "templates/datalens/authoring_profiles/standard_dashboard/prepare_adapter.js",
            ROOT / "templates/datalens/advanced_editor/category_comparison/prepare.js",
            ROOT / "templates/datalens/advanced_editor/flow_sankey/prepare.js",
            ROOT / "templates/datalens/editor_table/table_node/prepare.js",
            ROOT / "templates/datalens/editor_js_control/selector/controls.js",
        ]
        for path in paths:
            value = path.read_text()
            self.assertIn("@cookbook-locale ru", value, path.as_posix())
            self.assertIn("@cookbook-locale en", value, path.as_posix())

    def test_runtime_sweep_contract(self):
        environment = os.environ.copy()
        if NODE.is_file():
            environment["DATALENS_MCP_NODE"] = str(NODE)
        completed = subprocess.run(
            [sys.executable, str(RUNTIME_SCRIPT), "--strict"],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["recipe_count"], 34)
        self.assertEqual(report["localized_recipe_count"], 68)
        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["recipe_probe_count"], 408)
        self.assertEqual(report["case_probe_count"], 144)
        self.assertEqual(report["probe_count"], 552)
        self.assertGreaterEqual(report["semantic_probe_count"], 16)


if __name__ == "__main__":
    unittest.main()
