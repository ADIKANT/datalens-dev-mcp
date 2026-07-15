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
ARTIFACT_DIR = ROOT / "artifacts" / "table_render_contract"


def run_sweep() -> dict[str, Any]:
    from datalens_dev_mcp.editor.bundle import generate_editor_bundle
    from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract
    from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v3

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    table_bundle = generate_editor_bundle(
        widget_id="table_contract",
        route="editor_table",
        title="Table Contract",
        family="table_node",
        columns=["name", "value"],
    )
    good_payload = {
        "route": "editor_table",
        "columns": [
            {"id": "name", "title": "Name", "role": "dimension", "type": "text", "format": "text"},
            {
                "id": "value",
                "title": "Value",
                "role": "measure",
                "type": "bar",
                "format": "number",
                "min": 0,
                "max": 100,
                "barColor": "#2f80ed",
                "showLabel": True,
                "label_position": "outside",
            },
        ],
        "rows": [{"cells": [{"value": "A"}, {"value": 42}]}],
        "source": {"row_count": 1},
        "sorting": {"by": "value", "direction": "desc"},
        "empty_state_policy": {"message": "Нет данных по выбранным фильтрам"},
    }
    bad_payload = {
        "route": "editor_table",
        "columns": [],
        "rows": [],
        "source": {"row_count": 3},
    }
    good = validate_native_table_contract(good_payload)
    bad = validate_native_table_contract(bad_payload)
    route = select_route_v3("Сделай таблицу с bars", semantic_output="table")
    issues = []
    if not good.ok:
        issues.append(f"good native table fixture failed: {[item.to_dict() for item in good.findings]}")
    if bad.ok:
        issues.append("non-empty source skeleton table unexpectedly passed")
    if route.selected_route != "editor_table":
        issues.append(f"table route selection mismatch: {route.to_dict()}")
    prepare = str((table_bundle.get("tabs") or {}).get("prepare.js") or "")
    if "type: 'bar'" not in prepare and '"type": "bar"' not in prepare:
        issues.append("generated table bundle does not include native bar contract")
    summary = {
        "ok": not issues,
        "issues": issues,
        "generated_bundle_route": table_bundle.get("route"),
        "good_validation": good.to_dict(),
        "bad_validation": bad.to_dict(),
        "route_selection": route.to_dict(),
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run native table render contract sweep.")
    parser.add_argument("--strict", action="store_true", help="Fail on any issue.")
    args = parser.parse_args(argv)
    summary = run_sweep()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
