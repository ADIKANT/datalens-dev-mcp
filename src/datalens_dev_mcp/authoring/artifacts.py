"""Local JSON artifacts are data, never executable scripts or instructions."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

_SAFE_ARTIFACT_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def default_recipe_artifact_dir(recipe_id: str) -> Path:
    """Create a private external-state directory for one compiled recipe."""
    state_home = os.environ.get("XDG_STATE_HOME")
    state_root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    root = state_root / "datalens-dev-mcp" / "recipe-artifacts"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe_name = _SAFE_ARTIFACT_NAME.sub("-", recipe_id).strip("-._")[:48] or "recipe"
    return Path(tempfile.mkdtemp(prefix=f"{safe_name}-", dir=root))


def prune_recipe_artifacts(
    keep: Path,
    *,
    max_directories: int = 200,
    max_bytes: int = 16 * 1024 * 1024,
    max_age_seconds: int = 30 * 24 * 60 * 60,
) -> None:
    """Bound completed recipe artifacts while preserving the current result."""
    keep = keep.resolve()
    root = keep.parent
    now = time.time()
    dated_directories: list[tuple[float, Path]] = []
    for path in root.iterdir():
        try:
            if path.is_dir() and not path.is_symlink():
                dated_directories.append((path.stat().st_mtime, path))
        except OSError:
            continue
    dated_directories.sort()
    for modified_at, path in dated_directories:
        if path != keep and now - modified_at > max_age_seconds:
            shutil.rmtree(path, ignore_errors=True)

    while True:
        live = [path for _, path in dated_directories if path.exists()]
        total_bytes = sum(_directory_size(path) for path in live)
        if len(live) <= max_directories and total_bytes <= max_bytes:
            return
        candidate = next((path for path in live if path != keep), None)
        if candidate is None:
            return
        shutil.rmtree(candidate, ignore_errors=True)
        dated_directories = [(modified_at, path) for modified_at, path in dated_directories if path != candidate]


def _directory_size(path: Path) -> int:
    size = 0
    try:
        children = path.rglob("*")
        for child in children:
            try:
                if child.is_file() and not child.is_symlink():
                    size += child.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0
    return size


def resolve_artifact(value: dict[str, Any]) -> dict[str, Any]:
    if "artifact_path" not in value:
        return deepcopy(value)
    if set(value) - {"artifact_path", "client_ref", "depends_on"}:
        raise ValueError("artifact references allow only artifact_path, client_ref and depends_on")
    raw = value["artifact_path"]
    if not isinstance(raw, str) or not raw:
        raise ValueError("artifact_path must be a nonempty absolute local path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("artifact_path must be absolute")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "artifact_path" in document:
        raise ValueError("artifact must contain one concrete JSON object, not another reference")
    for key in ("client_ref", "depends_on"):
        if key in value:
            document[key] = deepcopy(value[key])
    return document
