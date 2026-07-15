#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run([sys.executable, "scripts/run_acceptance_profile.py", "--profile", "standard"], check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
