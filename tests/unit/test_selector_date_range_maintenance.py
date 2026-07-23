import json
import tempfile
import unittest
from pathlib import Path


class SelectorDateRangeMaintenanceTests(unittest.TestCase):
    def test_static_date_controls_merge_preserves_unrelated_controls(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import merge_static_date_controls

        source = """module.exports = {
  controls: [
    {type: 'datepicker', param: 'period_from', label: 'From'},
    {type: 'select', param: 'team', content: [{title: 'All', value: 'all'}]},
    {type: 'datepicker', param: 'period_to', label: 'To'},
  ],
};
"""
        result = merge_static_date_controls(
            source,
            param_from="period_from",
            param_to="period_to",
            label="Period",
        )

        self.assertTrue(result["ok"], result)
        self.assertIn("type: 'range-datepicker'", result["source"])
        self.assertIn('paramFrom: "period_from"', result["source"])
        self.assertIn('paramTo: "period_to"', result["source"])
        self.assertIn("param: 'team'", result["source"])
        self.assertNotIn("updateControlsOnChange", result["source"])
        self.assertNotIn("param: 'period_from'", result["source"])
        self.assertNotIn("param: 'period_to'", result["source"])

    def test_static_date_controls_fail_closed_on_duplicate_parameter(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import merge_static_date_controls

        source = """module.exports = {controls: [
          {type: 'datepicker', param: 'period_from'},
          {type: 'datepicker', param: 'period_from'},
          {type: 'datepicker', param: 'period_to'},
        ]};"""
        result = merge_static_date_controls(
            source,
            param_from="period_from",
            param_to="period_to",
            label="Period",
        )

        self.assertFalse(result["ok"])
        self.assertIn("selector_controls.date_control_pair_ambiguous", result["blocked_reasons"])

    def test_dynamic_controls_fail_closed(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import merge_static_date_controls

        result = merge_static_date_controls(
            "module.exports = {controls: buildControls()};",
            param_from="period_from",
            param_to="period_to",
            label="Period",
        )

        self.assertFalse(result["ok"])
        self.assertIn("selector_controls.static_controls_array_required", result["blocked_reasons"])

        spread = merge_static_date_controls(
            """module.exports = {controls: [
              {type: 'datepicker', param: 'period_from'},
              {...buildControl()},
              {type: 'datepicker', param: 'period_to'},
            ]};""",
            param_from="period_from",
            param_to="period_to",
            label="Period",
        )
        mapped = merge_static_date_controls(
            """module.exports = {controls: [
              {type: 'datepicker', param: 'period_from'},
              {type: 'datepicker', param: 'period_to'},
            ].map(normalizeControl)};""",
            param_from="period_from",
            param_to="period_to",
            label="Period",
        )

        self.assertFalse(spread["ok"])
        self.assertIn(
            "selector_controls.dynamic_control_object",
            spread["blocked_reasons"],
        )
        self.assertFalse(mapped["ok"])
        self.assertIn(
            "selector_controls.static_controls_array_required",
            mapped["blocked_reasons"],
        )

    def test_multiple_dashboard_mounts_require_explicit_mount_id(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import patch_mounted_selector_defaults

        mounted = {
            "items": [
                {
                    "id": mount_id,
                    "data": {
                        "source": {"id": "selector_synthetic"},
                        "defaults": {"period_from": [], "period_to": []},
                    },
                }
                for mount_id in ("mount_a", "mount_b")
            ]
        }

        ambiguous = patch_mounted_selector_defaults(
            mounted,
            selector_object_id="selector_synthetic",
            mounted_control_id="",
            param_from="period_from",
            param_to="period_to",
            default_from="2026-01-01",
            default_to="2026-01-31",
        )
        selected = patch_mounted_selector_defaults(
            mounted,
            selector_object_id="selector_synthetic",
            mounted_control_id="mount_b",
            param_from="period_from",
            param_to="period_to",
            default_from="2026-01-01",
            default_to="2026-01-31",
        )
        mismatched = patch_mounted_selector_defaults(
            {
                "items": [
                    {
                        "id": "mount_b",
                        "data": {
                            "source": {"id": "different_selector"},
                            "defaults": {"period_from": [], "period_to": []},
                        },
                    }
                ]
            },
            selector_object_id="selector_synthetic",
            mounted_control_id="mount_b",
            param_from="period_from",
            param_to="period_to",
            default_from="2026-01-01",
            default_to="2026-01-31",
        )

        self.assertFalse(ambiguous["ok"])
        self.assertIn("dashboard_mount.ambiguous", ambiguous["blocked_reasons"])
        self.assertTrue(selected["ok"], selected)
        self.assertEqual(selected["mounted_control_id"], "mount_b")
        self.assertFalse(mismatched["ok"])
        self.assertIn("dashboard_mount.not_found", mismatched["blocked_reasons"])

    def test_params_patch_changes_only_requested_defaults(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import patch_params_defaults

        source = """module.exports = {
  period_from: ["old"],
  team: ["all"],
  period_to: [],
};
"""
        result = patch_params_defaults(
            source,
            param_from="period_from",
            param_to="period_to",
            default_from="2026-01-01",
            default_to="__relative_-0d",
        )

        self.assertTrue(result["ok"], result)
        self.assertIn('period_from: ["2026-01-01"]', result["source"])
        self.assertIn('period_to: ["__relative_-0d"]', result["source"])
        self.assertIn('team: ["all"]', result["source"])

        dynamic = patch_params_defaults(
            "module.exports = {period_from: [], ...runtimeParams, period_to: []};",
            param_from="period_from",
            param_to="period_to",
            default_from="2026-01-01",
            default_to="2026-01-31",
        )
        self.assertFalse(dynamic["ok"])
        self.assertIn("selector_params.dynamic_property", dynamic["blocked_reasons"])

    def test_semantic_compiler_builds_two_artifact_backed_updates(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import compile_date_range_selector_merge

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selector_path = root / "selector.saved.json"
            dashboard_path = root / "dashboard.saved.json"
            selector_path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "chart": {
                            "entry": {
                                "entryId": "selector_synthetic",
                                "revId": "selector_rev_1",
                                "data": {
                                    "meta": "{}",
                                    "params": (
                                        'module.exports = {period_from: ["2025-01-01"], '
                                        'period_to: [], team: ["all"]};'
                                    ),
                                    "sources": "[]",
                                    "controls": (
                                        "module.exports = {controls: ["
                                        "{type: 'datepicker', param: 'period_from', label: 'From'},"
                                        "{type: 'select', param: 'team'},"
                                        "{type: 'datepicker', param: 'period_to', label: 'To'}"
                                        "]};"
                                    ),
                                    "prepare": "module.exports = {};",
                                },
                                "meta": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            dashboard_path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "dashboard": {
                            "entry": {
                                "entryId": "dashboard_synthetic",
                                "revId": "dashboard_rev_1",
                                "data": {
                                    "items": [
                                        {
                                            "id": "mounted_selector",
                                            "layout": {"x": 0, "y": 0, "w": 12, "h": 2},
                                            "data": {
                                                "source": {"id": "selector_synthetic"},
                                                "defaults": {
                                                    "period_from": ["2025-01-01"],
                                                    "period_to": [],
                                                    "team": ["all"],
                                                },
                                            },
                                        }
                                    ],
                                    "settings": {"theme": "light"},
                                },
                                "meta": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            maintenance_contract = {
                "kind": "date_range_selector_merge",
                "selector_readback_path": str(selector_path),
                "dashboard_readback_path": str(dashboard_path),
                "selector_object_id": "selector_synthetic",
                "dashboard_id": "dashboard_synthetic",
                "selector_contract": {
                    "param_from": "period_from",
                    "param_to": "period_to",
                    "label": "Period",
                    "option_source": "none",
                    "default_from": "2026-01-01",
                    "default_to": "__relative_-0d",
                    "reset_behavior": "initial",
                },
            }
            result = compile_date_range_selector_merge(
                project_root=root,
                maintenance_contract=maintenance_contract,
            )
            from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

            safe_plan = dl_create_safe_apply_plan(
                project_root=str(root),
                delivery_intent_text="fix the selector",
                target_workbook_id="workbook_synthetic",
                maintenance_contract=maintenance_contract,
            )
            target_lock_exists = (root / "artifacts" / "delivery" / "target_lock.json").is_file()

        self.assertTrue(result["ok"], result)
        self.assertEqual([item["object_type"] for item in result["actions"]], ["control_node", "dashboard"])
        self.assertEqual(result["mounted_control_id"], "mounted_selector")
        self.assertEqual(result["workflow_metrics"]["max_datalens_rpc_count"], 14)
        selector_overlay = result["actions"][0]["desired_overlay"]["entry"]["data"]
        self.assertIn("range-datepicker", selector_overlay["controls"])
        self.assertNotIn("updateControlsOnChange", selector_overlay["controls"])
        dashboard_overlay = result["actions"][1]["desired_overlay"]["entry"]["data"]
        mounted_defaults = dashboard_overlay["items"][0]["data"]["defaults"]
        self.assertEqual(mounted_defaults["period_from"], ["2026-01-01"])
        self.assertEqual(mounted_defaults["period_to"], ["__relative_-0d"])
        self.assertEqual(mounted_defaults["team"], ["all"])
        self.assertEqual(dashboard_overlay["items"][0]["layout"], {"x": 0, "y": 0, "w": 12, "h": 2})
        self.assertTrue(safe_plan["ok"], safe_plan)
        self.assertEqual(len(safe_plan["actions"]), 2)
        self.assertEqual(safe_plan["target_lock"]["status"], "locked")
        self.assertEqual(
            safe_plan["target_lock"]["target_objects"],
            [
                {"method": "updateDashboard", "object_id": "dashboard_synthetic"},
                {"method": "updateEditorChart", "object_id": "selector_synthetic"},
            ],
        )
        self.assertTrue(safe_plan["runtime_smoke"]["required"])
        self.assertTrue(target_lock_exists)

    def test_rerender_risk_is_reported_for_paired_range(self):
        from datalens_dev_mcp.pipeline.selector_maintenance import date_range_rerender_findings

        source = """module.exports = {controls: [{
          type: 'range-datepicker',
          paramFrom: 'period_from',
          paramTo: 'period_to',
          updateOnChange: true,
          updateControlsOnChange: true,
        }]};"""

        findings = date_range_rerender_findings(source)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")

    def test_rerender_risk_is_nonblocking_for_general_editor_validation(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import (
            validate_editor_runtime_contract,
        )

        result = validate_editor_runtime_contract(
            {
                "data": {
                    "controls": """module.exports = {controls: [{
                      type: 'range-datepicker',
                      paramFrom: 'period_from',
                      paramTo: 'period_to',
                      updateControlsOnChange: true,
                    }]};"""
                }
            }
        )

        matching = [
            item
            for item in result["findings"]
            if item.get("rule") == "date_range_controls_rerender_risk"
        ]
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(matching), 1)

    def test_general_existing_update_uses_artifact_overlay_and_blocks_stale_identity(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readback = root / "editor.saved.json"
            readback.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "response": {
                            "entry": {
                                "entryId": "editor_synthetic",
                                "revId": "rev_synthetic",
                                "data": {
                                    "meta": "module.exports = {};",
                                    "params": "module.exports = {};",
                                    "sources": "module.exports = {};",
                                    "controls": "module.exports = {controls: []};",
                                    "prepare": "module.exports = {};",
                                    "futureField": {"preserve": True},
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            overlay = {
                "entry": {
                    "data": {
                        "controls": "module.exports = {controls: [{type: 'select', param: 'team'}]};"
                    }
                }
            }
            planned = dl_create_safe_apply_plan(
                project_root=tmp,
                delivery_intent_text="fix the existing editor",
                existing_update_actions=[
                    {
                        "object_type": "editor_chart",
                        "readback_path": str(readback),
                        "desired_overlay": overlay,
                    }
                ],
            )
            stale = dl_create_safe_apply_plan(
                project_root=tmp,
                delivery_intent_text="fix the existing editor",
                existing_update_actions=[
                    {
                        "object_type": "editor_chart",
                        "object_id": "different_synthetic",
                        "base_revision": "different_revision",
                        "readback_path": str(readback),
                        "desired_overlay": overlay,
                    }
                ],
            )

        self.assertTrue(planned["ok"], planned)
        preview_data = planned["actions"][0]["payload"]["entry"]["data"]
        self.assertEqual(preview_data["futureField"], {"preserve": True})
        self.assertIn("param: 'team'", preview_data["controls"])
        self.assertFalse(stale["ok"])
        self.assertIn(
            "existing_update[0].readback_object_id_mismatch",
            stale["blocked_reasons"],
        )
        self.assertIn(
            "existing_update[0].readback_revision_mismatch",
            stale["blocked_reasons"],
        )

    def test_public_tool_schema_types_the_date_range_maintenance_contract(self):
        from datalens_dev_mcp.server import list_tools

        tool = next(
            item
            for item in list_tools()
            if item["name"] == "dl_create_safe_apply_plan"
        )
        maintenance = tool["inputSchema"]["properties"]["maintenance_contract"]
        selector = maintenance["properties"]["selector_contract"]

        self.assertEqual(maintenance["properties"]["kind"]["const"], "date_range_selector_merge")
        self.assertEqual(
            set(maintenance["required"]),
            {
                "kind",
                "selector_readback_path",
                "dashboard_readback_path",
                "selector_object_id",
                "dashboard_id",
                "selector_contract",
            },
        )
        self.assertEqual(selector["type"], "object")
        self.assertEqual(selector["additionalProperties"], {"type": "string"})
        self.assertEqual(
            set(selector["required"]),
            {
                "param_from",
                "param_to",
                "label",
                "default_from",
                "default_to",
                "option_source",
                "reset_behavior",
            },
        )


if __name__ == "__main__":
    unittest.main()
