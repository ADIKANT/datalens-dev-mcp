import unittest
import re
from pathlib import Path

from datalens_dev_mcp.mcp.prompts import PROMPTS


ROOT = Path(__file__).resolve().parents[2]


class InstructionModelTests(unittest.TestCase):
    def test_instruction_model_docs_exist_and_list_canonical_principles(self):
        model = ROOT / "docs" / "architecture" / "runtime_instruction_model.md"
        testing = ROOT / "docs" / "testing.md"
        model_text = model.read_text(encoding="utf-8")
        testing_text = testing.read_text(encoding="utf-8")

        for phrase in (
            "templates-first",
            "no removed chart routes",
            "Wizard path is separate",
            "do not invent Advanced Editor methods",
            "style tokens",
            "persistent Markdown requirements",
            "no legacy cache sync",
        ):
            self.assertIn(phrase, model_text)
        for phrase in (
            "python3 scripts/run_offline_acceptance.py",
            "autonomous-v2",
            "save-only",
            "confirm_delete",
        ):
            self.assertIn(phrase, testing_text)

    def test_runtime_prompts_use_compact_shared_directive(self):
        for name, prompt in PROMPTS.items():
            text = prompt["text"]
            self.assertLess(len(text), 900, name)
            self.assertIn("templates-first", text, name)
            self.assertIn("acceptance_criteria", text, name)
            self.assertIn("no legacy cache sync", text, name)

    def test_task_prompt_only_names_autonomous_tools(self):
        from datalens_dev_mcp.server import AUTONOMOUS_TOOL_NAMES

        from datalens_dev_mcp.mcp.prompts import AUTONOMOUS_PROMPTS

        named_tools = set(re.findall(r"\bdl_[a-z0-9_]+\b", AUTONOMOUS_PROMPTS["datalens.task"]["text"]))
        self.assertTrue(named_tools)
        self.assertLessEqual(named_tools, AUTONOMOUS_TOOL_NAMES)


if __name__ == "__main__":
    unittest.main()
