from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("acceptance_shards", ROOT / "scripts" / "acceptance_shards.py")
assert SPEC and SPEC.loader
acceptance_shards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance_shards)


class AcceptanceSurfacePolicyTests(unittest.TestCase):
    def test_surface_is_required_and_autonomy_is_never_legacy(self) -> None:
        with self.assertRaisesRegex(TypeError, "surface"):
            acceptance_shards.run_acceptance("autonomy", [])
        with self.assertRaisesRegex(ValueError, "must declare autonomous-v2"):
            acceptance_shards.run_acceptance("autonomy", [], surface="legacy-v1")

    def test_shard_cannot_override_declared_surface(self) -> None:
        shard = {"name": "bad", "command": ["true"], "env": {"DATALENS_MCP_TOOL_SURFACE": "legacy-v1"}}
        with self.assertRaisesRegex(ValueError, "overrides"):
            acceptance_shards.run_acceptance("autonomy", [shard], surface="autonomous-v2")

    def test_receipt_records_exact_effective_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = acceptance_shards.run_acceptance(
                "policy-test",
                [{"name": "pass", "command": ["true"]}],
                surface="autonomous-v2",
                output=Path(tmp) / "receipt.json",
            )
        self.assertTrue(report["ok"])
        self.assertEqual(report["declared_surface"], "autonomous-v2")
        self.assertEqual(report["effective_surface"], "autonomous-v2")
        self.assertTrue(report["surface_consistent"])


if __name__ == "__main__":
    unittest.main()
