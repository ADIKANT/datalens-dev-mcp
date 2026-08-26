from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.editor.style_binding import (
    assert_technology_preserved,
    bind_style_profile,
    materialize_style_bundle,
    validate_source_alias_coordination,
    validate_bound_bundle,
)
from datalens_dev_mcp.editor.style_registry import select_style_profile, validate_style_registry
from datalens_dev_mcp.editor.style_scanner import public_safe_registry, scan_portfolio_style_registry
from datalens_dev_mcp.mcp.resources import read_resource


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "portfolio_styles"


class StyleRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = scan_portfolio_style_registry(FIXTURE_ROOT)
        self.exact_path = "exact_family"

    def test_exact_reference_beats_generic_family(self) -> None:
        selected = select_style_profile(
            self.registry,
            {"existing_object_path": self.exact_path, "technology": "editor_js_control"},
        )
        self.assertEqual(selected["origin"], "exact_object")
        self.assertEqual(selected["profile"]["source"]["relative_path"], self.exact_path)

    def test_explicit_reference_is_second_priority(self) -> None:
        selected = select_style_profile(self.registry, {"explicit_reference_path": self.exact_path})
        self.assertEqual(selected["origin"], "explicit_reference")

    def test_unknown_family_uses_cookbook_then_new_design(self) -> None:
        context = {"technology": "editor_markdown", "visualization_kind": "unknown"}
        self.assertEqual(select_style_profile(self.registry, context)["origin"], "generic_cookbook")
        context["cookbook_available"] = False
        self.assertEqual(select_style_profile(self.registry, context)["origin"], "new_design")

    def test_binding_is_immutable_and_valid(self) -> None:
        binding = bind_style_profile(self.registry, {"existing_object_path": self.exact_path})
        self.assertTrue(binding["immutable"])
        result = materialize_style_bundle(self.registry, binding, updates={"pagination": 75})
        self.assertTrue(validate_bound_bundle(result)["ok"])
        self.assertIn("75", result["tabs"]["prepare.js"])
        self.assertEqual(result["protected_region_validation"]["status"], "unchanged")

    def test_source_update_preserves_protected_renderer(self) -> None:
        binding = bind_style_profile(self.registry, {"existing_object_path": self.exact_path})
        result = materialize_style_bundle(
            self.registry,
            binding,
            updates={"source_sql": "SELECT category, metric FROM synthetic_table_v2"},
        )
        self.assertEqual(result["protected_region_validation"]["status"], "unchanged")
        self.assertIn("synthetic_table_v2", result["tabs"]["sources.js"])

    def test_uncoordinated_alias_rename_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "coordinated prepare.js"):
            validate_source_alias_coordination(["rows"], ["renamed_rows"], prepare_changed=False)

    def test_technology_change_is_blocked(self) -> None:
        binding = bind_style_profile(self.registry, {"existing_object_path": self.exact_path})
        with self.assertRaisesRegex(ValueError, "technology change"):
            assert_technology_preserved(binding, "editor_table")

    def test_stale_source_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "portfolio"
            copied.mkdir()
            target = copied / "family"
            target.mkdir()
            for path in (FIXTURE_ROOT / "exact_family").iterdir():
                (target / path.name).write_bytes(path.read_bytes())
            registry = scan_portfolio_style_registry(copied)
            binding = bind_style_profile(registry, {"existing_object_path": "family"})
            with (target / "sources.js").open("a", encoding="utf-8") as handle:
                handle.write("\n// source changed\n")
            with self.assertRaisesRegex(ValueError, "stale"):
                materialize_style_bundle(registry, binding)

    def test_public_projection_contains_no_private_paths_or_ids(self) -> None:
        safe = public_safe_registry(self.registry)
        raw = json.dumps(safe, ensure_ascii=False)
        self.assertNotIn(str(FIXTURE_ROOT), raw)
        self.assertNotIn("exact_family", raw)
        self.assertNotIn("synthetic-dataset", raw)
        self.assertEqual(safe["profiles"][0]["id"], "family_001")

    def test_registry_validation_and_bounded_large_projection(self) -> None:
        self.assertEqual(validate_style_registry(self.registry), [])
        binding = bind_style_profile(self.registry, {"existing_object_path": self.exact_path})
        result = materialize_style_bundle(self.registry, binding)
        projection = result["style_profile_summary"]["slot_projection"]
        self.assertLessEqual(projection["fragment_count"], 3)
        self.assertFalse(projection["full_content_inline"])
        self.assertTrue(projection["resource_uri"])

    def test_required_visual_contracts_are_preserved(self) -> None:
        profile = next(
            item for item in self.registry["profiles"] if item["source"]["relative_path"] == self.exact_path
        )
        contracts = profile["contracts"]
        self.assertEqual(contracts["themes"], ["light", "dark"])
        self.assertEqual(contracts["sticky_header"], "opaque")
        self.assertEqual(contracts["legend"], "actual_series_only")
        self.assertEqual(contracts["pagination"], "bounded")
        self.assertFalse(contracts["redundant_technical_columns"])

    def test_full_tab_is_available_as_hash_checked_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            family = project / "styles" / "family"
            shutil.copytree(FIXTURE_ROOT / "exact_family", family)
            registry = scan_portfolio_style_registry(project)
            registry_dir = project / ".datalens-mcp"
            registry_dir.mkdir()
            (registry_dir / "style-registry.json").write_text(
                json.dumps(registry),
                encoding="utf-8",
            )
            profile_id = registry["profiles"][0]["id"]
            uri = f"datalens://style-registry/profiles/{profile_id}/tabs/prepare.js"
            resource = read_resource(uri, project_root=project)
            self.assertEqual(resource["mimeType"], "text/javascript")
            self.assertIn("function createRender", resource["text"])

    def test_huge_prepare_projection_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            family = Path(tmp) / "huge_family"
            family.mkdir()
            (family / "meta.json").write_text("{\"links\":{}}", encoding="utf-8")
            (family / "sources.js").write_text("module.exports={};", encoding="utf-8")
            (family / "prepare.js").write_text(
                "/* datalens-protected:runtime:start */\n"
                + ("const syntheticPadding = 1;\n" * 4_000)
                + "/* datalens-protected:runtime:end */\n"
                + "const pageSize=/* datalens-slot:page:integer:start */50"
                + "/* datalens-slot:page:end */;\nmodule.exports={pageSize};\n",
                encoding="utf-8",
            )
            registry = scan_portfolio_style_registry(tmp)
            binding = bind_style_profile(registry, {"existing_object_path": "huge_family"})
            result = materialize_style_bundle(registry, binding)
            projection = result["style_profile_summary"]
            self.assertGreater((family / "prepare.js").stat().st_size, 100_000)
            self.assertLess(len(json.dumps(projection)), 8_000)
            self.assertFalse(projection["slot_projection"]["full_content_inline"])


if __name__ == "__main__":
    unittest.main()
