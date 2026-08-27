from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

from datalens_dev_mcp.pipeline.build_identity import BuildIdentityResolver


def _run(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_git_identity_detects_content_drift_but_ignores_branch_display_name() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _run(root, "init")
        _run(root, "config", "user.name", "Public Test")
        _run(root, "config", "user.email", "public-test@example.invalid")
        (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        _run(root, "add", "module.py")
        _run(root, "commit", "-m", "Initial")
        first = BuildIdentityResolver(root).resolve()
        _run(root, "switch", "-c", "renamed-source")
        renamed = BuildIdentityResolver(root).resolve()
        assert first["branch"] != renamed["branch"]
        assert first["identity_hash"] == renamed["identity_hash"]
        (root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
        changed = BuildIdentityResolver(root).resolve()
        assert changed["tree_hash"] == first["tree_hash"]
        assert changed["package_content_hash"] != first["package_content_hash"]
        assert changed["identity_hash"] != first["identity_hash"]


def test_archive_manifest_commit_change_changes_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = root / "ARCHIVE_MANIFEST.json"
        payload = {"snapshot_commit": "a" * 40, "publication_tree_hash": "b" * 64, "package_content_hash": "c" * 64}
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        first = BuildIdentityResolver(root, archive_manifest_path=manifest).resolve()
        payload["snapshot_commit"] = "d" * 40
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        second = BuildIdentityResolver(root, archive_manifest_path=manifest).resolve()
        assert first["kind"] == "archive_manifest"
        assert first["identity_hash"] != second["identity_hash"]


def test_installed_wheel_record_fingerprint_is_restart_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = root / "RECORD"
        record.write_text("pkg/a.py,sha256=abc,10\npkg.dist-info/RECORD,,\n", encoding="utf-8")
        first = BuildIdentityResolver(root, wheel_record_path=record).resolve()
        second = BuildIdentityResolver(root, wheel_record_path=record).resolve()
        assert first["kind"] == "installed_wheel"
        assert first["identity_hash"] == second["identity_hash"]
        assert first["package_content_hash"]


def test_resource_manifest_is_last_non_empty_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = root / "resource_manifest.json"
        manifest.write_text('{"resources": []}\n', encoding="utf-8")
        identity = BuildIdentityResolver(root, resource_manifest_path=manifest).resolve()
        assert identity["kind"] == "resource_manifest"
        assert identity["tree_hash"]
        assert identity["identity_hash"]
