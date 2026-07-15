import os
import unittest


class LivePlanTests(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("DATALENS_MCP_RUN_LIVE_TESTS") == "1",
        "set DATALENS_MCP_RUN_LIVE_TESTS=1 with disposable DataLens credentials to run live tests",
    )
    def test_auth_probe_requires_explicit_live_credentials(self):
        if not os.getenv("DATALENS_ORG_ID") or not os.getenv("DATALENS_IAM_TOKEN"):
            self.skipTest("BLOCKED_LIVE_CREDENTIALS")

        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_probe_auth

        result = dl_probe_auth()
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
