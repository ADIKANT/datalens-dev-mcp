#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "repo_size_budget"
BUDGETS = {
    "tracked_worktree_existing_mb": 60.0,
    "artifacts_existing_tracked_mb": 16.0,
    "runtime_assets_mb": 20.0,
}
WORKSPACE_SKIP_DIRS = {".git", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
LARGE_RUNTIME_ARTIFACT_BYTES = 1024 * 1024


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git ls-files failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def size_bytes(paths: list[str]) -> int:
    total = 0
    for rel in paths:
        path = ROOT / rel
        if path.is_file():
            total += path.stat().st_size
    return total


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 3)


def iter_workspace_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        try:
            rel_parts = path.relative_to(ROOT).parts
        except ValueError:
            continue
        if any(part in WORKSPACE_SKIP_DIRS for part in rel_parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def directory_size_rows(files: list[Path], *, limit: int = 15) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for path in files:
        rel = path.relative_to(ROOT)
        key = rel.parts[0] if rel.parts else "."
        totals[key] = totals.get(key, 0) + path.stat().st_size
    return [
        {"path": key, "bytes": value, "mb": mb(value)}
        for key, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def extension_size_rows(files: list[Path], *, limit: int = 20) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for path in files:
        suffix = "".join(path.suffixes[-2:]) if path.name.endswith(".tar.gz") else path.suffix.lower()
        key = suffix or "[no_ext]"
        totals[key] = totals.get(key, 0) + path.stat().st_size
    return [
        {"extension": key, "bytes": value, "mb": mb(value)}
        for key, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def largest_file_rows(files: list[Path], *, limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True)[:limit]:
        size = path.stat().st_size
        rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": size, "mb": mb(size)})
    return rows


def directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def category_rows(files: list[Path]) -> dict[str, dict[str, Any]]:
    categories = {
        "build_dist": [],
        "sqlite_index_artifacts": [],
        "release_bundles": [],
        "duplicated_docs_assets": [],
        "large_runtime_artifacts": [],
    }
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        parts = set(path.relative_to(ROOT).parts)
        suffixes = path.suffixes
        size = path.stat().st_size
        if {"build", "dist"} & parts or fnmatch.fnmatch(rel, "artifacts/**/dist/**"):
            categories["build_dist"].append(path)
        if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"} or path.name.endswith(".index"):
            categories["sqlite_index_artifacts"].append(path)
        if (
            path.name.endswith((".whl", ".tar.gz", ".zip"))
            or "release_qualification" in parts
            or "final_quality_program" in parts
            or "clean_room" in parts
            or "packages" in parts
        ):
            categories["release_bundles"].append(path)
        if rel.startswith("src/datalens_dev_mcp/assets/") and any(
            rel.startswith(f"src/datalens_dev_mcp/assets/{prefix}/")
            for prefix in ("config", "docs", "schemas", "templates")
        ):
            categories["duplicated_docs_assets"].append(path)
        if rel.startswith("artifacts/") and (
            size >= LARGE_RUNTIME_ARTIFACT_BYTES
            or any(part in parts for part in ("mcp_runs", "sql_performance", "datalens_knowledge"))
        ):
            categories["large_runtime_artifacts"].append(path)

    rows: dict[str, dict[str, Any]] = {}
    for name, paths in categories.items():
        total = sum(path.stat().st_size for path in paths)
        rows[name] = {
            "file_count": len(paths),
            "bytes": total,
            "mb": mb(total),
            "examples": [path.relative_to(ROOT).as_posix() for path in sorted(paths)[:20]],
        }
    git_bytes = directory_bytes(ROOT / ".git")
    rows["git_dir"] = {
        "file_count": sum(1 for path in (ROOT / ".git").rglob("*") if path.is_file()) if (ROOT / ".git").is_dir() else 0,
        "bytes": git_bytes,
        "mb": mb(git_bytes),
        "examples": [".git"],
    }
    return rows


def run_check(*, write: bool = False, output_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    from scripts.check_no_generated_artifacts_tracked import run_check as generated_artifact_check

    tracked = git_ls_files()
    existing_tracked = [rel for rel in tracked if (ROOT / rel).is_file()]
    artifacts = [rel for rel in existing_tracked if rel.startswith("artifacts/")]
    runtime_assets = [rel for rel in existing_tracked if rel.startswith("src/datalens_dev_mcp/assets/")]
    generated = generated_artifact_check(write=write, output_dir=output_dir)
    workspace_files = iter_workspace_files()
    sizes = {
        "tracked_worktree_existing_mb": round(size_bytes(existing_tracked) / 1024 / 1024, 3),
        "artifacts_existing_tracked_mb": round(size_bytes(artifacts) / 1024 / 1024, 3),
        "runtime_assets_mb": round(size_bytes(runtime_assets) / 1024 / 1024, 3),
    }
    budget_failures = [
        {"budget": name, "actual_mb": actual, "limit_mb": BUDGETS[name]}
        for name, actual in sizes.items()
        if actual > BUDGETS[name]
    ]
    report = {
        "ok": not budget_failures and bool(generated.get("ok")),
        "schema_version": "2026-07-01.repo_size_budget.v1",
        "budgets_mb": BUDGETS,
        "sizes_mb": sizes,
        "existing_tracked_file_count": len(existing_tracked),
        "pending_deleted_tracked_file_count": len(tracked) - len(existing_tracked),
        "workspace_file_count": len(workspace_files),
        "top_directories": directory_size_rows(workspace_files),
        "top_extensions": extension_size_rows(workspace_files),
        "largest_files": largest_file_rows(workspace_files),
        "categories": category_rows(workspace_files),
        "generated_artifact_check": generated,
        "budget_failures": budget_failures,
        "artifact_policy": (
            "compact reports/manifests/hashes only; generated packages, clean rooms, "
            "final-quality evidence, repo-size reports, and mcp_runs stay ignored or externalized"
        ),
    }
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check repository size and generated-artifact budget.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write", action="store_true", help="Write summary.json under the output directory.")
    parser.add_argument("--output-dir", default=str(DEFAULT_ARTIFACT_DIR), help="Report directory used with --write.")
    args = parser.parse_args(argv)
    report = run_check(write=args.write, output_dir=Path(args.output_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
