from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload


REPO_ROOT = Path(__file__).resolve().parents[2]


def _payload(
    *,
    items: list[dict[str, object]],
    layout: list[dict[str, object]],
    global_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "tabs": [
            {
                "id": "overview",
                "title": "Overview",
                "items": items,
                "globalItems": global_items or [],
                "layout": layout,
            }
        ]
    }


class DashboardGridContractTests(unittest.TestCase):
    def test_lightweight_planning_tabs_with_string_references_are_not_native_grid_payloads(self):
        payload = {
            "tabs": [{"id": "overview", "items": ["widget_1"]}],
            "items": [{"id": "widget_1", "type": "widget"}],
        }

        result = validate_dashboard_payload(payload)

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])
        self.assertFalse(any(issue.rule == "malformed_dashboard_item" for issue in result.issues))

    def test_valid_native_grid_maps_items_and_global_items_one_to_one(self):
        payload = _payload(
            items=[
                {"id": "section_title", "type": "title", "data": {"text": "Summary"}},
                {
                    "id": "kpi_revenue",
                    "type": "widget",
                    "data": {"tabs": [{"id": "kpi_tab", "chartId": "chart_kpi", "title": "Revenue metric"}]},
                },
                {
                    "id": "detail_table",
                    "type": "widget",
                    "data": {"tabs": [{"id": "table_tab", "chartId": "chart_table", "title": "Detail table"}]},
                },
            ],
            global_items=[{"id": "period_control", "type": "group_control", "data": {"autoHeight": True}}],
            layout=[
                {"i": "period_control", "x": 0, "y": 0, "w": 36, "h": 2},
                {"i": "section_title", "x": 0, "y": 2, "w": 36, "h": 2},
                {"i": "kpi_revenue", "x": 0, "y": 4, "w": 9, "h": 6},
                {"i": "detail_table", "x": 0, "y": 10, "w": 36, "h": 14},
            ],
        )

        result = validate_dashboard_payload(payload)

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])
        self.assertFalse(any(issue.rule.startswith(("missing_item", "orphan_layout")) for issue in result.issues))

    def test_grid_rejects_duplicate_missing_orphan_and_invalid_geometry(self):
        payload = _payload(
            items=[
                {"id": "item_a", "type": "widget"},
                {"id": "item_b", "type": "widget"},
            ],
            layout=[
                {"i": "item_a", "x": 0, "y": 0, "w": 0, "h": 6},
                {"i": "item_a", "x": 0, "y": 7, "w": 6, "h": 6},
                {"i": "orphan", "x": 35, "y": 0, "w": 2, "h": 2},
            ],
        )

        result = validate_dashboard_payload(payload)
        rules = {issue.rule for issue in result.issues}

        self.assertFalse(result.ok)
        self.assertTrue(
            {
                "duplicate_layout_id",
                "missing_item_layout",
                "orphan_layout_id",
                "invalid_layout_geometry",
                "layout_exceeds_36_columns",
            }.issubset(rules),
            rules,
        )

    def test_parented_fixed_children_are_not_ordinary_peer_overlaps(self):
        items = [
            {"id": "content", "type": "widget"},
            {"id": "fixed_control", "type": "control"},
            {"id": "fixed_global_control", "type": "control"},
        ]
        fixed_payload = _payload(
            items=items,
            layout=[
                {"i": "content", "x": 0, "y": 0, "w": 36, "h": 12},
                {"i": "fixed_control", "x": 0, "y": 0, "w": 12, "h": 2, "parent": "__fixHead"},
                {"i": "fixed_global_control", "x": 0, "y": 0, "w": 12, "h": 2, "parent": "__fixGCont"},
            ],
        )
        peer_payload = _payload(
            items=items,
            layout=[
                {"i": "content", "x": 0, "y": 0, "w": 36, "h": 12},
                {"i": "fixed_control", "x": 0, "y": 0, "w": 12, "h": 2},
                {"i": "fixed_global_control", "x": 12, "y": 0, "w": 12, "h": 2},
            ],
        )

        fixed_result = validate_dashboard_payload(fixed_payload)
        peer_result = validate_dashboard_payload(peer_payload)

        self.assertTrue(fixed_result.ok, [issue.to_dict() for issue in fixed_result.issues])
        self.assertFalse(peer_result.ok)
        self.assertTrue(any(issue.rule == "peer_layout_overlap" for issue in peer_result.issues))

    def test_grid_rejects_orphan_self_and_cyclic_layout_parents(self):
        payload = _payload(
            items=[
                {"id": "orphan", "type": "widget"},
                {"id": "self_parent", "type": "widget"},
                {"id": "cycle_a", "type": "widget"},
                {"id": "cycle_b", "type": "widget"},
            ],
            layout=[
                {"i": "orphan", "x": 0, "y": 0, "w": 6, "h": 4, "parent": "missing"},
                {"i": "self_parent", "x": 0, "y": 0, "w": 6, "h": 4, "parent": "self_parent"},
                {"i": "cycle_a", "x": 0, "y": 0, "w": 6, "h": 4, "parent": "cycle_b"},
                {"i": "cycle_b", "x": 0, "y": 0, "w": 6, "h": 4, "parent": "cycle_a"},
            ],
        )

        result = validate_dashboard_payload(payload)
        rules = {issue.rule for issue in result.issues}

        self.assertFalse(result.ok)
        self.assertTrue({"orphan_layout_parent", "self_layout_parent", "layout_parent_cycle"}.issubset(rules), rules)

    def test_real_parent_checks_child_bounds_and_sibling_overlap(self):
        items = [
            {"id": "group", "type": "widget"},
            {"id": "left", "type": "widget"},
            {"id": "right", "type": "widget"},
        ]
        valid = _payload(
            items=items,
            layout=[
                {"i": "group", "x": 0, "y": 0, "w": 12, "h": 8},
                {"i": "left", "x": 0, "y": 0, "w": 6, "h": 4, "parent": "group"},
                {"i": "right", "x": 6, "y": 0, "w": 6, "h": 4, "parent": "group"},
            ],
        )
        invalid = _payload(
            items=items,
            layout=[
                {"i": "group", "x": 0, "y": 0, "w": 12, "h": 8},
                {"i": "left", "x": 0, "y": 0, "w": 8, "h": 4, "parent": "group"},
                {"i": "right", "x": 7, "y": 0, "w": 6, "h": 4, "parent": "group"},
            ],
        )

        valid_result = validate_dashboard_payload(valid)
        invalid_result = validate_dashboard_payload(invalid)
        invalid_rules = {issue.rule for issue in invalid_result.issues}

        self.assertTrue(valid_result.ok, [issue.to_dict() for issue in valid_result.issues])
        self.assertFalse(invalid_result.ok)
        self.assertIn("child_layout_exceeds_parent_bounds", invalid_rules)
        self.assertIn("peer_layout_overlap", invalid_rules)

    def test_unchanged_legacy_peer_overlap_is_preservation_compatible(self):
        legacy = _payload(
            items=[
                {"id": "created_closed", "type": "widget"},
                {"id": "alert", "type": "widget"},
            ],
            layout=[
                {"i": "created_closed", "x": 0, "y": 14, "w": 16, "h": 9},
                {"i": "alert", "x": 0, "y": 8, "w": 5, "h": 12},
            ],
        )

        result = validate_dashboard_payload(legacy, current_dashboard=legacy)

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])
        self.assertFalse(any(issue.rule == "peer_layout_overlap" for issue in result.issues))

    def test_proposed_change_cannot_introduce_peer_overlap(self):
        current = _payload(
            items=[{"id": "left", "type": "widget"}, {"id": "right", "type": "widget"}],
            layout=[
                {"i": "left", "x": 0, "y": 0, "w": 18, "h": 8},
                {"i": "right", "x": 18, "y": 0, "w": 18, "h": 8},
            ],
        )
        proposed = _payload(
            items=[{"id": "left", "type": "widget"}, {"id": "right", "type": "widget"}],
            layout=[
                {"i": "left", "x": 0, "y": 0, "w": 18, "h": 8},
                {"i": "right", "x": 12, "y": 0, "w": 18, "h": 8},
            ],
        )

        result = validate_dashboard_payload(proposed, current_dashboard=current)

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "peer_layout_overlap" for issue in result.issues))

    def test_existing_item_geometry_change_warns_and_requires_runtime_review(self):
        current = _payload(
            items=[{"id": "existing", "type": "widget"}],
            layout=[{"i": "existing", "x": 0, "y": 0, "w": 12, "h": 6}],
        )
        proposed = _payload(
            items=[{"id": "existing", "type": "widget"}],
            layout=[{"i": "existing", "x": 1, "y": 0, "w": 12, "h": 7}],
        )

        result = validate_dashboard_payload(proposed, current_dashboard=current)

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])
        issue = next(item for item in result.issues if item.rule == "existing_layout_geometry_changed")
        self.assertEqual(issue.severity, "warning")

    def test_layout_ownership_rejects_geometry_changes_outside_changed_object_ids(self):
        current = _payload(
            items=[{"id": "owned", "type": "widget"}, {"id": "preserved", "type": "widget"}],
            layout=[
                {"i": "owned", "x": 0, "y": 0, "w": 18, "h": 8},
                {"i": "preserved", "x": 18, "y": 0, "w": 18, "h": 8},
            ],
        )
        proposed = _payload(
            items=[{"id": "owned", "type": "widget"}, {"id": "preserved", "type": "widget"}],
            layout=[
                {"i": "owned", "x": 0, "y": 0, "w": 18, "h": 7},
                {"i": "preserved", "x": 18, "y": 0, "w": 18, "h": 7},
            ],
        )

        result = validate_dashboard_payload(
            proposed,
            current_dashboard=current,
            project_contract={"layout_ownership": {"changed_object_ids": ["owned"]}},
        )

        self.assertFalse(result.ok)
        ownership_issues = [issue for issue in result.issues if issue.rule == "unowned_layout_geometry_change"]
        self.assertEqual([issue.path for issue in ownership_issues], ["$.tabs[0].layout[1]"])
        self.assertIn("'preserved'", ownership_issues[0].message)

    def test_layout_ownership_allows_geometry_changes_for_owned_objects(self):
        current = {
            "entry": {
                "data": {
                    **_payload(
                        items=[{"id": "owned", "type": "widget"}],
                        layout=[{"i": "owned", "x": 0, "y": 0, "w": 18, "h": 8}],
                    )
                }
            }
        }
        proposed = {
            "data": {
                **_payload(
                    items=[{"id": "owned", "type": "widget"}],
                    layout=[{"i": "owned", "x": 0, "y": 0, "w": 18, "h": 7}],
                )
            }
        }

        result = validate_dashboard_payload(
            proposed,
            current_dashboard=current,
            project_contract={"layout_ownership": {"changed_object_ids": ["owned"]}},
        )

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])
        self.assertTrue(any(issue.rule == "existing_layout_geometry_changed" for issue in result.issues))
        self.assertFalse(any(issue.rule == "unowned_layout_geometry_change" for issue in result.issues))

    def test_semantic_noop_rejects_geometry_drift_even_for_owned_objects(self):
        current = _payload(
            items=[{"id": "owned", "type": "widget"}],
            layout=[{"i": "owned", "x": 0, "y": 0, "w": 18, "h": 8, "parent": "__fixHead"}],
        )
        proposed = _payload(
            items=[{"id": "owned", "type": "widget"}],
            layout=[{"i": "owned", "x": 0, "y": 0, "w": 18, "h": 8, "parent": "__fixGCont"}],
        )

        result = validate_dashboard_payload(
            proposed,
            current_dashboard=current,
            project_contract={
                "layout_ownership": {
                    "changed_object_ids": ["owned"],
                    "semantic_noop": True,
                }
            },
        )

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "semantic_noop_layout_geometry_drift" for issue in result.issues))

    def test_changed_legacy_overlap_is_not_exempted(self):
        current = _payload(
            items=[{"id": "left", "type": "widget"}, {"id": "right", "type": "widget"}],
            layout=[
                {"i": "left", "x": 0, "y": 0, "w": 18, "h": 8},
                {"i": "right", "x": 12, "y": 0, "w": 18, "h": 8},
            ],
        )
        proposed = _payload(
            items=[{"id": "left", "type": "widget"}, {"id": "right", "type": "widget"}],
            layout=[
                {"i": "left", "x": 0, "y": 0, "w": 20, "h": 8},
                {"i": "right", "x": 12, "y": 0, "w": 18, "h": 8},
            ],
        )

        result = validate_dashboard_payload(proposed, current_dashboard=current)

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "peer_layout_overlap" for issue in result.issues))

    def test_height_and_auto_height_guidance_is_warning_only(self):
        payload = _payload(
            items=[
                {"id": "title", "type": "title"},
                {"id": "filters", "type": "group_control", "data": {"autoHeight": True}},
                {
                    "id": "kpi_orders",
                    "type": "widget",
                    "data": {"tabs": [{"id": "orders", "chartId": "orders_chart", "title": "Orders metric"}]},
                },
                {
                    "id": "compact_table",
                    "type": "widget",
                    "data": {"tabs": [{"id": "details", "chartId": "details_chart", "title": "Details table"}]},
                },
                {
                    "id": "mixed_height_widget",
                    "type": "widget",
                    "data": {
                        "tabs": [
                            {"id": "mixed_a", "chartId": "mixed_a_chart", "title": "A", "autoHeight": True},
                            {"id": "mixed_b", "chartId": "mixed_b_chart", "title": "B", "autoHeight": False},
                        ]
                    },
                },
            ],
            layout=[
                {"i": "title", "x": 0, "y": 0, "w": 36, "h": 3},
                {"i": "filters", "x": 0, "y": 3, "w": 36, "h": 5},
                {"i": "kpi_orders", "x": 0, "y": 8, "w": 9, "h": 8},
                {"i": "compact_table", "x": 0, "y": 16, "w": 36, "h": 6},
                {"i": "mixed_height_widget", "x": 0, "y": 22, "w": 36, "h": 10},
            ],
        )

        result = validate_dashboard_payload(payload)
        warning_rules = {issue.rule for issue in result.issues if issue.severity == "warning"}

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])
        self.assertTrue(
            {
                "atypical_title_height",
                "atypical_control_height",
                "atypical_kpi_height",
                "atypical_table_height",
                "mixed_widget_auto_height",
            }.issubset(warning_rules),
            warning_rules,
        )

    def test_layout_schema_and_packaged_mirror_require_integer_grid_geometry(self):
        schema_path = REPO_ROOT / "schemas" / "dashboard-layout-spec.schema.json"
        packaged_path = REPO_ROOT / "src" / "datalens_dev_mcp" / "assets" / "schemas" / schema_path.name
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        packaged = json.loads(packaged_path.read_text(encoding="utf-8"))
        self.assertEqual(schema, packaged)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        valid = {
            "dashboard_name": "Grid contract",
            "desktop_grid": "36 columns",
            "tabs": [
                {
                    "id": "overview",
                    "items": [{"id": "metric", "type": "widget"}],
                    "globalItems": [],
                    "layout": [{"i": "metric", "x": 0, "y": 0, "w": 9, "h": 6}],
                }
            ],
        }
        invalid = json.loads(json.dumps(valid))
        invalid["tabs"][0]["layout"][0]["w"] = 0

        self.assertEqual(list(validator.iter_errors(valid)), [])
        self.assertTrue(list(validator.iter_errors(invalid)))


if __name__ == "__main__":
    unittest.main()
