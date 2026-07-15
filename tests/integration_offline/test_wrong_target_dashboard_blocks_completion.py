import unittest


class WrongTargetDashboardBlocksCompletionTests(unittest.TestCase):
    def test_final_validation_fails_wrong_target(self):
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock, validate_target_delivery_trace

        lock = create_target_lock("publish dashboard_id:dash_user", target_workbook_id="wb_1")
        result = validate_target_delivery_trace(
            {
                "target_lock": lock.to_dict(),
                "generated_widget_count": 1,
                "published_readback": {"dashboard": {"entry": {"entryId": "dash_other"}}, "active_widget_count": 1},
            }
        )

        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
