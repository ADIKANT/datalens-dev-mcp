from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
from typing import Any

from datalens_dev_mcp import __version__
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


BUILD_IDENTITY_SCHEMA_ID = "datalens_build_identity"
BUILD_IDENTITY_KINDS = frozenset({"git", "archive_manifest", "installed_wheel", "resource_manifest"})


class BuildIdentityError(RuntimeError):
    pass


class BuildIdentityResolver:
    """Resolve a restart-stable identity for the exact server source in use."""

    def __init__(
        self,
        source_root: str | Path | None = None,
        *,
        archive_manifest_path: str | Path | None = None,
        wheel_record_path: str | Path | None = None,
        resource_manifest_path: str | Path | None = None,
    ) -> None:
        self.source_root = Path(source_root).resolve() if source_root else Path(__file__).resolve().parents[3]
        self.archive_manifest_path = Path(archive_manifest_path).resolve() if archive_manifest_path else None
        self.wheel_record_path = Path(wheel_record_path).resolve() if wheel_record_path else None
        self.resource_manifest_path = (
            Path(resource_manifest_path).resolve()
            if resource_manifest_path
            else Path(__file__).resolve().parents[1] / "assets" / "resource_manifest.json"
        )

    def resolve(self) -> dict[str, Any]:
        candidates = (
            self._from_git,
            self._from_archive_manifest,
            self._from_installed_wheel,
            self._from_resource_manifest,
        )
        errors: list[str] = []
        for resolver in candidates:
            try:
                value = resolver()
            except (BuildIdentityError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{resolver.__name__}: {exc}")
                continue
            if value:
                issues = validate_build_identity(value)
                if issues:
                    errors.append(f"{resolver.__name__}: {'; '.join(issues)}")
                    continue
                return value
        raise BuildIdentityError("stable server build identity is unavailable: " + " | ".join(errors))

    def _from_git(self) -> dict[str, Any] | None:
        root_result = self._git("rev-parse", "--show-toplevel")
        if root_result is None:
            return None
        root = Path(root_result).resolve()
        head = self._git("rev-parse", "HEAD", cwd=root)
        tree = self._git("rev-parse", "HEAD^{tree}", cwd=root)
        if not head or not tree:
            raise BuildIdentityError("git HEAD or tree is unavailable")
        branch = self._git("branch", "--show-current", cwd=root) or ""
        listing = self._git_bytes("ls-files", "--cached", "--others", "--exclude-standard", "-z", cwd=root)
        if listing is None:
            raise BuildIdentityError("git publication inventory is unavailable")
        digest = hashlib.sha256()
        count = 0
        for raw in sorted(item for item in listing.split(b"\0") if item):
            relative = Path(raw.decode("utf-8"))
            if relative.is_absolute() or ".." in relative.parts:
                raise BuildIdentityError("git publication inventory contains an unsafe path")
            path = root / relative
            if not path.is_file() or path.is_symlink():
                continue
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
            count += 1
        if not count:
            raise BuildIdentityError("git publication inventory is empty")
        return _finalize_identity(
            kind="git",
            commit=head,
            branch=branch,
            tree_hash=tree,
            package_content_hash=digest.hexdigest(),
            provenance={"publication_file_count": count},
        )

    def _from_archive_manifest(self) -> dict[str, Any] | None:
        candidates = [
            self.archive_manifest_path,
            self.source_root / "ARCHIVE_MANIFEST.json",
            self.source_root / "archive-manifest.json",
        ]
        path = next((item for item in candidates if item and item.is_file()), None)
        if path is None:
            return None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        commit = str(manifest.get("snapshot_commit") or manifest.get("commit") or "")
        tree_hash = str(manifest.get("publication_tree_hash") or manifest.get("tree_hash") or "")
        content_hash = str(manifest.get("package_content_hash") or manifest.get("content_hash") or "")
        if not tree_hash and content_hash:
            tree_hash = content_hash
        if not content_hash:
            content_hash = _directory_content_hash(path.parent, excluded={path.name})
        if not tree_hash:
            tree_hash = content_hash
        return _finalize_identity(
            kind="archive_manifest",
            commit=commit,
            branch=str(manifest.get("branch") or ""),
            tree_hash=tree_hash,
            package_content_hash=content_hash,
            provenance={"manifest_sha256": _sha256_file(path)},
        )

    def _from_installed_wheel(self) -> dict[str, Any] | None:
        path = self.wheel_record_path
        if path is None:
            try:
                distribution = importlib.metadata.distribution("datalens-dev-mcp")
            except importlib.metadata.PackageNotFoundError:
                return None
            record = next((item for item in distribution.files or () if item.name == "RECORD"), None)
            if record is None:
                return None
            path = Path(distribution.locate_file(record)).resolve()
        if not path.is_file():
            return None
        normalized_rows: list[tuple[str, str, str]] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if not row:
                    continue
                normalized_rows.append(tuple((row + ["", ""])[:3]))
        if not normalized_rows:
            raise BuildIdentityError("installed wheel RECORD is empty")
        content_hash = canonical_hash(sorted(normalized_rows))
        return _finalize_identity(
            kind="installed_wheel",
            commit="",
            branch="",
            tree_hash=content_hash,
            package_content_hash=content_hash,
            provenance={"record_entry_count": len(normalized_rows)},
        )

    def _from_resource_manifest(self) -> dict[str, Any] | None:
        path = self.resource_manifest_path
        if not path.is_file():
            return None
        digest = _sha256_file(path)
        return _finalize_identity(
            kind="resource_manifest",
            commit="",
            branch="",
            tree_hash=digest,
            package_content_hash=digest,
            provenance={"resource_manifest_sha256": digest},
        )

    def _git(self, *args: str, cwd: Path | None = None) -> str | None:
        value = self._git_bytes(*args, cwd=cwd)
        return value.decode("utf-8", errors="replace").strip() if value is not None else None

    def _git_bytes(self, *args: str, cwd: Path | None = None) -> bytes | None:
        result = subprocess.run(
            ["git", "-C", str(cwd or self.source_root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return result.stdout if result.returncode == 0 else None


def validate_build_identity(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != BUILD_IDENTITY_SCHEMA_ID:
        issues.append("build identity schema_id is invalid")
    if value.get("kind") not in BUILD_IDENTITY_KINDS:
        issues.append("build identity kind is invalid")
    if not str(value.get("tree_hash") or ""):
        issues.append("build identity tree_hash is empty")
    if not str(value.get("package_content_hash") or ""):
        issues.append("build identity package_content_hash is empty")
    supplied = str(value.get("identity_hash") or "")
    if not supplied or supplied != build_identity_hash(value):
        issues.append("build identity hash mismatch")
    return tuple(issues)


def build_identity_hash(value: dict[str, Any]) -> str:
    material = {
        "schema_id": value.get("schema_id"),
        "kind": value.get("kind"),
        "commit": value.get("commit") or "",
        "tree_hash": value.get("tree_hash") or "",
        "package_content_hash": value.get("package_content_hash") or "",
    }
    return canonical_hash(material)


def _finalize_identity(
    *,
    kind: str,
    commit: str,
    branch: str,
    tree_hash: str,
    package_content_hash: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_id": BUILD_IDENTITY_SCHEMA_ID,
        "kind": kind,
        "commit": commit,
        "branch": branch,
        "tree_hash": tree_hash,
        "package_content_hash": package_content_hash,
        "package_release": __version__,
        "provenance": provenance,
    }
    payload["identity_hash"] = build_identity_hash(payload)
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_content_hash(root: Path, *, excluded: set[str]) -> str:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name in excluded:
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        count += 1
    if not count:
        raise BuildIdentityError("archive package content is empty")
    return digest.hexdigest()
