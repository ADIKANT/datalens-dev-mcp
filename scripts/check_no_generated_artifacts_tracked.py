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
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "repo_size_budget"
FORBIDDEN_PATTERNS = [
    "build/**",
    "dist/**",
    "*.whl",
    "*.tar.gz",
    "artifacts/**/dist/**",
    "artifacts/**/packages/**",
    "artifacts/**/clean_room/**",
    "artifacts/final_quality_program/02_semantic_authoring/**",
    "artifacts/**/mcp_runs/**",
    "artifacts/mcp_runs/**",
    "artifacts/reference_runs/**",
    "artifacts/repo_size_budget/**",
    "artifacts/validation_profiles/**",
    "__pycache__/**",
    "*.pyc",
    ".DS_Store",
]


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


def forbidden_existing(paths: list[str]) -> list[str]:
    offenders: list[str] = []
    for rel in paths:
        if any(fnmatch.fnmatch(rel, pattern) for pattern in FORBIDDEN_PATTERNS) and (ROOT / rel).exists():
            offenders.append(rel)
    return sorted(offenders)


def run_check(*, write: bool = False, output_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    paths = git_ls_files()
    offenders = forbidden_existing(paths)
    report = {
        "ok": not offenders,
        "schema_version": "2026-07-01.generated_artifact_tracking.v1",
        "forbidden_patterns": FORBIDDEN_PATTERNS,
        "offender_count": len(offenders),
        "offenders": offenders[:100],
        "pending_deleted_tracked_matches_ignored": True,
    }
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "generated_artifacts.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check forbidden generated artifacts still present in the working tree.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write", action="store_true", help="Write generated_artifacts.json under the output directory.")
    parser.add_argument("--output-dir", default=str(DEFAULT_ARTIFACT_DIR), help="Report directory used with --write.")
    args = parser.parse_args(argv)
    report = run_check(write=args.write, output_dir=Path(args.output_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
