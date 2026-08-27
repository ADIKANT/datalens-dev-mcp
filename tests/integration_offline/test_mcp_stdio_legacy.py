from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


class LegacyStdioSurfaceTests(unittest.TestCase):
    def test_legacy_surface_is_explicit_and_preserves_39_tools(self) -> None:
        env = {
            **os.environ,
            "PYTHONPATH": "src",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATALENS_MCP_TOOL_SURFACE": "legacy-v1",
        }
        code = (
            "import json; from datalens_dev_mcp.server import JsonRpcServer; "
            "s=JsonRpcServer(project_root='.'); "
            "i=s.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}); "
            "t=s.handle({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}); "
            "print(json.dumps({'instructions':i['result']['instructions'],"
            "'surface':t['result']['tool_surface'],"
            "'count':t['result']['tool_count']}))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("legacy-v1 surface", payload["instructions"])
        self.assertEqual(payload["surface"], "legacy-v1")
        self.assertEqual(payload["count"], 39)


if __name__ == "__main__":
    unittest.main()
