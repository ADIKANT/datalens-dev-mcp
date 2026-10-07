"""Deterministic content identity, shared by packaging and the active runtime."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

PACKAGE_EXCLUDES = ("assets/templates", "assets/config/datalens_mcp.local.json")


def content_digest(root: Path, *, exclude: tuple[str, ...] = ()) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(relative == item or relative.startswith(item + "/") for item in exclude):
            continue
        if (path.is_file() and path.suffix in {".py", ".json", ".js", ".md"}
                and path.name != "_build_provenance.json" and "__pycache__" not in path.parts):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def build_provenance(root: Path) -> dict:
    package = root / "src/datalens_dev_mcp"
    carried = package / "_build_provenance.json"
    if carried.is_file():
        # A source archive has no Git directory. Preserve the original source
        # identity only while its package bytes still agree with the stamp.
        value = json.loads(carried.read_text())
        if value["package_content_sha256"] != content_digest(package, exclude=PACKAGE_EXCLUDES):
            raise ValueError("Source archive content does not match packaged provenance")
        return value
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    value = {"format": 1, "package_version": project["version"],
             "sdk_pin": next(x.split("==", 1)[1] for x in project["dependencies"] if x.startswith("datalens-sdk==")),
             "source_commit": None, "source_tree": None, "commit_status": "unknown",
             "package_content_sha256": content_digest(package, exclude=PACKAGE_EXCLUDES), "schema_sha256": content_digest(package / "schemas"),
             "assets_sha256": content_digest(package / "assets", exclude=("templates", "config/datalens_mcp.local.json")), "skills_sha256": content_digest(root / "skills")}
    if (root / ".git").exists():
        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
        value.update(source_commit=git("rev-parse", "HEAD"), source_tree=git("rev-parse", "HEAD^{tree}"),
                     commit_status="dirty" if git("status", "--porcelain", "--untracked-files=normal") else "clean")
    return value
