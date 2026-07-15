import json
import tempfile
import unittest
from pathlib import Path


class DqReconciliationTests(unittest.TestCase):
    def test_bucket_totals_and_bridge_reconcile(self):
        from datalens_dev_mcp.pipeline.dq_reconciliation import classify_dq_reconciliation

        control = [
            {"business_key": "ORD-1", "stable_rk": "RK-1", "amount": 100},
            {"business_key": "ORD-2", "stable_rk": "RK-2", "amount": 200},
            {"business_key": "ORD-3", "stable_rk": "RK-3", "amount": 300},
            {"business_key": "ORD-4", "stable_rk": "RK-4", "amount": 400},
        ]
        evidence = [
            {
                "business_key": "ORD-1",
                "stable_rk": "RK-1",
                "raw_present": True,
                "current_edm_present": True,
                "edm_item_amount": 100,
                "dm_amount": 100,
                "dashboard_amount": 100,
            },
            {
                "business_key": "ORD-2-NEW",
                "stable_rk": "RK-2",
                "raw_present": True,
                "current_edm_present": True,
                "edm_item_amount": 200,
                "dm_amount": 200,
                "dashboard_amount": 200,
            },
            {
                "business_key": "ORD-3",
                "stable_rk": "RK-3",
                "raw_present": True,
                "current_edm_present": True,
                "edm_item_amount": 300,
                "dm_amount": 300,
                "dashboard_amount": 600,
                "fallback_duplicate": True,
                "dashboard_row_count": 2,
            },
            {
                "business_key": "ORD-4",
                "stable_rk": "RK-4",
                "raw_present": True,
                "current_edm_present": False,
                "edm_item_amount": 400,
                "dm_amount": 400,
                "dashboard_amount": 0,
            },
            {
                "business_key": "ORD-X",
                "stable_rk": "RK-X",
                "dashboard_amount": 50,
            },
        ]

        result = classify_dq_reconciliation(control, evidence)
        buckets = result["classification_buckets"]
        bridge = result["amount_count_bridge"]

        self.assertEqual(buckets["ok_exact_dm"]["count"], 1)
        self.assertEqual(buckets["ok_rk_renumbered"]["count"], 1)
        self.assertEqual(buckets["dashboard_logic_issue"]["count"], 1)
        self.assertEqual(buckets["missing_current_edm_order"]["count"], 1)
        self.assertEqual(buckets["extra_dashboard_row"]["count"], 1)
        self.assertEqual(sum(item["count"] for name, item in buckets.items() if name != "extra_dashboard_row"), 4)
        self.assertTrue(bridge["baseline_reconciles"])
        self.assertTrue(bridge["dashboard_reconciles"])
        self.assertEqual(bridge["baseline_amount"], 1000)
        self.assertEqual(bridge["dashboard_reproduction_amount"], 950)

    def test_mutable_order_number_is_classified_via_rk_and_duplicate_is_reported(self):
        from datalens_dev_mcp.pipeline.dq_reconciliation import classify_dq_reconciliation

        result = classify_dq_reconciliation(
            [{"business_key": "ORDER-OLD", "stable_rk": "RK-77", "amount": 10}],
            [
                {
                    "business_key": "ORDER-NEW",
                    "stable_rk": "RK-77",
                    "raw_present": True,
                    "current_edm_present": True,
                    "edm_item_amount": 10,
                    "dm_amount": 10,
                    "dashboard_amount": 10,
                    "dashboard_row_count": 2,
                }
            ],
        )

        self.assertEqual(result["classification_buckets"]["ok_rk_renumbered"]["count"], 1)
        self.assertTrue(result["classified_rows"][0]["resolved_by_stable_rk"])
        self.assertEqual(result["defects"][0]["type"], "fallback_duplicate")

    def test_report_blocks_dashboard_fix_when_upstream_contradicts_control(self):
        from datalens_dev_mcp.pipeline.dq_reconciliation import build_dq_before_after_report, classify_dq_reconciliation

        before = classify_dq_reconciliation(
            [{"business_key": "ORDER-1", "stable_rk": "RK-1", "amount": 99}],
            [
                {
                    "business_key": "ORDER-1",
                    "stable_rk": "RK-1",
                    "raw_present": True,
                    "source_status_conflict": True,
                    "current_edm_present": True,
                    "edm_item_amount": 99,
                    "dm_amount": 99,
                    "dashboard_amount": 99,
                }
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            report = build_dq_before_after_report(tmp, before)

        self.assertFalse(report["ok"])
        self.assertTrue(report["dashboard_fix_guard"]["blocked"])
        self.assertIn("source_status_conflict", report["dashboard_fix_guard"]["blocked_by_buckets"])

    def test_control_summary_omits_raw_rows_and_secret_like_keys(self):
        from datalens_dev_mcp.pipeline.dq_reconciliation import ingest_dq_control_summary

        with tempfile.TemporaryDirectory() as tmp:
            result = ingest_dq_control_summary(
                tmp,
                {
                    "baseline_count": 2,
                    "baseline_amount": 30,
                    "rows": [{"business_key": "ORDER-1"}, {"business_key": "ORDER-2"}],
                    "token": "secret-token-value",
                    "group_totals": [{"bucket": "a", "amount": 30}],
                },
            )
            artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))

        dumped = json.dumps(artifact, ensure_ascii=False)
        self.assertNotIn("secret-token-value", dumped)
        self.assertNotIn("ORDER-1", dumped)
        self.assertFalse(artifact["raw_control_file_committed"])
        self.assertIn("rows", artifact["omitted_keys"])
        self.assertEqual(artifact["control_summary"]["baseline_amount"], 30)

    def test_mcp_tools_are_registered(self):
        from datalens_dev_mcp.server import list_tools

        names = {item["name"] for item in list_tools("dq")}
        default_names = {item["name"] for item in list_tools()}

        for name in {
            "dl_ingest_dq_control_summary",
            "dl_build_dq_layer_reconciliation_plan",
            "dl_classify_dq_reconciliation",
            "dl_build_dq_before_after_report",
        }:
            self.assertIn(name, names)
            self.assertNotIn(name, default_names)

    def test_partial_create_reconciliation_output_is_json_serializable(self):
        from datalens_dev_mcp.pipeline.reconciliation import reconcile_partial_creates

        result = reconcile_partial_creates(
            workbook_id="wb_1",
            planned_objects=[{"object_type": "editor_chart", "internal_name": "Sales Chart", "display_title": "Sales"}],
            entries_payload={
                "entries": [
                    {
                        "entryId": "entry_1",
                        "scope": "chart",
                        "name": "sales_chart",
                        "displayKey": "Sales",
                    }
                ]
            },
        )

        json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["objects"][0]["matches"][0]["internal_names"], ["sales_chart"])


if __name__ == "__main__":
    unittest.main()
