#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.runtime_resources import resource_manifest  # noqa: E402


MANIFEST_PATH = ROOT / "src" / "datalens_dev_mcp" / "assets" / "resource_manifest.json"
SCHEMA_VERSION = "2026-06-25.runtime_resource_manifest.v1"


def build_manifest() -> dict[str, object]:
    rows = resource_manifest()
    return {
        "schema_version": SCHEMA_VERSION,
        "resource_count": len(rows),
        "resources": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or check the packaged runtime resource manifest.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_manifest()
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.check:
        current = MANIFEST_PATH.read_text(encoding="utf-8") if MANIFEST_PATH.is_file() else ""
        if current != rendered:
            print("runtime resource manifest is stale", file=sys.stderr)
            return 1
    if args.write:
        MANIFEST_PATH.write_text(rendered, encoding="utf-8")
    print(json.dumps({"ok": True, "resource_count": payload["resource_count"], "path": str(MANIFEST_PATH)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
