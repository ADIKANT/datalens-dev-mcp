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
ARTIFACT_DIR = ROOT / "artifacts" / "dashboard_object_granularity"


def run_suite() -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.dashboard_object_granularity import validate_dashboard_object_granularity
    from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract
    from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    separate_graph = {
        "expected_visual_count": 5,
        "objects": [
            {"object_id": "sel_period", "object_type": "control_node", "role": "selector"},
            {"object_id": "kpi_orders", "object_type": "indicator_node", "role": "kpi"},
            {"object_id": "kpi_quality", "object_type": "indicator_node", "role": "kpi"},
            {"object_id": "trend", "object_type": "advanced_editor_chart", "visual_count": 1, "role": "chart"},
            {"object_id": "distribution", "object_type": "advanced_editor_chart", "visual_count": 1, "role": "chart"},
            {"object_id": "dq_table", "object_type": "table_node", "role": "table"},
            {"object_id": "method", "object_type": "markdown_node", "role": "methodology"},
        ],
        "tabs": [{"id": "main", "items": [{"object_id": "kpi_orders"}, {"object_id": "trend"}, {"object_id": "dq_table"}]}],
    }
    composite_graph = {
        "expected_visual_count": 5,
        "objects": [
            {
                "object_id": "style_quality_composite",
                "object_type": "advanced_editor_chart",
                "visual_count": 5,
                "native_title": "Style Quality",
                "prepare": "<h1>Style Quality</h1><h2>Data Quality</h2><div class='kpi-card card-grid'></div><table></table>",
            }
        ],
    }
    kpi_good = {
        "expected_kpi_count": 2,
        "kpis": [
            {
                "object_type": "indicator_node",
                "formula": "count_orders",
                "unit": "orders",
                "grain": "day",
                "comparator_policy": "explicit_none",
                "native_title": "Orders",
                "native_hint": "Orders in selected period",
            },
            {
                "object_type": "indicator_node",
                "formula": "dq_pass_rate",
                "unit": "%",
                "grain": "snapshot",
                "comparator_policy": "threshold",
                "native_title": "DQ pass rate",
                "native_hint": "Share of checks passed",
            },
        ],
    }
    source_good = {
        "source_file_name": "style_quality.csv",
        "available_datasets": [{"id": "ds_style_quality", "name": "style_quality.csv"}],
        "source_mode": "dataset_backed",
    }
    source_bad = {"source_file_name": "style_quality.csv", "user_uploaded_file": True, "source_mode": "embedded"}
    good = validate_dashboard_object_granularity(separate_graph)
    bad = validate_dashboard_object_granularity(composite_graph)
    kpi = validate_kpi_indicator_contract(kpi_good)
    source_ok = validate_source_route_decision(source_good)
    source_block = validate_source_route_decision(source_bad)
    issues = []
    if not good.ok or good.visual_object_count < good.expected_visual_count:
        issues.append(f"separate object graph failed: {good.to_dict()}")
    if bad.ok:
        issues.append("composite Advanced Editor dashboard unexpectedly passed")
    if not kpi.ok:
        issues.append(f"KPI indicator contract failed good fixture: {kpi.to_dict()}")
    if not source_ok["ok"]:
        issues.append(f"dataset-backed source route failed: {source_ok}")
    if source_block["ok"]:
        issues.append("embedded source fallback without explicit static mode unexpectedly passed")
    summary = {
        "ok": not issues,
        "issues": issues,
        "separate_graph": good.to_dict(),
        "composite_graph": bad.to_dict(),
        "kpi_indicator": kpi.to_dict(),
        "source_route_dataset": source_ok,
        "source_route_embedded_block": source_block,
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run dashboard object granularity contract suite.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    summary = run_suite()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
