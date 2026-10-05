"""Identity captured by the active process; no dependence on the caller's Git checkout."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from uuid import uuid4

import datalens_sdk

from datalens_dev_mcp import __version__
from datalens_dev_mcp.provenance import PACKAGE_EXCLUDES, content_digest

CAPABILITY_REVISION = "2026-10-02.1"
_ACTIVE_SDK_VERSION = datalens_sdk.__version__
_PACKAGE_ROOT = Path(__file__).resolve().parent


def _load_provenance(path: Path, digest: str) -> dict:
    unknown = {"source_commit": None, "commit_status": "unknown"}
    if not path.is_file():
        return unknown
    try:
        value = json.loads(path.read_text())
        import re
        if (not isinstance(value, dict) or value.get("format") != 1
                or value.get("commit_status") not in {"clean", "dirty", "unknown"}
                or any(not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", value[key])
                       for key in ("package_content_sha256", "schema_sha256", "assets_sha256", "skills_sha256"))
                or (value.get("commit_status") != "unknown" and
                    any(not re.fullmatch(r"[0-9a-f]{40,64}", str(value.get(key, "")))
                        for key in ("source_commit", "source_tree")))):
            raise ValueError("invalid provenance")
        if (value["package_content_sha256"] != digest or value.get("package_version") != __version__
                or value.get("sdk_pin") != _ACTIVE_SDK_VERSION):
            return {**unknown, "commit_status": "mismatch"}
        return value
    except (OSError, ValueError, TypeError):
        return {**unknown, "commit_status": "invalid"}


_ACTIVE_PACKAGE_DIGEST = content_digest(_PACKAGE_ROOT, exclude=PACKAGE_EXCLUDES)
_ACTIVE_PROVENANCE = _load_provenance(_PACKAGE_ROOT / "_build_provenance.json", _ACTIVE_PACKAGE_DIGEST)
_INSTANCE = {"instance_id": uuid4().hex, "pid": os.getpid(),
             "started_at": datetime.now(UTC).isoformat(), "package_version": __version__, "sdk_version": _ACTIVE_SDK_VERSION,
             "import_kind": "site-packages" if "site-packages" in _PACKAGE_ROOT.parts else "source"}


def runtime_identity() -> dict:
    try:
        installed_version = metadata.version("datalens-dev-mcp")
    except metadata.PackageNotFoundError:
        installed_version = None
    try:
        installed_sdk = metadata.version("datalens-sdk")
    except metadata.PackageNotFoundError:
        installed_sdk = None
    return {
        "installed_sdk_version": installed_sdk,
        "active_sdk_matches_installed": installed_sdk == _ACTIVE_SDK_VERSION if installed_sdk else None,
        "runtime": dict(_INSTANCE),
        "capability_revision": CAPABILITY_REVISION,
        "build": {"package_content_sha256": _ACTIVE_PACKAGE_DIGEST,
                  **_ACTIVE_PROVENANCE},
        "installed_distribution_version": installed_version,
        "active_version_matches_installed": installed_version == __version__ if installed_version else None,
    }
