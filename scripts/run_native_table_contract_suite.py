#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
ARTIFACT_DIR = ROOT / "artifacts" / "native_table_contract"


def run_suite() -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract
    from scripts.run_table_render_contract_sweep import run_sweep

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    sweep = run_sweep()
    html_table = validate_native_table_contract(
        {
            "route": "editor_advanced",
            "columns": [{"id": "name", "title": "Name", "type": "text"}],
            "rows": [{"cells": [{"value": "A"}]}],
            "html": "<table><tr><td>A</td></tr></table>",
        },
        source_rows=1,
    )
    empty_source = validate_native_table_contract(
        {
            "route": "table_node",
            "columns": [{"id": "name", "title": "Name", "type": "text"}],
            "rows": [],
            "source": {"row_count": 0},
            "empty_state_policy": {"message": "No rows for selected filters"},
        },
        source_rows=0,
    )
    issues = []
    if not sweep.get("ok"):
        issues.append(f"table render sweep failed: {sweep.get('issues')}")
    if html_table.ok:
        issues.append("HTML table fixture unexpectedly passed native table contract")
    if not empty_source.ok:
        issues.append(f"zero-row explicit empty state failed: {empty_source.to_dict()}")
    summary = {
        "ok": not issues,
        "issues": issues,
        "table_render_sweep": sweep,
        "html_table_block": html_table.to_dict(),
        "zero_row_empty_state": empty_source.to_dict(),
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run native table contract suite.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    summary = run_suite()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
