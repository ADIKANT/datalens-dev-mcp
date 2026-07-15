import unittest


class PerformanceBudgetPolicyTests(unittest.TestCase):
    def test_slow_tab_blocks_publish(self):
        from datalens_dev_mcp.pipeline.performance_budget import assess_performance_budget

        result = assess_performance_budget({"tabs": [{"id": "workflow", "observed_seconds": 20}]})

        self.assertFalse(result.publish_allowed)
        self.assertIn("observed_20_second_tab", {finding.rule for finding in result.findings})

    def test_duplicate_heavy_sources_block_publish(self):
        from datalens_dev_mcp.pipeline.performance_budget import assess_performance_budget

        sql = "WITH base AS (SELECT * FROM a LEFT JOIN b ON a.id=b.id) SELECT * FROM base LEFT JOIN c ON base.id=c.id"
        result = assess_performance_budget({"sources": [{"query": sql}, {"query": sql}]})

        self.assertFalse(result.publish_allowed)
        self.assertIn("duplicated_heavy_source_without_cache", {finding.rule for finding in result.findings})


if __name__ == "__main__":
    unittest.main()
