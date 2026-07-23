#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import zipfile


ROOT_EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "htmlcov",
    "wheelhouse",
    "__MACOSX",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
}
EXCLUDED_FILE_NAMES = {".DS_Store", ".coverage"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".whl"}
EXCLUDED_DOUBLE_SUFFIXES = {".tar.gz"}
LOCAL_SECRET_FILES = {
    ".env",
    ".env.local",
    ".datalens.env",
    "datalens_token.env",
    "config/datalens_mcp.local.json",
    "src/datalens_dev_mcp/assets/config/datalens_mcp.local.json",
}
LOCAL_SECRET_SUFFIXES = {".local.json", ".local.env"}
EXCLUDED_PREFIXES = {
    ".external",
    ".metadata-fetch",
    "artifacts",
    "datalens_mapping",
    "docs/knowledge_base",
    "docs/reports",
    "dry-runs",
    "live-exports",
    "materials",
    "memory-bank",
    "raw",
    "shareable",
    "sync-local",
}
EXCLUDED_ROOT_FILES = {"RUN_STATE.md", "run_state.md"}


def should_exclude(path: Path, root: Path, *, output_path: Path | None = None) -> bool:
    if output_path is not None and path.resolve() == output_path.resolve():
        return True
    rel = path.relative_to(root).as_posix()
    parts = path.relative_to(root).parts
    if any(part in ROOT_EXCLUDED_DIR_NAMES for part in parts):
        return True
    if rel in LOCAL_SECRET_FILES:
        return True
    if rel in EXCLUDED_ROOT_FILES:
        return True
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if any(rel.endswith(suffix) for suffix in EXCLUDED_DOUBLE_SUFFIXES):
        return True
    if any(rel.endswith(suffix) for suffix in LOCAL_SECRET_SUFFIXES):
        return True
    if any(rel == prefix or rel.startswith(prefix + "/") for prefix in EXCLUDED_PREFIXES):
        return True
    return False


def iter_export_files(root: Path, *, output_path: Path | None = None) -> list[Path]:
    root = root.resolve()
    git_files = _git_publication_files(root, output_path=output_path)
    if git_files is not None:
        return git_files
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if should_exclude(path, root, output_path=output_path):
            continue
        if path.is_file():
            files.append(path)
    return files


def _git_publication_files(root: Path, *, output_path: Path | None = None) -> list[Path] | None:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    files: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe publication snapshot path: {relative}")
        candidate = root / relative
        if candidate.is_symlink():
            raise RuntimeError(f"publication snapshot contains a symlink: {relative}")
        if candidate.is_file() and not should_exclude(candidate, root, output_path=output_path):
            files.append(candidate)
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def export_archive(root: Path, output: Path, *, prefix: str = "datalens-dev-mcp") -> dict[str, object]:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = iter_export_files(root, output_path=output)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            archive.write(path, arcname=f"{prefix.rstrip('/')}/{rel}")
    return {
        "ok": True,
        "profile": "runtime",
        "root": str(root),
        "output": str(output),
        "archive_prefix": prefix.rstrip("/"),
        "file_count": len(files),
        "output_bytes": output.stat().st_size,
        "excluded": {
            "directories": sorted(ROOT_EXCLUDED_DIR_NAMES),
            "prefixes": sorted(EXCLUDED_PREFIXES),
            "root_files": sorted(EXCLUDED_ROOT_FILES),
            "local_secret_files": sorted(LOCAL_SECRET_FILES),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean runtime zip archive for datalens-dev-mcp.")
    parser.add_argument("--profile", default="runtime", choices=["runtime"], help="Export profile.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--output", required=True, help="Output zip path.")
    parser.add_argument("--prefix", default="datalens-dev-mcp", help="Top-level directory name inside the archive.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned file list instead of writing the archive.")
    args = parser.parse_args()

    root = Path(args.root)
    output = Path(args.output)
    if args.dry_run:
        resolved_root = root.resolve()
        files = iter_export_files(resolved_root, output_path=output.resolve())
        payload = {
            "ok": True,
            "profile": args.profile,
            "file_count": len(files),
            "files": [str(path.relative_to(resolved_root)) for path in files],
        }
        print(json.dumps(payload, indent=2))
        return 0
    summary = export_archive(root, output, prefix=args.prefix)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
