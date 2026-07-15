#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SAFE_FILE_NAMES = {".DS_Store", "Pasted text.txt"}
SAFE_DIR_NAMES = {"__MACOSX", "__pycache__", ".pytest_cache", ".ruff_cache"}
SAFE_SUFFIXES = {".pyc", ".pyo"}
SKIP_DIR_NAMES = {".git", ".venv", "venv", "dist", "build", ".mypy_cache"}


def _is_skipped(path: Path, root: Path) -> bool:
    if path == root:
        return False
    return any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts)


def clean_runtime_artifacts(root: Path) -> list[Path]:
    root = root.resolve()
    removed: list[Path] = []

    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if _is_skipped(path, root):
            continue
        if path.is_dir() and path.name in SAFE_DIR_NAMES:
            shutil.rmtree(path)
            removed.append(path)
            continue
        if path.is_file() and (path.name in SAFE_FILE_NAMES or path.suffix in SAFE_SUFFIXES):
            path.unlink()
            removed.append(path)

    return sorted(removed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove safe local runtime/cache artifacts.")
    parser.add_argument("--root", default=".", help="Repository root to clean.")
    args = parser.parse_args()

    root = Path(args.root)
    removed = clean_runtime_artifacts(root)
    for path in removed:
        print(path.relative_to(root.resolve()))
    print(f"clean_local_runtime_artifacts: removed {len(removed)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
