"""Local JSON artifacts are data, never executable scripts or instructions."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


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
