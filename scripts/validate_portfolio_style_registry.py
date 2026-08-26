#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.editor.style_registry import validate_style_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a DataLens portfolio style registry.")
    parser.add_argument("registry")
    args = parser.parse_args()
    payload = json.loads(Path(args.registry).expanduser().read_text(encoding="utf-8"))
    issues = validate_style_registry(payload)
    summary = {
        "ok": not issues,
        "profile_count": len(payload.get("profiles") or []),
        "issue_count": len(issues),
        "issues": issues,
    }
    print(json.dumps(summary, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
