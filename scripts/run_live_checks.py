#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    if os.getenv("DATALENS_MCP_RUN_LIVE_TESTS") != "1":
        print("Live tests are opt-in. Set DATALENS_MCP_RUN_LIVE_TESTS=1 with disposable credentials.")
        return 0
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    commands = [
        [sys.executable, "scripts/live_smoke_readonly.py"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests/live", "-p", "test_*.py", "-v"],
    ]
    for command in commands:
        print("+ " + " ".join(command), flush=True)
        result = subprocess.run(command, check=False, env=env)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
