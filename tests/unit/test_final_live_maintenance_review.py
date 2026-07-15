import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


def _dashboard(right_x: int) -> dict:
    return {
        "entry": {
            "entryId": "dash_1",
            "revId": "rev_1",
            "meta": {},
            "data": {
                "tabs": [
                    {
                        "id": "tab_1",
                        "title": "Overview",
                        "items": [
                            {"id": "left", "type": "widget"},
                            {"id": "right", "type": "widget"},
                        ],
                        "globalItems": [],
                        "layout": [
                            {"i": "left", "x": 0, "y": 0, "w": 18, "h": 8},
                            {"i": "right", "x": right_x, "y": 0, "w": 18, "h": 8},
                        ],
                    }
                ]
            },
        }
    }


def _dashboard_action(*, baseline: dict | None = None, contract: dict | None = None) -> dict:
    action = {
        "action": "update_dashboard",
        "method": "updateDashboard",
        "object_id": "dash_1",
        "payload": {"mode": "save", **_dashboard(12)},
        "fresh_read_method": "getDashboard",
        "fresh_read_payload": {"dashboardId": "dash_1", "branch": "saved"},
        "readback_method": "getDashboard",
        "readback_payload": {"dashboardId": "dash_1", "branch": "saved"},
    }
    if baseline is not None:
        action["current_dashboard"] = baseline
        action["baseline_dashboard"] = baseline
    if contract is not None:
        action["baseline_diff_contract"] = contract
    return action


