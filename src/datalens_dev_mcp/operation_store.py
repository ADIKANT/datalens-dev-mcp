from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def default_operation_root() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return root / "datalens-dev-mcp" / "operations"


class OperationStore:
    """Small durable records for modifying API calls, not a task journal."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_operation_root()

    def get(self, operation_id: str) -> dict[str, Any] | None:
        path = self._path(operation_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"invalid operation record: {operation_id}")
        return value

    def put(self, record: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(record.get("operation_id") or "")
        path = self._path(operation_id)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return deepcopy(record)

    def _path(self, operation_id: str) -> Path:
        if not _SAFE_ID.fullmatch(operation_id):
            raise ValueError("operation_id must contain only letters, digits, dot, underscore or hyphen")
        return self.root / f"{operation_id}.json"

