#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datalens_dev_mcp.server import AUTONOMOUS_TOOL_NAMES, LEGACY_TOOL_NAMES, JsonRpcServer, list_tools


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts" / "autonomy" / "tool_surface_budget.json"


def _utf8_bytes(value: object, *, pretty: bool = False) -> int:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=pretty,
    )
    return len(rendered.encode("utf-8"))


def _schema_branch_count(value: object) -> int:
    if isinstance(value, dict):
        count = sum(
            len(value.get(keyword) or [])
            for keyword in ("oneOf", "anyOf", "allOf")
            if isinstance(value.get(keyword), list)
        )
        return count + sum(_schema_branch_count(child) for child in value.values())
    if isinstance(value, list):
        return sum(_schema_branch_count(child) for child in value)
    return 0


def _description_metrics(tools: list[dict[str, Any]]) -> tuple[int, int]:
    descriptions: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "description" and isinstance(child, str):
                    descriptions.append(child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(tools)
    seen: set[str] = set()
    duplicate_bytes = 0
    for description in descriptions:
        if description in seen:
            duplicate_bytes += len(description.encode("utf-8"))
        else:
            seen.add(description)
    return len(descriptions), duplicate_bytes


def _normalize_interaction_metrics(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {
            "status": "not_provided",
            "public_call_count": None,
            "invalid_call_count": None,
            "invalid_call_rate": None,
            "extra_contract_reads": None,
            "evidence_refs": [],
        }
    public_call_count = max(0, int(value.get("public_call_count") or 0))
    invalid_call_count = max(0, int(value.get("invalid_call_count") or 0))
    extra_contract_reads = max(0, int(value.get("extra_contract_reads") or 0))
    if invalid_call_count > public_call_count:
        raise ValueError("invalid_call_count cannot exceed public_call_count")
    return {
        "status": "measured",
        "public_call_count": public_call_count,
        "invalid_call_count": invalid_call_count,
        "invalid_call_rate": round(invalid_call_count / public_call_count, 6) if public_call_count else 0.0,
        "extra_contract_reads": extra_contract_reads,
        "evidence_refs": [str(item) for item in value.get("evidence_refs") or []],
    }


def build_report(interaction_metrics: dict[str, Any] | None = None) -> dict[str, object]:
    autonomous = list_tools("autonomous-v2")
    legacy = list_tools("legacy-v1")
    expert = list_tools("expert")
    raw_tools_list_bytes = _utf8_bytes({"tools": autonomous})
    client_rendered_bytes = _utf8_bytes({"tools": autonomous}, pretty=True)
    schema_bytes = {
        str(tool["name"]): _utf8_bytes(tool.get("inputSchema") or {})
        for tool in autonomous
    }
    largest_tool_name = max(schema_bytes, key=schema_bytes.__getitem__)
    description_count, duplicate_description_bytes = _description_metrics(autonomous)
    interaction = _normalize_interaction_metrics(interaction_metrics)
    with patch.dict(os.environ, {}, clear=True):
        initialized = JsonRpcServer(project_root=str(ROOT)).handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
    instructions = str(initialized["result"]["instructions"]).encode("utf-8")
    checks = {
        "autonomous_tool_count": len(autonomous) == 8 and len(autonomous) <= 9,
        "tools_list_bytes": raw_tools_list_bytes <= 9_000,
        "initialization_bytes": len(instructions) <= 1_500,
        "legacy_tool_count": len(legacy) == 39,
        "no_low_level_duplicates": not bool(AUTONOMOUS_TOOL_NAMES & LEGACY_TOOL_NAMES),
        "strict_object_validation": all(
            (tool.get("inputSchema") or {}).get("additionalProperties") is False
            for tool in autonomous
        ),
    }
    if interaction["status"] == "measured":
        checks["invalid_call_rate_zero"] = interaction["invalid_call_rate"] == 0.0
        checks["extra_contract_reads_zero"] = interaction["extra_contract_reads"] == 0
    return {
        "schema_id": "datalens_autonomous_tool_surface_budget",
        "ok": all(checks.values()),
        "surface": "autonomous-v2",
        "tool_count": len(autonomous),
        "autonomous_tool_count": len(autonomous),
        "autonomous_tools": sorted(AUTONOMOUS_TOOL_NAMES),
        "raw_tools_list_bytes": raw_tools_list_bytes,
        "tools_list_utf8_bytes": raw_tools_list_bytes,
        "client_rendered_bytes": client_rendered_bytes,
        "estimated_tokens": math.ceil(client_rendered_bytes / 4),
        "initialization_bytes": len(instructions),
        "initialization_utf8_bytes": len(instructions),
        "schema_branch_count": _schema_branch_count([tool.get("inputSchema") or {} for tool in autonomous]),
        "largest_tool_schema": {
            "name": largest_tool_name,
            "utf8_bytes": schema_bytes[largest_tool_name],
        },
        "description_count": description_count,
        "duplicate_description_bytes": duplicate_description_bytes,
        "invalid_call_rate": interaction["invalid_call_rate"],
        "extra_contract_reads": interaction["extra_contract_reads"],
        "interaction_measurement": interaction,
        "legacy_tool_count": len(legacy),
        "expert_tool_count": len(expert),
        "metric_definitions": {
            "raw_tools_list_bytes": "Compact UTF-8 JSON bytes of the tools/list tools payload.",
            "client_rendered_bytes": "Pretty UTF-8 JSON bytes for the same client-visible tools payload.",
            "estimated_tokens": "Ceiling of client_rendered_bytes divided by four.",
            "schema_branch_count": "Total oneOf/anyOf/allOf alternatives across public input schemas.",
            "duplicate_description_bytes": "UTF-8 bytes of exact repeated description values after their first occurrence.",
            "invalid_call_rate": "Observed invalid public calls divided by observed public calls from the supplied interaction metrics.",
            "extra_contract_reads": "Observed client reads of hidden or additional contracts beyond the supplied public tools/list schema.",
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the compact autonomous MCP tool surface and compatibility budget.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--interaction-metrics",
        type=Path,
        help="Optional JSON measurement with public_call_count, invalid_call_count, extra_contract_reads, and evidence_refs.",
    )
    args = parser.parse_args()
    interaction_metrics = None
    if args.interaction_metrics is not None:
        interaction_metrics = json.loads(args.interaction_metrics.read_text(encoding="utf-8"))
        if not isinstance(interaction_metrics, dict):
            raise ValueError("interaction metrics must be a JSON object")
    report = build_report(interaction_metrics)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**report, "artifact_path": str(out)}, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
