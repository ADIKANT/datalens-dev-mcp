from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


class ExistingEffectVerificationTests(unittest.TestCase):
    def test_discovery_does_not_reparse_raw_request_for_missing_typed_target(self):
        from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService

        class Client:
            def rpc_readonly(self, method, params):
                raise AssertionError(f"provider must not be called: {method} {params}")

        contract = {
            "mode": "review",
            "operation_kind": "verify_existing_effect",
            "target": {},
            "effect": {"kind": "published"},
            "verification": {"required_live_reads": ["current_object"]},
        }
        result = TargetDiscoveryService(Client()).discover(
            contract,
            request_text="Проверь https://datalens.ru/dashboards/raw_text_only_target",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["missing_facts"], ["dashboard_id"])

    def _journal(self, root: Path):
        return SimpleNamespace(
            root=root,
            task_id="synthetic-task",
            target_binding_path=root / "bindings" / "target.json",
            target_graph_path=root / "bindings" / "graph.json",
            discovery_path=root / "bindings" / "discovery.json",
        )

    def _write_live_evidence(self, journal) -> None:
        from datalens_dev_mcp.pipeline.artifacts import write_json

        write_json(
            journal.target_binding_path,
            {
                "source": "live_discovery",
                "binding_hash": "a" * 64,
                "dashboard_id": "synthetic_dashboard",
            },
        )
        write_json(
            journal.target_graph_path,
            {
                "graph_hash": "b" * 64,
                "nodes": [
                    {
                        "object_id": "synthetic_dashboard",
                        "saved_revision": "synthetic_revision",
                        "published_revision": "synthetic_revision",
                    }
                ],
                "edges": [],
            },
        )
        write_json(
            journal.discovery_path,
            {
                "provider_calls": [
                    {"method": "getDashboard", "effect": "read", "status": "success"}
                ]
            },
        )

    def test_published_effect_is_verified_from_reads_with_zero_mutation(self):
        from datalens_dev_mcp.pipeline.existing_effect_verification import ExistingEffectVerificationService

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self._journal(root)
            self._write_live_evidence(journal)
            contract = {
                "contract_hash": "c" * 64,
                "operation_kind": "verify_existing_effect",
                "effect": {"kind": "published", "expected_state": "published_revision_matches_saved"},
                "verification": {
                    "required_live_reads": ["current_object", "saved_or_published_revision", "relations"]
                },
                "acceptance": [{"kind": "existing_effect", "statement": "published", "hard": True}],
            }

            receipt = ExistingEffectVerificationService(journal, contract).execute()

            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["outcome"], "verified")
            self.assertEqual(receipt["missing_live_reads"], [])
            self.assertEqual(receipt["write_attempted"], 0)
            self.assertEqual(receipt["write_executed"], 0)

    def test_generic_changed_effect_is_honestly_indeterminate(self):
        from datalens_dev_mcp.pipeline.existing_effect_verification import ExistingEffectVerificationService

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self._journal(root)
            self._write_live_evidence(journal)
            contract = {
                "contract_hash": "c" * 64,
                "operation_kind": "verify_existing_effect",
                "effect": {"kind": "changed", "expected_state": "requested_semantic_effect_observed"},
                "verification": {
                    "required_live_reads": [
                        "current_object", "saved_or_published_revision", "relations", "runtime_assertions_if_applicable"
                    ]
                },
                "acceptance": [{"kind": "existing_effect", "statement": "changed", "hard": True}],
            }

            receipt = ExistingEffectVerificationService(journal, contract).execute()

            self.assertEqual(receipt["status"], "blocked")
            self.assertEqual(receipt["outcome"], "indeterminate")
            self.assertIn("runtime_assertions_if_applicable", receipt["missing_live_reads"])
            self.assertEqual(receipt["write_executed"], 0)


if __name__ == "__main__":
    unittest.main()
