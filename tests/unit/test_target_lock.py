import unittest


class TargetLockTests(unittest.TestCase):
    def test_url_and_text_target_lock_is_hashable(self):
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        lock = create_target_lock(
            "Fix https://datalens.yandex.cloud/workbooks/wb_1/dashboards/dash_1",
            target_workbook_id="wb_1",
        )

        self.assertTrue(lock.known)
        self.assertEqual(lock.target_dashboard_id, "dash_1")
        self.assertEqual(len(lock.lock_hash), 64)

    def test_wrong_target_readback_fails(self):
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock, validate_target_delivery_trace

        lock = create_target_lock("update dashboard_id:dash_a", target_workbook_id="wb_1")
        result = validate_target_delivery_trace(
            {
                "target_lock": lock.to_dict(),
                "generated_widget_count": 2,
                "published_readback": {"dashboard": {"entry": {"entryId": "dash_b"}}, "active_widget_count": 0},
            }
        )

        self.assertFalse(result["ok"])
        self.assertTrue(any(item["rule"] for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
