import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = Path(
    os.environ.get(
        "DATALENS_DOCS_CORPUS_ROOT",
        ROOT / ".external" / "datalens-docs-corpus",
    )
).expanduser()
COMPILER = ROOT / "scripts" / "reconcile_datalens_api.py"


def copy_minimal_corpus(target: Path) -> None:
    for rel in [
        "raw/api/openapi.json",
        "api_inventory.json",
        "reports/content_hashes.json",
        "reports/validation.md",
        "raw/md/datalens/charts/editor/methods.md",
        "raw/md/datalens/charts/editor/widgets/advanced.md",
    ]:
        source = CORPUS_ROOT / rel
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


class AuthoritativeDocsCompilerTests(unittest.TestCase):
    def setUp(self):
        if not CORPUS_ROOT.is_dir():
            self.skipTest("external DataLens docs corpus is not available")

    def test_committed_compiler_outputs_match_supplied_corpus(self):
        result = subprocess.run(
            [sys.executable, str(COMPILER), "--check", "--corpus-root", str(CORPUS_ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_openapi_lock_and_schema_bundle_are_closed(self):
        lock = json.loads((ROOT / "schemas" / "datalens-api" / "openapi.lock.json").read_text(encoding="utf-8"))
        bundle = json.loads((ROOT / "schemas" / "datalens-api" / "closed-schema-bundle.json").read_text(encoding="utf-8"))
        index = json.loads((ROOT / "schemas" / "datalens-api" / "operation-schema-index.json").read_text(encoding="utf-8"))

        self.assertEqual(lock["operation_count"], 88)
        self.assertEqual(lock["component_schema_count"], 483)
        self.assertEqual(lock["closed_schema_count"], 510)
        self.assertEqual(lock["required_api_header_version"], "2")
        self.assertEqual(lock["path_count"], 88)
        self.assertEqual(lock["inventory_path_count"], 88)
        self.assertEqual(bundle["schema_count"], 510)
        self.assertEqual(bundle["missing_refs"], [])
        self.assertEqual(index["updateDataset"]["request_schema_ref"], "UpdateDatasetRequest")
        self.assertEqual(index["validateDataset"]["request_schema_ref"], "ValidateDatasetRequest")
        self.assertEqual(index["updateConnection"]["request_schema_ref"], "UpdateConnectionRequest")
        for schema_name in ("DatasetUpdate", "DatasetValidate", "ConnectionUpdate", "EntryLocationIdentifiers"):
            self.assertIn(schema_name, bundle["schemas"])

    def test_editor_allowlist_comes_from_normalized_docs(self):
        allowlist = json.loads(
            (ROOT / "schemas" / "datalens-api" / "editor-runtime-allowlist.json").read_text(encoding="utf-8")
        )

        self.assertIn("setRawData", allowlist["methods"])
        self.assertIn("marker", allowlist["html_tags"])
        self.assertIn("data-id", allowlist["html_attributes"])
        self.assertIn("data-tooltip-content", allowlist["html_attributes"])
        self.assertNotIn("rel", allowlist["html_attributes"])
        self.assertNotIn("marker-end", allowlist["html_attributes"])

    def test_changed_and_missing_corpus_are_reported_as_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed"
            copy_minimal_corpus(changed)
            content_hashes_path = changed / "reports" / "content_hashes.json"
            content_hashes = json.loads(content_hashes_path.read_text(encoding="utf-8"))
            content_hashes["api_content_hash"] = "changed-content-hash"
            content_hashes_path.write_text(json.dumps(content_hashes, ensure_ascii=False), encoding="utf-8")

            drift = subprocess.run(
                [sys.executable, str(COMPILER), "--check", "--corpus-root", str(changed)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            missing = subprocess.run(
                [sys.executable, str(COMPILER), "--check", "--corpus-root", str(Path(tmp) / "missing")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(drift.returncode, 1, drift.stderr + drift.stdout)
        self.assertIn("changed schemas/datalens-api/openapi.lock.json", drift.stdout)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("missing corpus inputs", missing.stderr)

    def test_operation_inventory_mismatch_is_a_clear_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed"
            copy_minimal_corpus(changed)
            inventory_path = changed / "api_inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["operations"] = inventory["operations"][:-1]
            inventory["stats"]["operations"] = 86
            inventory_path.write_text(json.dumps(inventory, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(COMPILER), "--check", "--corpus-root", str(changed)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("OpenAPI operation inventory blocker", result.stderr)
        self.assertIn("inventory operations=87 expected 88", result.stderr)


if __name__ == "__main__":
    unittest.main()
