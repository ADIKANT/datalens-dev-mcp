from __future__ import annotations

import unittest

from datalens_dev_mcp.editor.protected_regions import build_protected_regions, validate_protected_regions
from datalens_dev_mcp.editor.semantic_slots import apply_semantic_slot_updates, discover_semantic_slots


class ProtectedRegionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tabs = {
            "sources.js": "module.exports={rows:{sql_query: `SELECT old_value FROM synthetic_table`}};",
            "prepare.js": (
                "/* datalens-protected:renderer:start */\n"
                "function createRender(rows) { return rows.length; }\n"
                "/* datalens-protected:renderer:end */\n"
                "const limit = /* datalens-slot:page:integer:start */50/* datalens-slot:page:end */;\n"
            ),
        }

    def test_protected_regions_survive_semantic_update(self) -> None:
        regions = build_protected_regions(self.tabs)
        slots = discover_semantic_slots(self.tabs)
        changed = apply_semantic_slot_updates(self.tabs, slots, {"page": 100})
        result = validate_protected_regions(self.tabs, changed, regions)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unchanged")

    def test_full_rewrite_requires_template_migration(self) -> None:
        regions = build_protected_regions(self.tabs)
        changed = dict(self.tabs, **{"prepare.js": "module.exports = {};\n"})
        blocked = validate_protected_regions(self.tabs, changed, regions)
        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked["expanded_acceptance_required"])
        allowed = validate_protected_regions(self.tabs, changed, regions, template_migration=True)
        self.assertTrue(allowed["ok"])
        self.assertEqual(allowed["status"], "migration_authorized")

    def test_stale_slot_is_rejected(self) -> None:
        slots = discover_semantic_slots(self.tabs)
        stale = dict(self.tabs, **{"prepare.js": self.tabs["prepare.js"].replace("50", "51")})
        with self.assertRaisesRegex(ValueError, "stale"):
            apply_semantic_slot_updates(stale, slots, {"page": 100})


if __name__ == "__main__":
    unittest.main()
