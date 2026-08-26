#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.editor.style_scanner import public_safe_registry, scan_portfolio_style_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded read-only DataLens portfolio style registry.")
    parser.add_argument("--portfolio-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-profiles", type=int, default=1024)
    parser.add_argument("--public-safe", action="store_true")
    args = parser.parse_args()
    registry = scan_portfolio_style_registry(args.portfolio_root, max_profiles=args.max_profiles)
    if args.public_safe:
        registry = public_safe_registry(registry)
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = not bool(registry.get("truncated"))
    summary = {
        "ok": ok,
        "profile_count": registry["profile_count"],
        "truncated": registry.get("truncated", False),
        "source_kind": registry["source_kind"],
        "output": str(output),
    }
    print(json.dumps(summary))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
