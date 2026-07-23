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

    def test_action_set_lock_is_sorted_and_rejects_extra_target(self):
        from datalens_dev_mcp.pipeline.target_lock import (
            create_target_lock,
            validate_action_target_lock,
        )

        lock = create_target_lock(
            "fix existing objects",
            target_workbook_id="workbook_synthetic",
            target_objects=[
                {"method": "updateEditorChart", "object_id": "selector_synthetic"},
                {"method": "updateDashboard", "object_id": "dashboard_synthetic"},
            ],
        )
        reversed_lock = create_target_lock(
            "fix existing objects",
            target_workbook_id="workbook_synthetic",
            target_objects=list(reversed(lock.target_objects)),
        )

        self.assertTrue(lock.known)
        self.assertEqual(lock.lock_hash, reversed_lock.lock_hash)
        self.assertEqual(
            lock.target_objects,
            [
                {"method": "updateDashboard", "object_id": "dashboard_synthetic"},
                {"method": "updateEditorChart", "object_id": "selector_synthetic"},
            ],
        )
        result = validate_action_target_lock(
            lock,
            {
                "method": "updateEditorChart",
                "payload": {"entry": {"entryId": "unrelated_synthetic"}},
            },
        )
        dashboard_result = validate_action_target_lock(
            lock,
            {
                "method": "updateDashboard",
                "payload": {
                    "entry": {"entryId": "dashboard_synthetic"},
                },
                "fresh_read_payload": {
                    "dashboardId": "dashboard_synthetic",
                    "branch": "saved",
                },
            },
        )
        self.assertFalse(result["ok"])
        self.assertIn("outside the locked action set", result["findings"][0])
        self.assertTrue(dashboard_result["ok"], dashboard_result)

    def test_readback_identity_supports_response_entry_and_object_ids(self):
        from datalens_dev_mcp.pipeline.target_lock import (
            create_target_lock,
            validate_readback_target_lock,
        )

        lock = create_target_lock(
            "fix existing objects",
            target_workbook_id="workbook_synthetic",
            target_objects=[
                {"method": "updateEditorChart", "object_id": "selector_synthetic"},
                {"method": "updateDashboard", "object_id": "dashboard_synthetic"},
            ],
        )
        response_entry = validate_readback_target_lock(
            lock,
            {"response": {"entry": {"entryId": "selector_synthetic"}}},
        )
        object_ids = validate_readback_target_lock(
            lock,
            {
                "object_ids": [
                    {"object_id": "selector_synthetic"},
                    "dashboard_synthetic",
                ]
            },
        )

        self.assertTrue(response_entry["ok"], response_entry)
        self.assertTrue(object_ids["ok"], object_ids)


if __name__ == "__main__":
    unittest.main()
