import unittest


class DuplicateHeavySourcesAreDedupedTests(unittest.TestCase):
    def test_duplicate_heavy_sources_block_until_deduped(self):
        from datalens_dev_mcp.pipeline.performance_budget import assess_performance_budget

        sql = "WITH base AS (SELECT * FROM a LEFT JOIN b ON a.id=b.id) SELECT * FROM base LEFT JOIN c ON base.id=c.id"
        result = assess_performance_budget({"sources": [{"query": sql}, {"query": sql}]})

        self.assertFalse(result.publish_allowed)


if __name__ == "__main__":
    unittest.main()
