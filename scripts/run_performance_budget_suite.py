#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
ARTIFACT_DIR = ROOT / "artifacts" / "performance_budget"


def run_suite() -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.performance_budget import assess_performance_budget

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    heavy_sql = (
        "WITH base AS (SELECT * FROM events LEFT JOIN users ON events.user_id = users.id) "
        "SELECT segment, count(*) FROM base LEFT JOIN teams ON base.team_id = teams.id GROUP BY segment"
    )
    good = assess_performance_budget(
        {
            "tabs": [{"id": "main", "observed_seconds": 3, "widgets": [{"id": "w1"}]}],
            "sources": [{"query": "SELECT segment, count(*) FROM events GROUP BY segment LIMIT 100"}],
        }
    )
    slow = assess_performance_budget({"tabs": [{"id": "workflow", "observed_seconds": 20, "widgets": [{"id": "w1"}]}]})
    duplicate = assess_performance_budget({"sources": [{"query": heavy_sql}, {"query": heavy_sql}]})
    issues = []
    if not good.publish_allowed:
        issues.append(f"good performance fixture failed: {good.to_dict()}")
    if slow.publish_allowed:
        issues.append("20-second tab did not block publish")
    if duplicate.publish_allowed:
        issues.append("duplicated heavy source SQL did not block publish")
    summary = {
        "ok": not issues,
        "issues": issues,
        "good": good.to_dict(),
        "slow": slow.to_dict(),
        "duplicate_heavy_source": duplicate.to_dict(),
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run performance budget suite.")
    parser.add_argument("--strict", action="store_true", help="Fail on any issue.")
    args = parser.parse_args(argv)
    summary = run_suite()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
