#!/usr/bin/env python3
"""Install the canonical DataLens dashboard skill into user scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


SKILL_NAME = "datalens-dashboard-work"


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--target-root", default=str(Path.home() / ".agents" / "skills"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    source = Path(args.repo_root).resolve() / "skills" / SKILL_NAME
    target_root = Path(args.target_root).expanduser().resolve()
    target = target_root / SKILL_NAME
    if not (source / "SKILL.md").is_file():
        raise SystemExit("canonical skill source is missing")
    source_hash = _tree_hash(source)
    if args.verify_only:
        if not target.is_dir() or _tree_hash(target) != source_hash:
            raise SystemExit("installed skill does not match canonical source")
        print(json.dumps({"ok": True, "skill": SKILL_NAME, "content_hash": source_hash}, sort_keys=True))
        return 0

    target_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}.", dir=target_root))
    backup = target_root / f".{SKILL_NAME}.previous"
    replaced_existing = False
    try:
        shutil.copytree(source, staging / SKILL_NAME)
        if target.exists():
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(target, backup)
            replaced_existing = True
        os.replace(staging / SKILL_NAME, target)
        installed_hash = _tree_hash(target)
        if installed_hash != source_hash:
            raise RuntimeError("installed skill verification failed")
    except Exception as exc:
        if target.exists():
            shutil.rmtree(target)
        if replaced_existing and backup.exists():
            os.replace(backup, target)
        raise SystemExit(str(exc)) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if backup.exists():
        shutil.rmtree(backup)
    print(json.dumps({"ok": True, "skill": SKILL_NAME, "content_hash": installed_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