class FinalLiveMaintenanceReviewTests(unittest.TestCase):
    def test_chart_write_ids_are_separate_from_dashboard_browser_scope(self):
        from datalens_dev_mcp.pipeline import live_maintenance as live

        completion = {
            "phase": {"name": "completion_evidence", "status": "verified", "artifact_paths": []},
            "completion_ready": True,
            "missing_evidence": [],
            "blocked_reasons": [],
            "safe_apply_execution": {},
            "saved_readback": {},
            "publish_from_saved": {},
            "published_readback": {},
            "artifact_paths": [],
        }
        runtime = {
            "phase": {"name": "runtime_gate", "status": "passed", "artifact_paths": []},
            "evidence": {"status": "passed", "marker_counts": {}},
            "runtime_smoke": {"status": "passed"},
            "artifact_path": "",
        }
        safe_phase = {
            "phase": {"name": "safe_apply", "status": "planned", "artifact_paths": []},
            "blocked_reasons": [],
            "plan": {},
        }
        chart_action = {
            "method": "updateEditorChart",
            "object_id": "chart_1",
            "payload": {"entry": {"entryId": "chart_1"}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(live, "_safe_apply_phase", return_value=safe_phase),
                patch.object(live, "_completion_evidence_phase", return_value=completion) as completion_mock,
                patch.object(live, "_runtime_gate_phase", return_value=runtime) as runtime_mock,
            ):
                result = live.run_live_maintenance_update(
                    project_root=tmp,
                    workbook_id="wb_1",
                    dashboard_id="dash_1",
                    target_tab_id="tab_1",
                    safe_apply_actions=[chart_action],
                    target_url="https://datalens.example/dash_1",
                    runtime_gate_evidence={"status": "passed"},
                    approved=True,
                    publish=False,
                )

        self.assertEqual(result["status"], "done")
        self.assertEqual(completion_mock.call_args.kwargs["required_object_ids"], ["chart_1"])
        self.assertEqual(runtime_mock.call_args.kwargs["required_object_ids"], ["chart_1", "dash_1"])

    def test_dashboard_plan_requires_baseline_and_differential_contract(self):
        from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        baseline = _dashboard(12)
        contract = build_baseline_diff_contract(
            dashboard_id="dash_1",
            baseline_dashboard=baseline,
            proposed_dashboard={"mode": "save", **_dashboard(12)},
        )
        without_contract = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[_dashboard_action()],
        )
        with_contract = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[_dashboard_action(baseline=baseline, contract=contract)],
        )

        missing = validate_safe_apply_plan_exhaustive(without_contract)
        valid = validate_safe_apply_plan_exhaustive(with_contract)

        self.assertFalse(missing["ok"])
        self.assertIn("current_dashboard baseline", "\n".join(missing["issues"]))
        self.assertIn("baseline_diff_contract", "\n".join(missing["issues"]))
        self.assertTrue(valid["ok"], valid["issues"])

    def test_dashboard_content_update_preserves_fresh_geometry_before_write(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        baseline = _dashboard(12)
        contract = build_baseline_diff_contract(
            dashboard_id="dash_1",
            baseline_dashboard=baseline,
            proposed_dashboard={"mode": "save", **_dashboard(12)},
        )

        class FreshDashboardClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict]] = []

            def rpc(self, method: str, payload: dict) -> dict:
                self.calls.append((method, payload))
                return _dashboard(18)

        with tempfile.TemporaryDirectory() as tmp:
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[_dashboard_action(baseline=baseline, contract=contract)],
            )
            client = FreshDashboardClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual([method for method, _ in client.calls], ["getDashboard", "updateDashboard", "getDashboard"])
        write_payload = client.calls[1][1]
        self.assertEqual(write_payload["entry"]["data"]["tabs"][0]["layout"][1]["x"], 18)

    def test_fabricated_empty_dashboard_contract_cannot_hide_removed_object(self):
        from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        baseline = _dashboard(18)
        baseline["entry"]["data"]["tabs"][0]["items"][1]["data"] = {"chartId": "chart_removed"}
        proposed = deepcopy(baseline)
        proposed["entry"]["data"]["tabs"][0]["items"] = proposed["entry"]["data"]["tabs"][0]["items"][:1]
        proposed["entry"]["data"]["tabs"][0]["layout"] = proposed["entry"]["data"]["tabs"][0]["layout"][:1]
        payload = {"mode": "save", **proposed}
        actual_contract = build_baseline_diff_contract(
            dashboard_id="dash_1",
            baseline_dashboard=baseline,
            proposed_dashboard=payload,
        )
        fabricated = deepcopy(actual_contract)
        fabricated["unexpected_layout_diff"] = []
        fabricated["blocked_reasons"] = []
        action = _dashboard_action(baseline=baseline, contract=fabricated)
        action["payload"] = payload
        plan = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[action],
        )

        result = validate_safe_apply_plan_exhaustive(plan)
        joined = "\n".join(result["issues"])

        self.assertFalse(result["ok"])
        self.assertIn("stale or unbound", joined)
        self.assertIn("broad_rebuild_or_object_drop_requires_explicit_authorization", joined)

    def test_publish_saved_source_object_must_equal_action_object(self):
        from datalens_dev_mcp.pipeline.live_maintenance import _saved_source_matches_publish_action

        action = {"object_id": "chart_1"}
        self.assertTrue(_saved_source_matches_publish_action(action, {"object_id": "chart_1"}))
        self.assertFalse(_saved_source_matches_publish_action(action, {"object_id": "chart_other"}))
        self.assertFalse(_saved_source_matches_publish_action(action, {}))

    def test_expected_titles_are_target_scoped_and_never_use_internal_name(self):
        from datalens_dev_mcp.pipeline.live_maintenance import _expected_runtime_titles

        proposed = {
            "entry": {
                "data": {
                    "tabs": [
                        {
                            "id": "tab_target",
                            "title": "Target tab",
                            "items": [
                                {
                                    "id": "widget_target",
                                    "title": "Target widget",
                                    "data": {
                                        "tabs": [
                                            {"id": "inner", "chartId": "chart_1", "title": "Target chart"}
                                        ]
                                    },
                                },
                                {
                                    "id": "widget_other",
                                    "title": "Other widget",
                                    "data": {"chartId": "chart_other"},
                                },
                            ],
                        },
                        {"id": "tab_other", "title": "Other tab", "items": []},
                    ]
                }
            }
        }
        titles = _expected_runtime_titles(
            changed_objects=[
                {"object_id": "chart_1", "title": "Changed target", "name": "internal_chart_1"},
                {"object_id": "chart_other", "title": "Changed other"},
            ],
            proposed_dashboard=proposed,
            safe_apply_actions=[
                {
                    "method": "updateEditorChart",
                    "object_id": "chart_1",
                    "payload": {
                        "entry": {
                            "entryId": "chart_1",
                            "name": "internal_entry_name",
                            "data": {"title": "Action target"},
                        }
                    },
                }
            ],
            required_object_ids=["chart_1"],
            target_tab_id="tab_target",
        )

        self.assertEqual(
            set(titles),
            {"Changed target", "Action target", "Target tab", "Target widget", "Target chart"},
        )
        self.assertNotIn("internal_chart_1", titles)
        self.assertNotIn("internal_entry_name", titles)
        self.assertNotIn("Other widget", titles)
        self.assertNotIn("Other tab", titles)

    def test_rendering_scope_is_derived_from_capture_or_blocks_when_missing(self):
        from datalens_dev_mcp.pipeline.live_maintenance import _resolve_rendering_scope

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / "capture.json"
            capture.write_text(
                json.dumps(
                    {
                        "target_url": "https://datalens.example/dash_1",
                        "tab_id": "tab_1",
                    }
                ),
                encoding="utf-8",
            )
            derived = _resolve_rendering_scope(
                root,
                runtime_gate_evidence={
                    "status": "passed",
                    "browser_capture_artifact": str(capture),
                },
                target_url="",
                target_tab_id="",
                browser_runtime_required=True,
                non_rendering_exemption="",
            )
            missing = _resolve_rendering_scope(
                root,
                runtime_gate_evidence={"status": "passed"},
                target_url="",
                target_tab_id="",
                browser_runtime_required=True,
                non_rendering_exemption="",
            )

        self.assertEqual(derived["target_url"], "https://datalens.example/dash_1")
        self.assertEqual(derived["target_tab_id"], "tab_1")
        self.assertEqual(derived["blocked_reasons"], [])
        self.assertEqual(
            missing["blocked_reasons"],
            ["rendering_run_requires_target_url", "rendering_run_requires_target_tab_id"],
        )


if __name__ == "__main__":
    unittest.main()
