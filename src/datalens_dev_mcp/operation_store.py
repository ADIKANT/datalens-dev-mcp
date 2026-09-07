from __future__ import annotations

import json
import os
import re
import tempfile
import time
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

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        max_records: int = 200,
        max_bytes: int = 16 * 1024 * 1024,
        max_age_seconds: int = 30 * 24 * 60 * 60,
    ) -> None:
        self.root = Path(root) if root is not None else default_operation_root()
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.max_age_seconds = max_age_seconds

    def get(self, operation_id: str) -> dict[str, Any] | None:
        path = self._path(operation_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(f"invalid operation record: {operation_id}")
        return value

    def put(self, record: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(record.get("operation_id") or "")
        path = self._path(operation_id)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix=f".{operation_id}-", suffix=".tmp", dir=self.root)
        temporary = Path(filename)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self._prune(keep=path)
        return deepcopy(record)

    def _prune(self, *, keep: Path) -> None:
        now = time.time()
        terminal: list[tuple[float, Path]] = []
        for path in self.root.glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                status = value.get("status") if isinstance(value, dict) else None
                mtime = path.stat().st_mtime
            except (OSError, ValueError, TypeError):
                continue
            # Pending, partial, blocked and uncertain records are recovery state.
            if status not in {"completed", "failed"}:
                continue
            if path != keep and now - mtime > self.max_age_seconds:
                path.unlink(missing_ok=True)
                continue
            terminal.append((mtime, path))
        terminal.sort(key=lambda item: item[0])
        while terminal:
            live = [(mtime, path) for mtime, path in terminal if path.exists()]
            total_bytes = sum(path.stat().st_size for _, path in live)
            if len(live) <= self.max_records and total_bytes <= self.max_bytes:
                break
            candidate = next((path for _, path in live if path != keep), None)
            if candidate is None:
                break
            candidate.unlink(missing_ok=True)
            terminal = [(mtime, path) for mtime, path in live if path != candidate]

    def _path(self, operation_id: str) -> Path:
        if not _SAFE_ID.fullmatch(operation_id):
            raise ValueError("operation_id must contain only letters, digits, dot, underscore or hyphen")
        return self.root / f"{operation_id}.json"


def compact_operation(record: dict[str, Any]) -> dict[str, Any]:
    """Project a durable operation record onto the default public response."""
    if record.get("status") == "not_found":
        return deepcopy(record)
    result: dict[str, Any] = {
        key: deepcopy(record[key])
        for key in ("ok", "operation_id", "effect", "status", "write_replayed")
        if key in record
    }
    compact_items = []
    for item in record.get("results") or []:
        if not isinstance(item, dict):
            continue
        compact_items.append(
            {
                key: deepcopy(item[key])
                for key in (
                    "key",
                    "status",
                    "code",
                    "target",
                    "observed_revision",
                    "expected_revision",
                    "returned_revision",
                    "error",
                )
                if key in item
            }
        )
    result["results"] = compact_items
    if result.get("operation_id"):
        result["detail_reference"] = {"operation_id": result["operation_id"], "include_detail": True}
    return result
