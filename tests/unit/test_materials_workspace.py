import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MaterialsWorkspaceTests(unittest.TestCase):
    def test_private_material_and_internal_report_roots_are_ignored_and_untracked(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("/materials/", "/docs/reports/", "/artifacts/"):
            self.assertIn(pattern, gitignore)

        tracked = subprocess.check_output(
            ["git", "ls-files", "--", "materials", "docs/reports"],
            cwd=ROOT,
            text=True,
        )
        self.assertEqual("", tracked.strip())

    def test_public_policies_define_source_and_runtime_boundary(self):
        policy = " ".join((ROOT / "docs" / "materials_policy.md").read_text(encoding="utf-8").split())
        provenance = " ".join((ROOT / "docs" / "source_provenance.md").read_text(encoding="utf-8").split())
        sanitization = " ".join(
            (ROOT / "docs" / "security" / "sanitization_policy.md").read_text(encoding="utf-8").split()
        )

        self.assertIn("public repository is an executable toolkit, not a document archive", policy)
        self.assertIn("third-party books, paid courses", policy)
        self.assertIn("external build input", policy)
        self.assertIn("never required at runtime", policy)
        self.assertIn("Полный корпус документации используется только", provenance)
        self.assertIn("Обычная установка и работа сервера используют готовые компактные индексы", provenance)
        self.assertIn("must not depend on ignored materials at runtime", sanitization)


if __name__ == "__main__":
    unittest.main()
