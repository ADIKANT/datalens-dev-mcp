from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

GENERIC_DEFAULTS: dict[str, Any] = {
    "theme": "auto",
    "spacing": 8,
    "title": {"owner": "widget", "visible": True},
    "hint": {"owner": "widget", "enabled": True},
    "technology": "wizard",
}
FORBIDDEN_CONFIG_KEYS = {"workflow", "history", "messages", "memory", "task", "orchestrator"}


def get_authoring_defaults(
    project_root: str | Path | None = None,
    family: str | None = None,
    *,
    explicit: Mapping[str, Any] | None = None,
    reference: Mapping[str, Any] | None = None,
    user_config_path: str | Path | None = None,
) -> dict[str, Any]:
    user_path = Path(user_config_path).expanduser() if user_config_path else _user_config_path()
    project_path = Path(project_root).expanduser().resolve() / ".datalens/authoring.json" if project_root else None
    user = _read_config(user_path)
    project = _read_config(project_path) if project_path else {}
    values = deepcopy(GENERIC_DEFAULTS)
    sources = ["generic"]
    for name, config in (("user", user), ("project", project)):
        if config:
            values = _deep_merge(values, _config_values(config, family))
            sources.append(name)
    if reference:
        values = _deep_merge(values, dict(reference))
        sources.append("reference")
    if explicit:
        values = _deep_merge(values, dict(explicit))
        sources.append("explicit")
    return {
        "ok": True,
        "family": family,
        "values": values,
        "precedence": ["generic", "user", "project", "reference", "explicit"],
        "applied_sources": sources,
        "config": {
            "user": str(user_path) if user else None,
            "project": str(project_path) if project and project_path else None,
        },
        "allowed_reference_files": [
            *_reference_files(user, user_path.parent),
            *_reference_files(project, project_path.parent if project_path else Path.cwd()),
        ],
    }


def _user_config_path() -> Path:
    base = Path(os.environ["XDG_CONFIG_HOME"]).expanduser() if os.environ.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / "datalens-dev-mcp/authoring.json"


def _read_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"authoring config must contain an object: {path}")
    forbidden = FORBIDDEN_CONFIG_KEYS.intersection(str(key).lower() for key in value)
    if forbidden:
        raise ValueError("authoring config cannot contain workflow, history, task, orchestrator, or memory state")
    return value


def _config_values(config: Mapping[str, Any], family: str | None) -> dict[str, Any]:
    values = dict(config.get("defaults") or {}) if isinstance(config.get("defaults"), Mapping) else {}
    families = config.get("families")
    if family and isinstance(families, Mapping) and isinstance(families.get(family), Mapping):
        values = _deep_merge(values, dict(families[family]))
    return values


def _reference_files(config: Mapping[str, Any], base: Path) -> list[str]:
    raw = config.get("reference_files")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser()
        result.append(str((base / path).resolve() if not path.is_absolute() else path.resolve()))
    return result


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
