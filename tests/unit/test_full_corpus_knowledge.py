import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.knowledge.compiler import (
    DEFAULT_CORPUS_ROOT,
    EXPECTED_COUNTS,
    INDEX_PATH,
    build_compiled_knowledge,
    check_compiled_knowledge,
    load_corpus,
    validate_corpus_counts,
)
from datalens_dev_mcp.knowledge.formulas import validate_formula_expression
from datalens_dev_mcp.knowledge.reference import build_reference_response


@unittest.skipUnless(DEFAULT_CORPUS_ROOT.is_dir(), "DataLens full corpus is not available")
class FullCorpusKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = build_compiled_knowledge(DEFAULT_CORPUS_ROOT)

    def test_baseline_reader_matches_expected_corpus_counts(self):
        report = validate_corpus_counts(load_corpus(DEFAULT_CORPUS_ROOT))

        self.assertTrue(report["ok"], report["mismatches"])
        for key, expected in EXPECTED_COUNTS.items():
            self.assertEqual(report["counts"][key], expected, key)

    def test_lock_uses_portable_corpus_root_hint(self):
        root = Path(__file__).resolve().parents[2]

        self.assertEqual(self.compiled["lock"]["corpus_root_hint"], "<DATALENS_DOCS_CORPUS_ROOT>")
        for path in (
            root / "schemas" / "datalens-knowledge" / "knowledge.lock.json",
            root
            / "src"
            / "datalens_dev_mcp"
            / "assets"
            / "schemas"
            / "datalens-knowledge"
            / "knowledge.lock.json",
        ):
            lock = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(lock["corpus_root_hint"], "<DATALENS_DOCS_CORPUS_ROOT>")

    def test_compiler_classifies_every_page_chunk_and_asset(self):
        check = check_compiled_knowledge(self.compiled)

        self.assertTrue(check["ok"], check["issues"])
        self.assertEqual(sum(check["classification_counts"].values()), EXPECTED_COUNTS["pages"])
        self.assertEqual(check["recipe_count"], 15)

    def test_formula_validator_detects_unknown_function(self):
        registry = self.compiled["formula_registry"]
        result = validate_formula_expression("UNKNOWN_FUNC([value])", registry)

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["category"], "unknown_function")

    def test_reference_response_is_bounded_and_source_traced(self):
        response = build_reference_response(mode="recipe", query="table_pivot_js", max_chars=6000)

        self.assertTrue(response["ok"])
        self.assertLessEqual(response["response_chars"], 6000)
        self.assertEqual(response["results"][0]["recipe_id"], "table_pivot_js")
        self.assertTrue(response["results"][0]["source_traces"])

    def test_check_is_write_free_and_rejects_every_writer_flag(self):
        root = Path(__file__).resolve().parents[2]
        guarded_paths = [
            INDEX_PATH,
            root / "schemas" / "datalens-knowledge" / "knowledge.lock.json",
            root
            / "src"
            / "datalens_dev_mcp"
            / "assets"
            / "schemas"
            / "datalens-knowledge"
            / "knowledge.lock.json",
        ]
        before = {
            path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in guarded_paths
            if path.is_file()
        }
        check = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "compile_datalens_knowledge.py"),
                "--corpus-root",
                str(DEFAULT_CORPUS_ROOT),
                "--check",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(check.returncode, 0, check.stderr + check.stdout)
        after = {
            path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in before
        }
        self.assertEqual(after, before)

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "must_not_exist"
            env = dict(os.environ)
            env["DATALENS_KNOWLEDGE_ARTIFACT_DIR"] = str(artifact_dir)
            for writer_flag in ("--write", "--baseline", "--reports"):
                with self.subTest(writer_flag=writer_flag):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(root / "scripts" / "compile_datalens_knowledge.py"),
                            "--corpus-root",
                            str(DEFAULT_CORPUS_ROOT),
                            "--check",
                            writer_flag,
                        ],
                        cwd=root,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertIn("--check is read-only", result.stderr)
            self.assertFalse(artifact_dir.exists())


if __name__ == "__main__":
    unittest.main()
