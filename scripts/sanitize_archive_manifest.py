#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re


ABSOLUTE_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s]+(?:/[^\s]*)?")
WINDOWS_USER_PATH = re.compile(r"[A-Za-z]:\\Users\\[^\s]+", re.I)


def sanitize_manifest_text(text: str, *, source_root: str = "") -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if source_root:
        normalized = normalized.replace(str(Path(source_root).expanduser().resolve()), "<SOURCE_ROOT>")
    normalized = ABSOLUTE_USER_PATH.sub("<SOURCE_ROOT>", normalized)
    normalized = WINDOWS_USER_PATH.sub("<SOURCE_ROOT>", normalized)
    lines = [line.rstrip() for line in normalized.splitlines()]
    return "\n".join(lines).strip() + "\n"


def generate_manifest(root: Path) -> str:
    rows = ["# Sanitized archive manifest", "", "path\tbytes\tsha256"]
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        rows.append(f"{relative}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}")
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or sanitize a deterministic public-safe archive manifest.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", default="")
    args = parser.parse_args()
    if args.source.is_dir():
        rendered = generate_manifest(args.source.resolve())
    else:
        rendered = sanitize_manifest_text(args.source.read_text(encoding="utf-8"), source_root=args.source_root)
    if "/Users/" in rendered or "\\Users\\" in rendered:
        raise SystemExit("manifest still contains an absolute user path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"sanitized archive manifest: {args.output} ({len(rendered.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
