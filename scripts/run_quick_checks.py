#!/usr/bin/env python3
"""Run the quick profile, including the synthetic session-regression contracts."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run([sys.executable, "scripts/run_acceptance_profile.py", "--profile", "quick"], check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
