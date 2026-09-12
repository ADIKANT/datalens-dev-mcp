"""Reject retired runtime owners and private-file classes in release archives.

This structural check is not a substitute for a synthetic-fixture/privacy review.
"""

from __future__ import annotations

import ast
import json
import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path


def audit(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            contents = {name: archive.read(name) for name in names if not name.endswith("/")}
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
            contents = {item.name: archive.extractfile(item).read() for item in archive.getmembers() if item.isfile()}
    forbidden = {"pipeline", "memory-bank", "__pycache__", ".git", "artifacts", ".env"}
    bad = [
        name
        for name in names
        if forbidden.intersection(Path(name).parts) or name.endswith((".pyc", ".env", ".pem", ".key"))
    ]
    if bad:
        raise ValueError(f"{path.name}: forbidden archive members: {bad}")
    for required in ("server.py", "api/sdk_adapter.py", "assets/recipes/registry.json"):
        if not any(name.endswith("datalens_dev_mcp/" + required) for name in names):
            raise ValueError(f"{path.name}: missing {required}")
    runtime_paths = [name for name in contents if name.endswith("datalens_dev_mcp/__init__.py")]
    metadata_paths = [name for name in contents if name.endswith((".dist-info/METADATA", "/PKG-INFO"))]
    if len(runtime_paths) != 1 or not metadata_paths:
        raise ValueError("missing or ambiguous package version metadata")
    versions = [ast.literal_eval(node.value) for node in ast.parse(contents[runtime_paths[0]]).body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__"
                                                       for t in node.targets)]
    versions.extend(Parser().parsestr(contents[name].decode())["Version"] for name in metadata_paths)
    for name, content in contents.items():
        if name.endswith("/pyproject.toml"):
            versions.append(tomllib.loads(content.decode())["project"]["version"])
        elif name.endswith("/.codex-plugin/plugin.json"):
            versions.append(json.loads(content)["version"])
    if not versions or len(set(versions)) != 1 or None in versions:
        raise ValueError("archive package metadata and content version differ")
    print(f"{path.name}: structural archive and version audit passed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Provide wheel and/or source archive paths")
    for argument in sys.argv[1:]:
        audit(Path(argument))
