from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from datalens_dev_mcp.server import STANDARD_TOOL_NAMES, list_tools


ROOT = Path(__file__).resolve().parents[2]
TOOL_ROW_RE = re.compile(r"^\|\s*`(dl_[a-z0-9_]+)`\s*\|", re.MULTILINE)
TOOL_NAME_RE = re.compile(r"\bdl_[a-z0-9_]+\b")
PUBLIC_SUFFIXES = {".md", ".json", ".toml", ".yaml", ".yml"}


def public_text_files() -> list[Path]:
    files = [
        ROOT / "README.md",
        ROOT / "README_en.md",
        ROOT / "AGENTS.md",
        ROOT / "SECURITY.md",
        ROOT / "THIRD_PARTY_NOTICES.md",
    ]
    for directory in (ROOT / "docs", ROOT / "examples", ROOT / "templates"):
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.casefold() in PUBLIC_SUFFIXES
        )
    return sorted(set(files))


class PublicToolGuideTests(unittest.TestCase):
    def test_bilingual_guides_cover_exact_standard_surface(self):
        for rel in ("docs/tools.md", "docs/tools_en.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            rows = TOOL_ROW_RE.findall(text)
            self.assertEqual(len(rows), 38, rel)
            self.assertEqual(len(rows), len(set(rows)), rel)
            self.assertEqual(set(rows), STANDARD_TOOL_NAMES, rel)
            table_rows = [line for line in text.splitlines() if TOOL_ROW_RE.match(line)]
            self.assertTrue(all(line.count("|") == 7 for line in table_rows), rel)

    def test_public_schema_is_exact_and_has_no_approval_fields(self):
        tools = list_tools()
        self.assertEqual(len(tools), 38)
        self.assertEqual({tool["name"] for tool in tools}, STANDARD_TOOL_NAMES)
        forbidden = {"approved", "approval_source", "approved_plan_path", "approve_guid_changes"}
        for tool in tools:
            properties = set(tool["inputSchema"].get("properties") or {})
            self.assertFalse(properties & forbidden, (tool["name"], sorted(properties & forbidden)))
        rendered = json.dumps(tools, ensure_ascii=False).casefold()
        self.assertNotIn("approval", rendered)
        self.assertNotIn("approved", rendered)

    def test_all_public_content_names_only_standard_tools(self):
        failures: list[str] = []
        for path in public_text_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            unknown = sorted(set(TOOL_NAME_RE.findall(text)) - STANDARD_TOOL_NAMES)
            if unknown:
                failures.append(f"{path.relative_to(ROOT)}: {', '.join(unknown)}")
        self.assertFalse(failures, "\n".join(failures))

    def test_bilingual_public_guides_keep_section_parity(self):
        pairs = (
            ("README.md", "README_en.md"),
            ("docs/README.md", "docs/README_en.md"),
            ("docs/access.md", "docs/access_en.md"),
            ("docs/tools.md", "docs/tools_en.md"),
            ("docs/usage-flow.md", "docs/usage-flow_en.md"),
            ("docs/sources.md", "docs/sources_en.md"),
            ("docs/codex_setup.md", "docs/codex_setup_en.md"),
            ("docs/configuration.md", "docs/configuration_en.md"),
            ("docs/local-only-safety-model.md", "docs/local-only-safety-model_en.md"),
            ("docs/route-policy.md", "docs/route-policy_en.md"),
            ("docs/safe-apply.md", "docs/safe-apply_en.md"),
        )
        for russian_rel, english_rel in pairs:
            russian = (ROOT / russian_rel).read_text(encoding="utf-8")
            english = (ROOT / english_rel).read_text(encoding="utf-8")
            self.assertEqual(russian.count("\n## "), english.count("\n## "), (russian_rel, english_rel))

    def test_obsolete_onboarding_duplicates_are_removed(self):
        obsolete = (
            "docs/datalens-auth.md",
            "docs/datalens/api_start_auth.md",
            "docs/mcp-configuration.md",
            "docs/getting-started.md",
            "docs/getting_started_local.md",
        )
        self.assertFalse([rel for rel in obsolete if (ROOT / rel).exists()])


if __name__ == "__main__":
    unittest.main()
