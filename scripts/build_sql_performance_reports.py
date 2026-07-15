#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.pipeline.sql_performance import write_required_reports  # noqa: E402


def main() -> int:
    result = write_required_reports(ROOT)
    print(json.dumps({"ok": result["ok"], "paths": result["paths"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
