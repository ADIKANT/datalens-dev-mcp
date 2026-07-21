from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.scheduler import record_cache_hit


ASSET_PACKAGE = "datalens_dev_mcp.assets"
RESOURCE_OVERRIDE_ENV = "DATALENS_MCP_RESOURCE_ROOT"


@dataclass(frozen=True)
class RuntimeResourceError(RuntimeError):
    category: str
    resource_path: str
    message: str

    def __str__(self) -> str:
        return f"{self.category}: {self.resource_path}: {self.message}"


def resource_text(relative_path: str) -> str:
    path = _clean_relative_path(relative_path)
    try:
        override = _override_root()
        if override:
            target = _override_path(override, path)
            if not target.is_file():
                raise RuntimeResourceError("missing_runtime_resource", path, "resource is absent from override root")
            return target.read_text(encoding="utf-8")
        hits_before = _package_resource_text.cache_info().hits
        value = _package_resource_text(path)
        if _package_resource_text.cache_info().hits > hits_before:
            record_cache_hit("packaged_resource_text")
        return value
    except RuntimeResourceError:
        raise
    except UnicodeDecodeError as exc:
        raise RuntimeResourceError("corrupt_runtime_resource", path, "resource is not valid UTF-8") from exc
    except OSError as exc:
        raise RuntimeResourceError("runtime_resource_io_error", path, exc.__class__.__name__) from exc


def resource_json(relative_path: str, *, expected_object: bool = True) -> Any:
    path = _clean_relative_path(relative_path)
    try:
        if _override_root():
            value = json.loads(resource_text(path))
        else:
            hits_before = _package_resource_json.cache_info().hits
            value = copy.deepcopy(_package_resource_json(path))
            if _package_resource_json.cache_info().hits > hits_before:
                record_cache_hit("packaged_resource_json")
    except json.JSONDecodeError as exc:
        raise RuntimeResourceError("corrupt_runtime_resource", path, f"invalid JSON at line {exc.lineno}") from exc
    if expected_object and not isinstance(value, dict):
        raise RuntimeResourceError("corrupt_runtime_resource", path, "JSON resource must be an object")
    return value


def resource_exists(relative_path: str) -> bool:
    path = _clean_relative_path(relative_path)
    override = _override_root()
    if override:
        return _override_path(override, path).exists()
    return _assets_root().joinpath(*path.split("/")).is_file()


def resource_child_texts(relative_dir: str, names: list[str] | tuple[str, ...]) -> dict[str, str]:
    base = _clean_relative_path(relative_dir).rstrip("/")
    return {name: resource_text(f"{base}/{name}") for name in names}


def resource_manifest() -> list[dict[str, Any]]:
    override = _override_root()
    if override:
        return _filesystem_manifest(override)
    hits_before = _package_manifest.cache_info().hits
    manifest = _package_manifest()
    if _package_manifest.cache_info().hits > hits_before:
        record_cache_hit("packaged_resource_manifest")
    return [
        {"path": path, "bytes": byte_count, "sha256": sha256}
        for path, byte_count, sha256 in manifest
    ]


def declared_resource_manifest() -> dict[str, Any]:
    if _override_root():
        return resource_json("resource_manifest.json")
    return copy.deepcopy(_package_declared_resource_manifest())


@lru_cache(maxsize=1)
def _package_declared_resource_manifest() -> dict[str, Any]:
    return resource_json("resource_manifest.json")


def _clean_relative_path(relative_path: str) -> str:
    path = str(relative_path or "").strip().replace("\\", "/")
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise RuntimeResourceError("invalid_runtime_resource_path", path, "resource path must be relative")
    return path


def _override_root() -> Path | None:
    raw = os.getenv(RESOURCE_OVERRIDE_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _override_path(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise RuntimeResourceError("invalid_runtime_resource_path", relative_path, "resource path escapes override root")
    return target


def _assets_root() -> resources.abc.Traversable:
    return resources.files(ASSET_PACKAGE)


@lru_cache(maxsize=256)
def _package_resource_text(path: str) -> str:
    target = _assets_root().joinpath(*path.split("/"))
    if not target.is_file():
        raise RuntimeResourceError("missing_runtime_resource", path, "resource is absent from package assets")
    return target.read_text(encoding="utf-8")


@lru_cache(maxsize=128)
def _package_resource_json(path: str) -> Any:
    try:
        return json.loads(_package_resource_text(path))
    except json.JSONDecodeError as exc:
        raise RuntimeResourceError("corrupt_runtime_resource", path, f"invalid JSON at line {exc.lineno}") from exc


@lru_cache(maxsize=1)
def _package_manifest() -> tuple[tuple[str, int, str], ...]:
    root = _assets_root()
    rows: list[dict[str, Any]] = []

    def walk(node: resources.abc.Traversable, prefix: str = "") -> None:
        for child in sorted(node.iterdir(), key=lambda item: item.name):
            rel = f"{prefix}/{child.name}" if prefix else child.name
            if child.is_dir():
                walk(child, rel)
            elif child.is_file() and _include_manifest_file(rel):
                data = child.read_bytes()
                rows.append(_manifest_row(rel, data))

    walk(root)
    return tuple((str(row["path"]), int(row["bytes"]), str(row["sha256"])) for row in rows)


def _filesystem_manifest(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or not _include_manifest_file(rel):
            continue
        rows.append(_manifest_row(rel, path.read_bytes()))
    return rows


def _include_manifest_file(relative_path: str) -> bool:
    name = Path(relative_path).name
    return (
        name not in {"__init__.py", "resource_manifest.json", "datalens_mcp.local.json"}
        and "__pycache__" not in Path(relative_path).parts
    )


def _manifest_row(path: str, data: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
