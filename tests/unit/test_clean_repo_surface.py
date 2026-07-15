import unittest
from pathlib import Path

from datalens_dev_mcp.server import list_prompts, list_resources, list_tools


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_SURFACES = (
    "dl_list_corpus_items",
    "dl_read_corpus_item",
    "dl_search_corpus",
    "dl_get_skill_context",
    "dl_compare_codex_plugins_parity",
    "dl_route_capability",
    "dl_list_migrated_helpers",
    "datalens.parity_audit",
    "datalens://codex-plugins",
    "datalens://parity",
)


class CleanRepoSurfaceTests(unittest.TestCase):
    def test_no_legacy_corpus_or_parity_mcp_surface_is_registered(self):
        payload = "\n".join(
            [
                *(tool["name"] for tool in list_tools()),
                *(tool["description"] for tool in list_tools()),
                *(prompt["name"] for prompt in list_prompts()),
                *(resource["uri"] for resource in list_resources()),
            ]
        )
        for forbidden in FORBIDDEN_SURFACES:
            self.assertNotIn(forbidden, payload)

    def test_legacy_directories_are_absent(self):
        for rel in [
            "docs/corpus",
            "src/datalens_dev_mcp/private_corpus",
            "src/datalens_dev_mcp/migrated",
            "examples/migrated",
            "templates/migrated",
        ]:
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_local_garbage_files_are_absent(self):
        problems = []
        for rel in subprocess_check_output(["git", "ls-files"]).splitlines():
            path = ROOT / rel
            if path.name in {".DS_Store", "Pasted text.txt", "__MACOSX", "__pycache__"}:
                problems.append(rel)
            elif path.is_file() and path.suffix == ".pyc":
                problems.append(rel)
        self.assertEqual(problems, [])

    def test_stale_extraction_surfaces_are_absent(self):
        for rel in [
            "scripts/materials_pipeline.py",
            "scripts/build_next_iteration_artifacts.py",
            "docs/reports/materials_preflight_coverage.md",
            "docs/reports/materials_usage_matrix.md",
            "docs/reports/materials_coverage_gate.md",
            "docs/reports/clean_repo_inventory.md",
        ]:
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_user_facing_startup_docs_have_no_legacy_surface_terms(self):
        docs = [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "README_ru.md",
            ROOT / "docs" / "local-only-safety-model.md",
            ROOT / "docs" / "widget-conversion-wizard-to-js.md",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in docs)
        for forbidden in (
            "private-only",
            "public release package",
            "plugin mirror",
            "migration archive",
            "codex-plugins",
            "plugin cache",
            "source_plugin",
            "private-corpus",
        ):
            self.assertNotIn(forbidden, text)
        self.assertFalse((ROOT / "docs" / "private-only-safety-model.md").exists())
        self.assertFalse((ROOT / "docs" / "migration-wizard-to-js.md").exists())


if __name__ == "__main__":
    unittest.main()


def subprocess_check_output(command):
    import subprocess

    return subprocess.check_output(command, cwd=ROOT, text=True)
