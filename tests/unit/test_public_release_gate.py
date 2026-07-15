from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.check_public_release import REQUIRED_NOTICES, run_check


class PublicReleaseGateTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _write_required_notices(self, root: Path) -> None:
        for rel in REQUIRED_NOTICES:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Public notice: {rel}\n", encoding="utf-8")

    def _init_repo(self, root: Path, extra: dict[str, str] | None = None) -> None:
        self._git(root, "init", "-q")
        self._git(root, "config", "user.email", "release-gate@example.com")
        self._git(root, "config", "user.name", "Release Gate")
        self._write_required_notices(root)
        (root / "README.md").write_text(
            "Official docs: https://yandex.cloud/ru/docs/datalens/\n"
            "Official sources: https://github.com/yandex-cloud/docs\n"
            "Protocol: https://modelcontextprotocol.io/\n",
            encoding="utf-8",
        )
        for rel, content in (extra or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self._git(root, "add", ".")
        self._git(root, "commit", "-qm", "fixture")

    def test_clean_git_snapshot_and_official_sources_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)

            report = run_check(root)

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["issue_count"], 0)

    def test_required_release_notices_are_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")

            report = run_check(root)

        missing = {issue["path"] for issue in report["issues"] if issue["category"] == "missing_notice"}
        self.assertEqual(missing, {"LICENSES/CC-BY-4.0.txt", "THIRD_PARTY_NOTICES.md"})

    def test_concrete_datalens_object_url_is_rejected(self):
        object_url = (
            "https"
            + "://datalens.yandex.cloud/workbooks/abcdefghijkl"
            + "/dashboards/qwertyuiopas"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)
            (root / "private-target.md").write_text(object_url + "\n", encoding="utf-8")

            report = run_check(root)

        self.assertTrue(
            any(
                issue["category"] == "internal_url"
                and issue["message"] == "URL appears to identify a concrete DataLens object"
                for issue in report["issues"]
            ),
            report["issues"],
        )

    def test_standalone_datalens_shaped_id_is_rejected(self):
        concrete_id = "abcde" + "12345678"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)
            (root / "fixture.json").write_text(f'{{"dashboard_id": "{concrete_id}"}}\n', encoding="utf-8")

            report = run_check(root)

        self.assertTrue(
            any(issue["category"] == "concrete_datalens_id" for issue in report["issues"]),
            report["issues"],
        )

    def test_worktree_inventory_handles_deletions_edits_and_untracked_files(self):
        local_path = "/" + "Users/alice/private/config.json"
        synthetic_token = "abcdefghijklmnop" + "qrstuvwxyz123456"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(
                root,
                {
                    "artifacts/staged-delete.json": "private export\n",
                    "notes/unstaged-delete.md": "safe before deletion\n",
                    "notes/edited.md": "safe before edit\n",
                },
            )
            self._git(root, "rm", "-q", "artifacts/staged-delete.json")
            (root / "notes/unstaged-delete.md").unlink()
            (root / "notes/edited.md").write_text(local_path + "\n", encoding="utf-8")
            (root / "notes/untracked.md").write_text(
                f"Authorization: Bearer {synthetic_token}\n",
                encoding="utf-8",
            )

            report = run_check(root)

        paths = {issue["path"] for issue in report["issues"]}
        categories = {issue["category"] for issue in report["issues"]}
        self.assertFalse(report["ok"])
        self.assertNotIn("artifacts/staged-delete.json", paths)
        self.assertNotIn("notes/unstaged-delete.md", paths)
        self.assertIn("notes/edited.md", paths)
        self.assertIn("notes/untracked.md", paths)
        self.assertIn("absolute_local_path", categories)
        self.assertIn("secret", categories)

    def test_detects_source_material_private_key_internal_url_and_email(self):
        source_trace = "Source " + "trace: handbook." + "pdf pages 12-20"
        private_key = "-----BEGIN " + "PRIVATE KEY-----"
        internal_url = "https" + "://confluence." + "corp.internal/display/BI"
        internal_email = "owner" + "@corp.internal"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)
            (root / "notes.md").write_text(
                "\n".join((source_trace, private_key, internal_url, internal_email)) + "\n",
                encoding="utf-8",
            )

            report = run_check(root)

        categories = {issue["category"] for issue in report["issues"]}
        self.assertTrue(
            {"source_material_provenance", "secret", "internal_url", "internal_email"}.issubset(categories),
            report["issues"],
        )

    def test_detects_forbidden_paths_environment_files_and_binary_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)
            (root / "docs" / "reports").mkdir(parents=True)
            (root / "docs" / "reports" / "private.md").write_text("generated evidence\n", encoding="utf-8")
            (root / ".env.production").write_text("TOKEN=value\n", encoding="utf-8")
            (root / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")

            report = run_check(root)

        categories = {issue["category"] for issue in report["issues"]}
        self.assertIn("forbidden_path", categories)
        self.assertIn("unsafe_file_type", categories)

    def test_clean_wheel_and_source_distribution_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            self._write_required_notices(root)
            (root / "README.md").write_text("https://docs.yandex.cloud/ru/datalens/\n", encoding="utf-8")
            wheel = base / "package-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("package/__init__.py", "__version__ = '1.0'\n")
                archive.writestr("package-1.0.dist-info/licenses/LICENSE", "Apache-2.0\n")
                archive.writestr("package-1.0.dist-info/licenses/LICENSES/CC-BY-4.0.txt", "CC-BY-4.0\n")
                archive.writestr("package-1.0.dist-info/licenses/THIRD_PARTY_NOTICES.md", "Yandex Cloud docs\n")

            sdist = base / "package-1.0.tar.gz"
            with tarfile.open(sdist, "w:gz") as archive:
                members = {
                    "package-1.0/package.py": b"VALUE = 1\n",
                    "package-1.0/scripts/check_docs_consistency.py": b"MARKERS = ('/Users/', 'materials/raw/')\n",
                    "package-1.0/LICENSE": b"Apache-2.0\n",
                    "package-1.0/LICENSES/CC-BY-4.0.txt": b"CC-BY-4.0\n",
                    "package-1.0/THIRD_PARTY_NOTICES.md": b"Yandex Cloud docs\n",
                }
                for name, data in members.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))

            report = run_check(root, [wheel, sdist])

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["archive_count"], 2)

    def test_archive_rejects_traversal_binary_members_and_missing_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            self._write_required_notices(root)
            archive_path = base / "unsafe.whl"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "escape\n")
                archive.writestr("package/export.sqlite", b"SQLite format 3\x00")
                archive.writestr("package/LICENSE", "Apache-2.0\n")

            report = run_check(root, [archive_path])

        categories = {issue["category"] for issue in report["issues"]}
        self.assertIn("archive_path", categories)
        self.assertIn("unsafe_file_type", categories)
        self.assertIn("archive_missing_notice", categories)

    def test_placeholder_credentials_and_project_schema_ids_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)
            (root / "fixture.py").write_text(
                "authorization = 'Bearer fixtureTokenValue12345'\n"
                "schema = 'https://schemas.local/project/example.schema.json'\n"
                "contact = 'tester@example.test'\n",
                encoding="utf-8",
            )

            report = run_check(root)

        self.assertTrue(report["ok"], report["issues"])


if __name__ == "__main__":
    unittest.main()
