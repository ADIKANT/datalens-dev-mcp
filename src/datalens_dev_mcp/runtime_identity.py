"""Identity captured by the active process; no dependence on the caller's Git checkout."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from uuid import uuid4

import datalens_sdk

from datalens_dev_mcp import __version__

CAPABILITY_REVISION = "2026-09-12.1"
_ACTIVE_SDK_VERSION = datalens_sdk.__version__
_PACKAGE_ROOT = Path(__file__).resolve().parent


def _package_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(_PACKAGE_ROOT.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".js"}:
            digest.update(path.relative_to(_PACKAGE_ROOT).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


_ACTIVE_PACKAGE_DIGEST = _package_digest()
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
                  "source_commit": None, "commit_status": "unknown"},
        "installed_distribution_version": installed_version,
        "active_version_matches_installed": installed_version == __version__ if installed_version else None,
    }
