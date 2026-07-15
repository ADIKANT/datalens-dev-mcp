import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_runtime_asset_sync.py"


def load_sync_module():
    spec = importlib.util.spec_from_file_location("check_runtime_asset_sync", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class RuntimeAssetSyncTests(unittest.TestCase):
    def test_runtime_asset_sync_checker_passes(self):
        checker = load_sync_module()
        report = checker.check_sync()

        self.assertTrue(report["ok"], report)
        self.assertGreater(report["checked_pair_count"], 200)
        self.assertEqual(report["missing_assets"], [])
        self.assertEqual(report["hash_mismatches"], [])
        self.assertEqual(report["raw_assets"], [])

    def test_runtime_resource_manifest_check_passes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_runtime_resource_manifest.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
