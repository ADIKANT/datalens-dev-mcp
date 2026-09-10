"""Offline installed-wheel check; deliberately does not claim live acceptance."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

PROBE = r"""
import importlib.metadata
import json
from pathlib import Path
import datalens_dev_mcp
from datalens_dev_mcp.server import dl_server_info, list_tools
location = Path(datalens_dev_mcp.__file__).resolve()
assert "site-packages" in location.parts, str(location)
tools = list_tools()
names = [tool["name"] for tool in tools]
assert len(names) == len(set(names)) == 25, names
assert not any(name.startswith("dl_task_") for name in names)
assert importlib.metadata.version("datalens-dev-mcp") == datalens_dev_mcp.__version__
info = dl_server_info()
assert info['runtime']['import_kind'] == 'site-packages'
assert info['active_version_matches_installed'] is True
assert info['capability_revision']
assert len(info['build']['package_content_sha256']) == 64
assert info['build']['source_commit'] is None
print(json.dumps({"version": datalens_dev_mcp.__version__, "tools": names, 'active': info}))
"""


def main() -> None:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    with tempfile.TemporaryDirectory(prefix="datalens-installed-") as directory:
        subprocess.run([sys.executable, "-I", "-c", PROBE], cwd=directory, env=env, check=True)
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "installed-smoke", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "dl_server_info", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "dl_dataset_preview", "arguments": {"dataset_id": "synthetic",
                                                                       "columns": [{"guid": "bad-shape"}]}}},
        ]
        result = subprocess.run(
            [sys.executable, "-I", "-m", "datalens_dev_mcp.cli", "stdio"],
            input="".join(json.dumps(request) + "\n" for request in requests),
            text=True,
            capture_output=True,
            cwd=directory,
            env=env,
            timeout=20,
            check=True,
        )
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        assert [reply["id"] for reply in replies] == [1, 2, 3, 4], replies
        assert len(replies[1]["result"]["tools"]) == 25, replies
        info = replies[2]['result']['structuredContent']
        assert info['runtime']['import_kind'] == 'site-packages'
        assert info['active_version_matches_installed'] is True
        assert info['version'] == replies[0]['result']['serverInfo']['version']
        invalid = replies[3]['result']
        assert invalid['isError'] and invalid['structuredContent']['status'] == 'input_error'
        print(json.dumps({'stdio_active': info, 'invalid_input': 'rejected_before_provider'}))
        from pathlib import Path

        assert list(Path(directory).iterdir()) == [], "stdio wrote to the caller directory"
    print("Installed package import and stdio smoke passed (offline only)")


if __name__ == "__main__":
    main()
