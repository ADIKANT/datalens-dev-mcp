#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    autonomy = subprocess.run([sys.executable, "scripts/run_autonomy_acceptance.py"], check=False)
    if autonomy.returncode != 0:
        return autonomy.returncode
    standard = subprocess.run([sys.executable, "scripts/run_acceptance_profile.py", "--profile", "standard"], check=False)
    return standard.returncode


if __name__ == "__main__":
    raise SystemExit(main())
