import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


WRITE_ENV = {
    "DATALENS_ENV_FILE": "",
    "DATALENS_MCP_ENABLE_WRITES": "1",
    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
}


def selector_entry():
    return {
        "entryId": "selector_synthetic",
        "revId": "selector_rev_1",
        "data": {
            "meta": "module.exports = {};",
            "params": (
                'module.exports = {period_from: ["2025-01-01"], '
                'period_to: [], team: ["all"]};'
            ),
            "sources": "module.exports = {};",
            "controls": (
                "module.exports = {controls: ["
                "{type: 'datepicker', param: 'period_from'},"
                "{type: 'select', param: 'team'},"
                "{type: 'datepicker', param: 'period_to'}"
                "]};"
            ),
            "prepare": "module.exports = {};",
            "futureField": {"preserve": True},
        },
        "meta": {},
    }


def dashboard_entry():
    return {
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
            "tabs": [],
            "settings": {"theme": "light"},
            "futureField": {"preserve": True},
        },
        "meta": {},
    }


class SyntheticDataLensClient:
    def __init__(self):
        self.calls = []
        self.saved = {}
        self.published = {}

    def rpc(self, method, payload):
        self.calls.append((method, deepcopy(payload)))
        object_type = "dashboard" if "Dashboard" in method else "chart"
        object_id = (
            payload.get("dashboardId")
            or payload.get("chartId")
            or (payload.get("entry") or {}).get("entryId")
        )
        baseline = dashboard_entry() if object_type == "dashboard" else selector_entry()
        if method.startswith("get"):
            branch = payload.get("branch")
            source = self.published if branch == "published" else self.saved
            return {object_type: {"entry": deepcopy(source.get(object_id, baseline))}}
        entry = deepcopy(payload["entry"])
        entry["revId"] = "rev_saved"
        if payload.get("mode") == "save":
            entry["savedId"] = f"saved_{object_id}"
            self.saved[object_id] = entry
        elif payload.get("mode") == "publish":
            entry.pop("savedId", None)
            self.published[object_id] = entry
        else:
            raise AssertionError(f"unexpected write mode: {payload}")
        return {object_type: {"entry": deepcopy(entry)}}


class DateRangeSelectorFastPathTests(unittest.TestCase):
    def test_semantic_plan_executes_grouped_save_and_grouped_publish(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_create_safe_apply_plan,
            dl_execute_safe_apply,
        )
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply as real_execute

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            WRITE_ENV,
            clear=False,
        ):
            root = Path(tmp)
            (root / "selector.saved.json").write_text(
                json.dumps({"branch": "saved", "chart": {"entry": selector_entry()}}),
                encoding="utf-8",
            )
            (root / "dashboard.saved.json").write_text(
                json.dumps(
                    {"branch": "saved", "dashboard": {"entry": dashboard_entry()}}
                ),
                encoding="utf-8",
            )
            maintenance_contract = {
                "kind": "date_range_selector_merge",
                "selector_readback_path": "selector.saved.json",
                "dashboard_readback_path": "dashboard.saved.json",
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
            plan = dl_create_safe_apply_plan(
                project_root=tmp,
                delivery_intent_text="fix the existing selector",
                target_workbook_id="workbook_synthetic",
                maintenance_contract=maintenance_contract,
            )
            client = SyntheticDataLensClient()

            def execute_with_client(plan_arg, *, config):
                return real_execute(
                    plan_arg,
                    config=DataLensConfig(write_enabled=config.write_enabled),
                    client=client,
                )

            with patch(
                "datalens_dev_mcp.mcp.tools.pipeline.execute_safe_apply",
                side_effect=execute_with_client,
            ):
                result = dl_execute_safe_apply(
                    tmp,
                    delivery_intent_text="fix the existing selector",
                )

        self.assertTrue(plan["ok"], plan)
        self.assertTrue(result["executed"], result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["publish_results"]), 1)
        self.assertEqual(result["publish_results"][0]["plan"]["object_count"], 2)
        self.assertEqual(len(client.calls), 12)
        self.assertEqual(len(result["saved_readback_paths"]), 2)
        self.assertEqual(len(result["published_readback_paths"]), 2)
        self.assertEqual(result["workflow_metrics"]["observed_total_rpc_count"], 14)
        self.assertTrue(result["workflow_metrics"]["budget_met"])
        self.assertEqual(result["workflow_metrics"]["publish_group_count"], 1)
        self.assertEqual(
            result["maintenance_completion"]["status"],
            "runtime_smoke_required",
        )
        self.assertEqual(result["runtime_smoke"]["status"], "required")
        published_selector = client.published["selector_synthetic"]
        published_dashboard = client.published["dashboard_synthetic"]
        self.assertIn("range-datepicker", published_selector["data"]["controls"])
        self.assertNotIn(
            "updateControlsOnChange",
            published_selector["data"]["controls"],
        )
        self.assertIn('period_from: ["2026-01-01"]', published_selector["data"]["params"])
        self.assertIn('period_to: ["__relative_-0d"]', published_selector["data"]["params"])
        self.assertEqual(
            published_selector["data"]["futureField"],
            {"preserve": True},
        )
        mounted = published_dashboard["data"]["items"][0]
        self.assertEqual(
            mounted["data"]["defaults"]["period_from"],
            ["2026-01-01"],
        )
        self.assertEqual(
            mounted["data"]["defaults"]["period_to"],
            ["__relative_-0d"],
        )
        self.assertEqual(mounted["data"]["defaults"]["team"], ["all"])
        self.assertEqual(mounted["layout"], {"x": 0, "y": 0, "w": 12, "h": 2})
        self.assertEqual(
            published_dashboard["data"]["futureField"],
            {"preserve": True},
        )


if __name__ == "__main__":
    unittest.main()
