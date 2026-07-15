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
ARTIFACT_DIR = ROOT / "artifacts" / "selector_layout_contract"


def run_suite() -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.selector_layout_contract import (
        SelectorLayoutContract,
        validate_selector_layout_contract,
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    contract = SelectorLayoutContract()
    selectors = [
        {
            "id": "period",
            "object_type": "control_node",
            "kind": "date_range",
            "label": "Reporting period date range",
            "target_widget_ids": ["trend", "table"],
            "target_field_or_parameter": "paid_dttm",
            "default_value_policy": "last_30_days",
            "affected_tabs": ["main"],
        },
        {
            "id": "sprint",
            "object_type": "control_node",
            "kind": "single_select",
            "label": "Sprint selection control",
            "target_widget_ids": ["trend", "table"],
            "target_field_or_parameter": "sprint",
            "default_value_policy": "all",
            "affected_tabs": ["main"],
        },
        {
            "id": "team",
            "object_type": "control_node",
            "kind": "multi_select",
            "label": "Delivery team multi select",
            "target_widget_ids": ["trend", "table"],
            "target_field_or_parameter": "team",
            "default_value_policy": "all",
            "affected_tabs": ["main"],
        },
        {
            "id": "rcp_category",
            "object_type": "control_node",
            "kind": "search_select",
            "label": "RCP category with long readable label",
            "target_widget_ids": ["trend", "table"],
            "target_field_or_parameter": "rcp_category",
            "default_value_policy": "all",
            "affected_tabs": ["main"],
        },
        {
            "id": "grain",
            "object_type": "control_node",
            "kind": "granularity",
            "label": "Reporting granularity",
            "target_widget_ids": ["trend", "table"],
            "target_field_or_parameter": "grain",
            "default_value_policy": "week",
            "affected_tabs": ["main"],
        },
    ]
    rows = contract.compute_rows(selectors)
    good_payload = {
        "selector_rows": rows,
        "objects": [{"object_id": "trend"}, {"object_id": "table"}],
        "fields": ["paid_dttm", "sprint", "team", "rcp_category", "grain"],
    }
    bad_payload = {
        "selector_rows": [
            [
                {
                    "id": "bad_selector",
                    "object_type": "advanced_editor_chart",
                    "kind": "single_select",
                    "label": "Fake selector",
                    "width": "104%",
                    "target_widget_ids": ["missing"],
                    "target_field_or_parameter": "missing_field",
                    "default_value_policy": "all",
                }
            ]
        ],
        "objects": [{"object_id": "trend"}],
        "fields": ["team"],
    }
    good = validate_selector_layout_contract(good_payload)
    bad = validate_selector_layout_contract(bad_payload)
    issues = []
    if not good.ok:
        issues.append(f"selector layout good fixture failed: {good.to_dict()}")
    if not all(width <= 96.0 for width in good.row_widths_pct):
        issues.append(f"selector row width exceeds 96%: {good.row_widths_pct}")
    if len(rows) < 2:
        issues.append("long selector labels did not split to a second row")
    if bad.ok:
        issues.append("bad selector layout/wiring unexpectedly passed")
    summary = {
        "ok": not issues,
        "issues": issues,
        "computed_rows": rows,
        "good": good.to_dict(),
        "bad": bad.to_dict(),
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run selector layout contract suite.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    summary = run_suite()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
