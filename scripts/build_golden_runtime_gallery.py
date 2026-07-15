#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.pipeline.golden_runtime_gallery import (  # noqa: E402
    build_golden_contracts,
    compare_generated_to_golden,
)


SOURCE_INVENTORY = ROOT / "config" / "golden_runtime_gallery_inventory.json"
SOURCE_CONTRACTS = ROOT / "config" / "golden_runtime_gallery_contracts.json"
ASSET_CONFIG = ROOT / "src" / "datalens_dev_mcp" / "assets" / "config"
ASSET_INVENTORY = ASSET_CONFIG / "golden_runtime_gallery_inventory.json"
ASSET_CONTRACTS = ASSET_CONFIG / "golden_runtime_gallery_contracts.json"
EXAMPLE_DIR = ROOT / "examples" / "golden_runtime_gallery"
DOC_REPORT = ROOT / "docs" / "testing" / "golden_runtime_gallery.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or check the DataLens golden runtime gallery contracts.")
    parser.add_argument("--write", action="store_true", help="Write source, packaged, examples, and docs contracts.")
    parser.add_argument("--check", action="store_true", help="Compare regenerated contracts with the checked-in golden file.")
    parser.add_argument(
        "--browser-unavailable-reason",
        default="No rendered DataLens URL, browser authentication, or browser capture artifact is configured for this static run.",
    )
    args = parser.parse_args()

    inventory = _read_json(SOURCE_INVENTORY)
    generated = build_golden_contracts(inventory=inventory, browser_unavailable_reason=args.browser_unavailable_reason)
    if args.write:
        _write_json(SOURCE_INVENTORY, inventory)
        _write_json(ASSET_INVENTORY, inventory)
        _write_json(SOURCE_CONTRACTS, generated)
        _write_json(ASSET_CONTRACTS, generated)
        _write_json(EXAMPLE_DIR / "golden_runtime_gallery_contracts.json", generated)
        (EXAMPLE_DIR / "README.md").write_text(_examples_readme(generated), encoding="utf-8")
        DOC_REPORT.write_text(_report_markdown(generated), encoding="utf-8")

    if args.check:
        expected = _read_json(SOURCE_CONTRACTS)
        comparison = compare_generated_to_golden(inventory=inventory, golden=expected)
        if not comparison["ok"]:
            print(json.dumps(comparison, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 1
        if ASSET_INVENTORY.is_file() and _canonical_json(_read_json(ASSET_INVENTORY)) != _canonical_json(inventory):
            print("packaged golden runtime gallery inventory is stale", file=sys.stderr)
            return 1
        if ASSET_CONTRACTS.is_file() and _canonical_json(_read_json(ASSET_CONTRACTS)) != _canonical_json(expected):
            print("packaged golden runtime gallery contracts are stale", file=sys.stderr)
            return 1

    print(
        json.dumps(
            {
                "ok": True,
                "supported_family_count": generated["summary"]["supported_family_count"],
                "families_by_route": generated["summary"]["families_by_route"],
                "browser_rendered_available_count": generated["summary"]["browser_rendered_available_count"],
                "contracts_path": str(SOURCE_CONTRACTS),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _examples_readme(gallery: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Golden Runtime Gallery",
            "",
            "This directory contains generated static contracts for the DataLens route-family gallery.",
            "The source of truth is `config/golden_runtime_gallery_inventory.json`; regenerate with:",
            "",
            "```bash",
            "python3 scripts/build_golden_runtime_gallery.py --write",
            "```",
            "",
            "Live saved, published, and browser proof are intentionally marked unavailable unless a future run supplies",
            "a disposable workbook, an implementation request, and browser evidence.",
            "",
            f"- Supported families: `{gallery['summary']['supported_family_count']}`",
            f"- Families by route: `{json.dumps(gallery['summary']['families_by_route'], sort_keys=True)}`",
            "",
        ]
    )


def _report_markdown(gallery: dict[str, Any]) -> str:
    lines = [
        "# Golden Runtime Gallery",
        "",
        "The MCP-supported chart creation routes are closed and represented by generated golden contracts.",
        "The gallery is a regression fixture and runtime-proof ledger, not a reusable business dashboard.",
        "",
        "## Route Inventory",
        "",
        "| Class | Routes |",
        "| --- | --- |",
    ]
    route_inventory = gallery["route_inventory"]
    for class_name in ("supported", "reference_only", "unsupported", "banned"):
        routes = ", ".join(f"`{item['route']}`" for item in route_inventory[class_name])
        lines.append(f"| {class_name} | {routes} |")
    lines.extend(
        [
            "",
            "## Contract Summary",
            "",
            f"- Supported family contracts: `{gallery['summary']['supported_family_count']}`",
            f"- Families by route: `{json.dumps(gallery['summary']['families_by_route'], sort_keys=True)}`",
            f"- Saved readback available: `{gallery['summary']['saved_readback_available_count']}`",
            f"- Published readback available: `{gallery['summary']['published_readback_available_count']}`",
            f"- Browser render proof available: `{gallery['summary']['browser_rendered_available_count']}`",
            f"- Browser render proof unavailable: `{gallery['summary']['browser_rendered_unavailable_count']}`",
            "",
            "Saved readback, published readback, and browser screenshots remain `unavailable` in the checked-in",
            "static contracts because no disposable workbook, implementation target, rendered URL, or authenticated",
            "browser evidence was supplied for this static release snapshot.",
            "",
            "## Contract Files",
            "",
            "- `config/golden_runtime_gallery_inventory.json`",
            "- `config/golden_runtime_gallery_contracts.json`",
            "- `examples/golden_runtime_gallery/golden_runtime_gallery_contracts.json`",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
