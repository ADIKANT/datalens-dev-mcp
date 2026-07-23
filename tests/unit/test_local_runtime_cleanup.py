import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def load_script_module(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class LocalRuntimeCleanupTests(unittest.TestCase):
    def test_cleanup_removes_safe_garbage_without_deleting_external_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external_input = root / ".external" / "input" / "source.json"
            external_input.parent.mkdir(parents=True)
            external_input.write_text("{}", encoding="utf-8")
            (root / ".DS_Store").write_text("finder", encoding="utf-8")
            (external_input.parent / ".DS_Store").write_text("finder", encoding="utf-8")
            cache_dir = root / "src" / "__pycache__"
            cache_dir.mkdir(parents=True)
            (cache_dir / "module.cpython-312.pyc").write_bytes(b"bytecode")
            (root / ".pytest_cache").mkdir()
            (root / ".ruff_cache").mkdir()

            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clean_local_runtime_artifacts.py"), "--root", str(root)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(external_input.exists())
            self.assertFalse((root / ".DS_Store").exists())
            self.assertFalse((external_input.parent / ".DS_Store").exists())
            self.assertFalse(cache_dir.exists())
            self.assertFalse((root / ".pytest_cache").exists())
            self.assertFalse((root / ".ruff_cache").exists())

    def test_runtime_export_archive_excludes_local_and_generated_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "server.py").write_text("print('runtime')\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "README.md").write_text("docs\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("git\n", encoding="utf-8")
            (root / "build").mkdir()
            (root / "build" / "generated.py").write_text("generated\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            (root / "artifacts" / "sql_performance").mkdir(parents=True)
            (root / "artifacts" / "sql_performance" / "run.json").write_text("{}", encoding="utf-8")
            generated = root / "artifacts" / "validation"
            generated.mkdir(parents=True)
            (generated / "report.json").write_text("{}", encoding="utf-8")
            (root / ".metadata-fetch" / "raw").mkdir(parents=True)
            (root / ".metadata-fetch" / "raw" / "evidence.json").write_text("{}", encoding="utf-8")
            (root / "memory-bank" / ".transactions").mkdir(parents=True)
            (root / "memory-bank" / ".transactions" / "tx.json").write_text("{}", encoding="utf-8")
            (root / "datalens_mapping").mkdir()
            (root / "datalens_mapping" / "live.json").write_text("{}", encoding="utf-8")
            (root / "RUN_STATE.md").write_text("local state\n", encoding="utf-8")
            output = root / "runtime.zip"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "export_clean_archive.py"),
                    "--root",
                    str(root),
                    "--output",
                    str(output),
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("datalens-dev-mcp/src/server.py", names)
            self.assertIn("datalens-dev-mcp/docs/README.md", names)
            self.assertNotIn("datalens-dev-mcp/.git/config", names)
            self.assertNotIn("datalens-dev-mcp/build/generated.py", names)
            self.assertNotIn("datalens-dev-mcp/.env", names)
            self.assertNotIn("datalens-dev-mcp/artifacts/sql_performance/run.json", names)
            self.assertNotIn("datalens-dev-mcp/artifacts/validation/report.json", names)
            self.assertNotIn("datalens-dev-mcp/.metadata-fetch/raw/evidence.json", names)
            self.assertNotIn("datalens-dev-mcp/memory-bank/.transactions/tx.json", names)
            self.assertNotIn("datalens-dev-mcp/datalens_mapping/live.json", names)
            self.assertNotIn("datalens-dev-mcp/RUN_STATE.md", names)

    def test_runtime_export_exclusions_cover_public_release_forbidden_paths(self):
        exporter = load_script_module("export_clean_archive")
        release_gate = load_script_module("check_public_release")

        self.assertLessEqual(set(release_gate.FORBIDDEN_TOP_LEVEL), set(exporter.EXCLUDED_PREFIXES))
        self.assertLessEqual(
            {"/".join(parts) for parts in release_gate.FORBIDDEN_PATH_PREFIXES},
            set(exporter.EXCLUDED_PREFIXES),
        )
        covered_root_files = {
            *exporter.LOCAL_SECRET_FILES,
            *exporter.EXCLUDED_ROOT_FILES,
        }
        self.assertLessEqual(set(release_gate.FORBIDDEN_ROOT_FILES), {item.lower() for item in covered_root_files})


if __name__ == "__main__":
    unittest.main()
