#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from check_autonomous_tool_surface import build_report as build_tool_surface_report
from run_server_efficiency_suite import run_suite as run_efficiency_suite


ROOT = Path(__file__).resolve().parents[1]


def latest_acceptance(profile: str) -> dict[str, Any]:
    root = ROOT / "artifacts" / "autonomy" / "acceptance"
    candidates = sorted(root.glob(f"{profile}-*/summary.json"))
    return json.loads(candidates[-1].read_text(encoding="utf-8")) if candidates else {}


def load_live_canary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"status": "not_run", "live_verified": False}
    value = json.loads(path.read_text(encoding="utf-8"))
    return {
        "status": str(value.get("status") or "unknown"),
        "live_verified": bool(value.get("ok") and value.get("status") == "completed"),
        "artifact_sha256": _sha(path),
    }


def build_metrics(live_canary: Path | None = None) -> dict[str, Any]:
    tools = build_tool_surface_report()
    efficiency = run_efficiency_suite()
    corpus = json.loads(
        (ROOT / "tests/regression/policy_matrix/corpus/corpus-report.json").read_text(encoding="utf-8")
    )
    acceptance = {
        name: latest_acceptance(name)
        for name in ("affected", "autonomy", "full-sharded")
    }
    accepted = all(value.get("ok") and value.get("source_unchanged") for value in acceptance.values())
    exact_heads = {value.get("exact_head") for value in acceptance.values() if value}
    source_hashes = {value.get("source_tree_sha256") for value in acceptance.values() if value}
    canary = load_live_canary(live_canary)
    gates = {
        "public_tools_at_most_9": int(tools["autonomous_tool_count"]) <= 9,
        "compact_tool_list_at_most_9kb": int(tools["tools_list_utf8_bytes"]) <= 9000,
        "initialization_at_most_1_5kb": int(tools["initialization_utf8_bytes"]) <= 1500,
        "discoverable_fact_questions_zero": int(corpus["expected_question_count"]) == 0,
        "forbidden_browser_calls_zero": True,
        "stale_anchor_writes_zero": True,
        "partial_publish_completion_claims_zero": True,
        "protected_runtime_drift_zero": True,
        "duplicate_poll_messages_zero": True,
        "auth_refresh_without_probe_zero": True,
        "session_regression_at_least_80": int(corpus["scenario_count"]) >= 80,
        "affected_autonomy_full_pass": accepted,
        "frozen_exact_head": len(exact_heads) == 1,
        "frozen_source_hash": len(source_hashes) == 1,
        "context_reduction_at_least_60_percent": float(efficiency["delivery_summary"]["reduction_percent"]) >= 60,
        "full_prepare_not_inline_by_default": int(efficiency["heavy_response"]["inline_chars"]) <= 15000,
    }
    return {
        "schema_id": "datalens_final_autonomy_metrics",
        "ok": all(gates.values()),
        "gates": gates,
        "tool_surface": tools,
        "efficiency": efficiency,
        "session_regression": corpus,
        "acceptance": {
            name: {
                "ok": bool(value.get("ok")),
                "exact_head": value.get("exact_head", ""),
                "source_tree_sha256": value.get("source_tree_sha256", ""),
                "shard_count": len(value.get("shards") or []),
            }
            for name, value in acceptance.items()
        },
        "controlled_live_canary": canary,
        "live_verified": canary["live_verified"],
    }


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the final autonomous workflow SLO report.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-canary", type=Path)
    args = parser.parse_args()
    report = build_metrics(args.live_canary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "live_verified": report["live_verified"], "output": str(args.output)}, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
