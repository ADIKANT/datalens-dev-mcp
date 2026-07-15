import unittest


class SlowTabBlocksPublishTests(unittest.TestCase):
    def test_20_second_tab_blocks_publish(self):
        from datalens_dev_mcp.pipeline.performance_budget import assess_performance_budget

        result = assess_performance_budget({"tabs": [{"id": "workflow", "observed_seconds": 20}]})

        self.assertFalse(result.publish_allowed)


if __name__ == "__main__":
    unittest.main()
