from __future__ import annotations

import tempfile
import unittest

from datalens_dev_mcp.knowledge.reference import build_reference_response
from datalens_dev_mcp.pipeline.evidence_compaction import compact_task_evidence
from datalens_dev_mcp.pipeline.investigation import ARCHITECTURE_REVIEW_STATE, start_investigation


class CompactTaskContextTests(unittest.TestCase):
    def test_three_failed_corrections_require_architecture_review(self):
        record = start_investigation("route invalid", operation="compile")
        for index in range(3):
            record.record_attempt(
                hypothesis=f"hypothesis {index}",
                probe=f"probe {index}",
                evidence=f"evidence {index}",
            )
        self.assertEqual(record.state, ARCHITECTURE_REVIEW_STATE)
        self.assertFalse(record.can_attempt_fix)
        self.assertEqual(record.corrective_attempts, 3)

    def test_unchanged_evidence_does_not_churn_stable_hash(self):
        common = {
            "policy_version": "1",
            "task_contract": {"task_id": "synthetic"},
            "target_binding": {"dashboard_id": "dashboard"},
            "style_binding": {},
            "last_state_change": {"state": "READ"},
        }
        first = compact_task_evidence(
            **common,
            checkpoint={"current_state": "READ", "polled_at": "first"},
            next_transition="READ -> VALIDATE",
        )
        second = compact_task_evidence(
            **common,
            checkpoint={"current_state": "READ", "polled_at": "second"},
            next_transition="READ -> VALIDATE",
        )
        self.assertEqual(first["stable_context_sha256"], second["stable_context_sha256"])

    def test_heavy_evidence_spills_with_uri_hash_and_synopsis(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = compact_task_evidence(
                policy_version="1",
                task_contract={"scope": "x" * 5000},
                target_binding={},
                style_binding={},
                checkpoint={"current_state": "READ"},
                artifact_root=tmp,
                inline_char_budget=1000,
            )
        pointer = result["full_evidence"]
        self.assertIn("uri", pointer)
        self.assertEqual(len(pointer["sha256"]), 64)
        self.assertEqual(pointer["synopsis"]["state"], "READ")

    def test_reference_retrieval_is_bounded_to_three_fragments(self):
        result = build_reference_response(mode="search", query="chart", limit=10, max_chars=12000)
        self.assertLessEqual(len(result.get("results") or []), 3)
        self.assertEqual(result["retrieval_contract"]["max_inline_fragments"], 3)
