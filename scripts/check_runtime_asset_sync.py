#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = ROOT / "src" / "datalens_dev_mcp" / "assets"
TEXT_RESOURCE_SUFFIXES = {".json", ".jsonl", ".js", ".md"}
RAW_PACKAGED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".html", ".parquet"}
EXCLUDED_SOURCE_FILES = {
    "config/datalens_mcp.local.json",
}
IGNORED_ASSET_FILES = {
    "__init__.py",
    "resource_manifest.json",
}
GENERATED_ASSET_EXCEPTIONS = {
    "validators/editor_runtime_contract.json": "asset-only distilled runtime validator contract",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for rel in _source_files("config"):
        if rel.as_posix() in EXCLUDED_SOURCE_FILES:
            continue
        pairs.append((ROOT / rel, ASSETS_ROOT / rel))
    for rel in _source_files("schemas"):
        pairs.append((ROOT / rel, ASSETS_ROOT / rel))
    for rel in _source_files("templates"):
        pairs.append((ROOT / rel, ASSETS_ROOT / rel))
    return sorted(pairs, key=lambda item: item[0].relative_to(ROOT).as_posix())


def _source_files(root_name: str) -> list[Path]:
    root = ROOT / root_name
    if not root.is_dir():
        return []
    return [
        path.relative_to(ROOT)
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_RESOURCE_SUFFIXES
    ]


def check_sync() -> dict[str, Any]:
    missing_assets: list[str] = []
    hash_mismatches: list[dict[str, str]] = []
    checked_pairs = expected_pairs()
    for source, asset in checked_pairs:
        rel = source.relative_to(ROOT).as_posix()
        if not asset.is_file():
            missing_assets.append(rel)
            continue
        source_hash = sha256_file(source)
        asset_hash = sha256_file(asset)
        if source_hash != asset_hash:
            hash_mismatches.append({"path": rel, "source_sha256": source_hash, "asset_sha256": asset_hash})

    unexpected_assets: list[dict[str, str]] = []
    raw_assets: list[str] = []
    for asset in sorted(path for path in ASSETS_ROOT.rglob("*") if path.is_file()):
        rel = asset.relative_to(ASSETS_ROOT).as_posix()
        if "__pycache__" in asset.parts or Path(rel).name in IGNORED_ASSET_FILES:
            continue
        if asset.suffix.lower() in RAW_PACKAGED_SUFFIXES or "/raw/" in f"/{rel}/":
            raw_assets.append(rel)
        if rel in GENERATED_ASSET_EXCEPTIONS:
            continue
        source = _source_for_asset(rel)
        if source is not None and not source.is_file():
            unexpected_assets.append({"asset": rel, "expected_source": source.relative_to(ROOT).as_posix()})

    return {
        "ok": not missing_assets and not hash_mismatches and not unexpected_assets and not raw_assets,
        "checked_pair_count": len(checked_pairs),
        "missing_assets": missing_assets,
        "hash_mismatches": hash_mismatches,
        "unexpected_assets": unexpected_assets,
        "generated_asset_exceptions": GENERATED_ASSET_EXCEPTIONS,
        "raw_assets": raw_assets,
    }


def _source_for_asset(asset_rel: str) -> Path | None:
    if asset_rel.startswith("schemas/datalens-knowledge/"):
        return None
    first = asset_rel.split("/", 1)[0]
    if first in {"config", "schemas", "templates"}:
        source = ROOT / asset_rel
        if source.as_posix().endswith("config/datalens_mcp.local.json"):
            return None
        return source
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check top-level runtime resources against packaged assets.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()
    report = check_sync()
    if args.json or not report["ok"]:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps({"ok": True, "checked_pair_count": report["checked_pair_count"]}, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
