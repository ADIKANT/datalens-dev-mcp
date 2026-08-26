#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.server import AUTONOMOUS_TOOL_NAMES, LEGACY_TOOL_NAMES, JsonRpcServer, list_tools


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts" / "autonomy" / "tool_surface_budget.json"


def build_report() -> dict[str, object]:
    autonomous = list_tools("autonomous-v2")
    legacy = list_tools("legacy-v1")
    expert = list_tools("expert")
    tools_payload = json.dumps({"tools": autonomous}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with patch.dict(os.environ, {}, clear=True):
        initialized = JsonRpcServer(project_root=str(ROOT)).handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
    instructions = str(initialized["result"]["instructions"]).encode("utf-8")
    checks = {
        "autonomous_tool_count": len(autonomous) == 8 and len(autonomous) <= 9,
        "tools_list_bytes": len(tools_payload) <= 9_000,
        "initialization_bytes": len(instructions) <= 1_500,
        "legacy_tool_count": len(legacy) == 39,
        "no_low_level_duplicates": not bool(AUTONOMOUS_TOOL_NAMES & LEGACY_TOOL_NAMES),
    }
    return {
        "schema_id": "datalens_autonomous_tool_surface_budget",
        "ok": all(checks.values()),
        "surface": "autonomous-v2",
        "autonomous_tool_count": len(autonomous),
        "autonomous_tools": sorted(AUTONOMOUS_TOOL_NAMES),
        "tools_list_utf8_bytes": len(tools_payload),
        "initialization_utf8_bytes": len(instructions),
        "legacy_tool_count": len(legacy),
        "expert_tool_count": len(expert),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the compact autonomous MCP tool surface and compatibility budget.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    report = build_report()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**report, "artifact_path": str(out)}, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
