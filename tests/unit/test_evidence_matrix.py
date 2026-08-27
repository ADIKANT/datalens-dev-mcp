import json
import unittest
from pathlib import Path

from datalens_dev_mcp.pipeline.evidence_matrix import (
    browser_policy_from_legacy_flag,
    build_evidence_matrix,
)
from datalens_dev_mcp.pipeline.proof_claims import build_proof_claim, highest_honest_proof_level
from datalens_dev_mcp.pipeline.proof_levels import PROOF_LEVELS


class EvidenceMatrixTests(unittest.TestCase):
    def test_source_label_change_needs_static_data_and_saved_readback_not_browser(self):
        matrix = build_evidence_matrix(
            change_class="source_labels_only",
            browser_policy={"mode": "optional", "source": "compiled_default"},
            evidence={"static": True, "data": True, "saved": True},
        )
        self.assertTrue(matrix["can_publish"])
        self.assertFalse(matrix["should_call_browser"])
        self.assertNotIn("browser_attestation", matrix["required_evidence"])

    def test_required_visual_change_blocks_without_fresh_browser_attestation(self):
        matrix = build_evidence_matrix(
            change_class="renderer_logic",
            browser_policy={"mode": "required", "source": "explicit_user"},
            evidence={"static": True, "contract_harness": True, "saved": True},
        )
        self.assertFalse(matrix["can_publish"])
        self.assertTrue(matrix["should_call_browser"])
        self.assertEqual(matrix["missing_evidence"], ["browser_attestation"])

    def test_selector_behavior_requires_contract_harness_even_when_browser_forbidden(self):
        matrix = build_evidence_matrix(
            change_class="selector_behavior",
            browser_policy={"mode": "forbidden", "source": "explicit_user"},
            evidence={"static": True, "data": True, "saved": True},
        )
        self.assertFalse(matrix["can_publish"])
        self.assertFalse(matrix["browser_adapter_allowed"])
        self.assertEqual(matrix["missing_evidence"], ["contract_harness"])

    def test_default_is_change_aware_not_literal_true(self):
        data_policy = browser_policy_from_legacy_flag(None, maintenance_mode="dataset_sql_patch")
        visual_policy = browser_policy_from_legacy_flag(None, maintenance_mode="quick_visible_patch")
        self.assertEqual(data_policy["mode"], "optional")
        self.assertEqual(visual_policy["mode"], "required")

    def test_contract_claim_cannot_be_promoted_to_browser_rendered(self):
        contract = {"schema_id": "render_contract_result", "ok": True, "status": "passed"}
        honest = build_proof_claim(claim="runtime contract holds", proof_level="contract_runtime", evidence=contract)
        false_visual = build_proof_claim(claim="pixel render passed", proof_level="browser_rendered", evidence=contract)
        self.assertTrue(honest["ok"])
        self.assertFalse(false_visual["ok"])
        self.assertEqual(highest_honest_proof_level([honest, false_visual]), "contract_runtime")

    def test_proof_vocabulary_is_unified_in_code_schema_and_docs(self):
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "schemas" / "proof-claim.schema.json").read_text(encoding="utf-8"))
        documented = (root / "docs" / "evidence-levels.md").read_text(encoding="utf-8")
        self.assertEqual(tuple(schema["properties"]["proof_level"]["enum"]), PROOF_LEVELS)
        for level in PROOF_LEVELS:
            self.assertIn(f"`{level}`", documented)
        self.assertIn("are not proof levels", documented)


if __name__ == "__main__":
    unittest.main()
