import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROFILE_SCRIPT = ROOT / "scripts" / "run_acceptance_profile.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ValidationProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_module(PROFILE_SCRIPT, "run_acceptance_profile")

    def test_quick_profile_covers_fast_static_smoke_and_focused_units(self):
        steps = self.profiles.profile_steps("quick")
        names = {step["name"] for step in steps}

        self.assertIn("lint_local", names)
        self.assertIn("schema_validation", names)
        self.assertIn("runtime_resource_manifest", names)
        self.assertIn("stdio_smoke", names)
        self.assertIn("api_contract_policy", names)
        self.assertIn("public_release_surface", names)
        self.assertIn("focused_unit_subset", names)

    def test_standard_profile_is_clean_tree_safe_successor_without_duplicate_focused_subset(self):
        steps = self.profiles.profile_steps("standard")
        names = [step["name"] for step in steps]

        self.assertIn("unit_tests", names)
        self.assertIn("integration_offline_tests", names)
        self.assertIn("repo_size_budget", names)
        self.assertIn("sensitive_artifact_scan", names)
        self.assertNotIn("focused_unit_subset", names)

    def test_full_profile_includes_release_weight_evidence_steps(self):
        steps = self.profiles.profile_steps("full")
        names = {step["name"] for step in steps}

        self.assertIn("package_wheel_build", names)
        self.assertIn("portable_wheel_smoke", names)
        self.assertIn("golden_runtime_gallery_fixtures", names)
        self.assertIn("controlled_live_proof", names)

    def test_smoke_script_reports_timings(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "smoke_mcp_stdio.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = __import__("json").loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["duration_ms"], 0)
        self.assertIn("total_ms", payload["timings"])


if __name__ == "__main__":
    unittest.main()
