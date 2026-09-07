"""Reject retired runtime owners and private-file classes in release archives.

This structural check is not a substitute for a synthetic-fixture/privacy review.
"""
from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


def audit(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    forbidden = {"pipeline", "memory-bank", "__pycache__", ".git", "artifacts", ".env"}
    bad = [name for name in names if forbidden.intersection(Path(name).parts)
           or name.endswith((".pyc", ".env", ".pem", ".key"))]
    if bad:
        raise ValueError(f"{path.name}: forbidden archive members: {bad}")
    for required in ("server.py", "api/sdk_adapter.py", "assets/recipes/registry.json"):
        if not any(name.endswith("datalens_dev_mcp/" + required) for name in names):
            raise ValueError(f"{path.name}: missing {required}")
    print(f"{path.name}: structural archive audit passed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Provide wheel and/or source archive paths")
    for argument in sys.argv[1:]:
        audit(Path(argument))
