from __future__ import annotations

import re
import unittest
from pathlib import Path

from datalens_dev_mcp.server import STANDARD_TOOL_NAMES, TOOLS


ROOT = Path(__file__).resolve().parents[2]
TOOL_ROW_RE = re.compile(r"^\|\s*`(dl_[a-z0-9_]+)`\s*\|", re.MULTILINE)
TOOL_NAME_RE = re.compile(r"\bdl_[a-z0-9_]+\b")


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

    def test_hidden_tools_are_not_presented_as_public_rows(self):
        hidden = set(TOOLS) - STANDARD_TOOL_NAMES
        for rel in ("docs/tools.md", "docs/tools_en.md"):
            rows = set(TOOL_ROW_RE.findall((ROOT / rel).read_text(encoding="utf-8")))
            self.assertFalse(rows & hidden, rel)

    def test_public_workflow_docs_name_only_standard_tools(self):
        workflow_docs = (
            "docs/getting-started.md",
            "docs/one-prompt-workflow.md",
            "docs/project_workflow.md",
            "docs/usage-flow.md",
            "docs/usage-flow_en.md",
            "docs/codex_setup.md",
            "docs/codex_setup_en.md",
        )
        for rel in workflow_docs:
            named = set(TOOL_NAME_RE.findall((ROOT / rel).read_text(encoding="utf-8")))
            self.assertLessEqual(named, STANDARD_TOOL_NAMES, f"{rel}: {sorted(named - STANDARD_TOOL_NAMES)}")

    def test_bilingual_public_guides_keep_section_parity(self):
        pairs = (
            ("docs/tools.md", "docs/tools_en.md"),
            ("docs/usage-flow.md", "docs/usage-flow_en.md"),
            ("docs/sources.md", "docs/sources_en.md"),
            ("docs/codex_setup.md", "docs/codex_setup_en.md"),
        )
        for russian_rel, english_rel in pairs:
            russian = (ROOT / russian_rel).read_text(encoding="utf-8")
            english = (ROOT / english_rel).read_text(encoding="utf-8")
            self.assertEqual(russian.count("\n## "), english.count("\n## "), (russian_rel, english_rel))


if __name__ == "__main__":
    unittest.main()
