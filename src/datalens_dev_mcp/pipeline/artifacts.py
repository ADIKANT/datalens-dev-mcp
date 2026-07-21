from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_project_dirs(project_root: str | Path) -> Path:
    root = Path(project_root)
    for rel in (
        "requirements",
        "datalens_mapping/contracts",
        "dashboard",
        "dashboards",
        "artifacts/baselines",
        "artifacts/readback",
        "artifacts/payloads",
        "reports",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    _write_if_changed(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.is_file():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    _write_if_changed(target, content)


def read_text(path: str | Path, default: str = "") -> str:
    target = Path(path)
    return target.read_text(encoding="utf-8") if target.is_file() else default


def _write_if_changed(target: Path, content: str) -> None:
    """Avoid rewriting stable artifacts and invalidating downstream caches."""

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        try:
            if target.read_text(encoding="utf-8") == content:
                return
        except (OSError, UnicodeDecodeError):
            pass
    target.write_text(content, encoding="utf-8")
