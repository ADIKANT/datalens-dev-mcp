"""Local JSON artifacts are data, never executable scripts or instructions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

_SAFE_ARTIFACT_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def write_private_json(path: Path, value: Any) -> None:
    """Publish a complete JSON artifact with private permissions, including replacements."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".artifact-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def default_recipe_artifact_dir(recipe_id: str) -> Path:
    """Create a private external-state directory for one compiled recipe."""
    state_home = os.environ.get("XDG_STATE_HOME")
    state_root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    root = state_root / "datalens-dev-mcp" / "recipe-artifacts"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe_name = _SAFE_ARTIFACT_NAME.sub("-", recipe_id).strip("-._")[:48] or "recipe"
    return Path(tempfile.mkdtemp(prefix=f"{safe_name}-", dir=root))


def resolve_artifact(value: dict[str, Any]) -> dict[str, Any]:
    if "artifact_path" not in value:
        return deepcopy(value)
    if set(value) - {"artifact_path", "artifact_sha256", "client_ref", "depends_on"}:
        raise ValueError("artifact references allow only artifact_path, artifact_sha256, client_ref and depends_on")
    raw = value["artifact_path"]
    if not isinstance(raw, str) or not raw:
        raise ValueError("artifact_path must be a nonempty absolute local path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("artifact_path must be absolute")
    content = path.read_bytes()
    if "artifact_sha256" in value and hashlib.sha256(content).hexdigest() != value["artifact_sha256"]:
        raise ValueError("artifact_sha256 mismatch; review the changed local bytes before applying")
    document = json.loads(content.decode("utf-8"))
    if not isinstance(document, dict) or "artifact_path" in document:
        raise ValueError("artifact must contain one concrete JSON object, not another reference")
    for key in ("client_ref", "depends_on"):
        if key in value:
            document[key] = deepcopy(value[key])
    return document
