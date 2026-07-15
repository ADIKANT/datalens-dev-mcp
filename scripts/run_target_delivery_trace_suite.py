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
ARTIFACT_DIR = ROOT / "artifacts" / "target_delivery_trace"


def run_suite() -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.approval_intent import SafeGates, resolve_approval_intent
    from datalens_dev_mcp.pipeline.target_lock import create_target_lock, validate_target_delivery_trace

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    lock = create_target_lock(
        "Fix and publish https://datalens.yandex.cloud/workbooks/wb_1/dashboards/dash_target",
        target_workbook_id="wb_1",
    )
    approval = resolve_approval_intent(
        "Fix and publish the target dashboard",
        target_lock=lock,
        safe_gates=SafeGates(
            writes_enabled=True,
            safe_apply_approved=True,
            fresh_readback_available=True,
            revision_preservation_available=True,
            saved_readback_available=True,
            publish_enabled=True,
        ),
        approval_sources=["codex_tool_approval"],
    )
    good_trace = {
        "target_lock": lock.to_dict(),
        "generated_widget_count": 1,
        "actions": [{"payload": {"dashboardId": "dash_target"}, "target_lock_hash": lock.lock_hash}],
        "saved_readback": {"dashboard": {"entry": {"entryId": "dash_target", "revId": "rev_saved"}}},
        "published_readback": {
            "dashboard": {"entry": {"entryId": "dash_target", "revId": "rev_pub"}},
            "active_widget_count": 1,
        },
    }
    wrong_trace = {
        **good_trace,
        "published_readback": {
            "dashboard": {"entry": {"entryId": "dash_other", "revId": "rev_pub"}},
            "active_widget_count": 0,
        },
    }
    good = validate_target_delivery_trace(good_trace)
    wrong = validate_target_delivery_trace(wrong_trace)
    issues = []
    if not approval.approved:
        issues.append(f"approval intent did not approve normal live task: {approval.to_dict()}")
    if good.get("ok") is not True:
        issues.append(f"target-correct trace failed: {good}")
    if wrong.get("ok") is not False:
        issues.append("wrong-target trace unexpectedly passed")
    summary = {
        "ok": not issues,
        "issues": issues,
        "target_lock": lock.to_dict(),
        "approval_intent": approval.to_dict(),
        "good_trace": good,
        "wrong_trace": wrong,
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run target delivery trace suite.")
    parser.add_argument("--strict", action="store_true", help="Fail on any issue.")
    args = parser.parse_args(argv)
    summary = run_suite()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
