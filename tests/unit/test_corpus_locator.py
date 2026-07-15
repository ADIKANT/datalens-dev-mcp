import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.knowledge import corpus


class CorpusLocatorTests(unittest.TestCase):
    def test_priority_is_explicit_then_env_then_repo_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = self._corpus(root / "explicit")
            env = self._corpus(root / "env")
            repo = self._corpus(root / "repo")
            required = ("marker",)

            with (
                patch.dict(os.environ, {"DATALENS_DOCS_CORPUS_ROOT": str(env)}),
                patch.object(corpus, "REPO_CORPUS_ROOT", repo),
            ):
                self.assertEqual(corpus.resolve_corpus_root(explicit, required_files=required), explicit)
                self.assertEqual(corpus.resolve_corpus_root(required_files=required), env)
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(corpus.resolve_corpus_root(required_files=required), repo)

    def test_explicit_invalid_root_never_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "invalid"
            env = self._corpus(root / "env")
            repo = self._corpus(root / "repo")

            with (
                patch.dict(os.environ, {"DATALENS_DOCS_CORPUS_ROOT": str(env)}),
                patch.object(corpus, "REPO_CORPUS_ROOT", repo),
            ):
                with self.assertRaises(FileNotFoundError) as raised:
                    corpus.resolve_corpus_root(invalid, required_files=("marker",))

            self.assertIn(str(invalid), str(raised.exception))
            self.assertNotIn(str(env), str(raised.exception))

    @staticmethod
    def _corpus(path: Path) -> Path:
        path.mkdir(parents=True)
        (path / "marker").write_text("ok\n", encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
