import tempfile
import unittest
import zipfile
from pathlib import Path


class SecurityScannerTests(unittest.TestCase):
    def test_runtime_scanner_allows_workspace_paths_and_ids_but_detects_tokens(self):
        from datalens_dev_mcp.validators.security_validator import scan_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_value = "y0_" + "syntheticsecretvalue000000000"
            workspace_path = "/workspace/sample-dashboard"
            synthetic_identifier = "demo123" + "example456"
            (root / "workspace_context.md").write_text(
                f"{workspace_path}\nworkbook id {synthetic_identifier}\n",
                encoding="utf-8",
            )
            (root / "bad.md").write_text(
                f"token {token_value}",
                encoding="utf-8",
            )

            result = scan_path(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("token" in issue.lower() for issue in result.issues))
        self.assertFalse(any("private path" in issue.lower() for issue in result.issues))
        self.assertFalse(any("identifier" in issue.lower() for issue in result.issues))

    def test_detects_auth_headers_and_private_keys(self):
        from datalens_dev_mcp.validators.security_validator import scan_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bearer = "Bearer " + "abcdefghijklmnopqrstuvwxyz123456"
            private_key_begin = "-----BEGIN " + "PRIVATE KEY-----"
            (root / "bad.md").write_text(
                f"Authorization: {bearer}\n"
                f"{private_key_begin}\n",
                encoding="utf-8",
            )

            result = scan_path(root)

        self.assertFalse(result.ok)
        self.assertGreaterEqual(len(result.issues), 2)

    def test_detects_api_keys_dsns_and_forbidden_archive_members(self):
        from datalens_dev_mcp.validators.security_validator import scan_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            header_value = "abcdefghijklmnopqrstuvwxyz" + "123456"
            dsn = "postgres://user:" + "password1234567890" + "@db.example.local/app"
            (root / "bad.txt").write_text(
                f"X-Api-Key: {header_value}\n"
                f"dsn={dsn}\n",
                encoding="utf-8",
            )
            with zipfile.ZipFile(root / "bad.whl", "w") as archive:
                archive.writestr("datalens_dev_mcp/assets/config/datalens_mcp.local.json", "{}")

            result = scan_path(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("token or secret-like value" in issue for issue in result.issues))
        self.assertTrue(any("forbidden local config packaged" in issue for issue in result.issues))

    def test_allows_public_dashboard_terms_and_code_variables(self):
        from datalens_dev_mcp.validators.security_validator import scan_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public.md").write_text(
                "# Dashboard Requirements Intake\n"
                "Use saved-branch reads before dashboard implementation and readback.\n"
                "`dashboard_plan.md` and `ChartDecision` are public contract names.\n",
                encoding="utf-8",
            )
            (root / "auth.py").write_text(
                "token = result.stdout.strip()\n"
                "output.append(f'DATALENS_IAM_TOKEN={token}')\n",
                encoding="utf-8",
            )

            result = scan_path(root)

        self.assertTrue(result.ok, result.issues)

    def test_ignored_build_artifacts_are_not_scanned_but_committed_docs_are(self):
        from datalens_dev_mcp.validators.security_validator import scan_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build" / "generated").mkdir(parents=True)
            (root / "docs").mkdir()
            token_value = "y0_" + "syntheticsecretvalue000000000"
            (root / "build" / "generated" / "draft.md").write_text(
                f"token {token_value}",
                encoding="utf-8",
            )
            (root / "docs" / "bad.md").write_text(
                f"token {token_value}",
                encoding="utf-8",
            )

            result = scan_path(root)

        self.assertFalse(result.ok)
        self.assertEqual(len(result.issues), 1)
        self.assertIn("docs/bad.md", result.issues[0])


if __name__ == "__main__":
    unittest.main()
