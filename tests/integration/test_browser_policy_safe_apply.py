import unittest
from pathlib import Path
from unittest.mock import Mock

from datalens_dev_mcp.pipeline.browser_qa import (
    execute_browser_qa_by_policy,
    validate_qa_attestation_binding,
)
from datalens_dev_mcp.pipeline.evidence_matrix import build_evidence_matrix
from datalens_dev_mcp.pipeline.runtime_gate import final_status_from_runtime_gate
from datalens_dev_mcp.pipeline.safe_apply import _qa_attestation_issues


class BrowserPolicySafeApplyIntegrationTests(unittest.TestCase):
    def test_explicit_forbidden_produces_zero_browser_calls(self):
        adapter = Mock(return_value={"ok": True, "status": "passed"})
        result = execute_browser_qa_by_policy(
            browser_policy={"mode": "forbidden", "source": "explicit_user"},
            adapter=adapter,
            plan={"target": {"dashboard_id": "synthetic"}},
        )
        adapter.assert_not_called()
        self.assertEqual(result["adapter_calls"], 0)
        self.assertFalse(result["browser_rendered"])

    def test_optional_data_only_task_completes_without_browser(self):
        matrix = build_evidence_matrix(
            change_class="source_labels_only",
            browser_policy={"mode": "optional", "source": "compiled_default"},
            evidence={"static": True, "data": True, "saved": True},
        )
        status = final_status_from_runtime_gate(
            {"status": "not_run"},
            browser_runtime_required=False,
            evidence_matrix=matrix,
        )
        self.assertEqual(status, "done")

    def test_safe_apply_uses_change_class_evidence_instead_of_unconditional_browser(self):
        action = {
            "change_class": "source_labels_only",
            "browser_policy": {"mode": "forbidden", "source": "explicit_user"},
            "proof_evidence": {"static": True, "data": True, "saved": True},
        }
        issues = _qa_attestation_issues(
            action=action,
            payload={"dashboardId": "synthetic"},
            index=0,
            attestation={"attestation_sha256": "a" * 64, "payload_set_sha256": "b" * 64},
            project_root=Path("."),
        )
        self.assertEqual(issues, [])

    def test_required_visual_task_blocks_without_attestation(self):
        action = {
            "change_class": "renderer_logic",
            "browser_policy": {"mode": "required", "source": "explicit_user"},
            "proof_evidence": {"static": True, "contract_harness": True, "saved": True},
        }
        issues = _qa_attestation_issues(
            action=action,
            payload={"dashboardId": "synthetic"},
            index=0,
            attestation={"attestation_sha256": "a" * 64, "payload_set_sha256": "b" * 64},
            project_root=Path("."),
        )
        self.assertTrue(any("requires qa_attestation" in item for item in issues))

    def test_old_revision_attestation_is_rejected(self):
        qa = {
            "schema_id": "qa_attestation",
            "ok": True,
            "status": "passed",
            "dashboard_id": "synthetic",
            "saved_revision": "old",
            "published_revision": "old",
        }
        issues = validate_qa_attestation_binding(
            qa,
            dashboard_id="synthetic",
            saved_revision="new",
            published_revision="new",
            final_payload_attestation_sha256="a" * 64,
            payload_set_sha256="b" * 64,
            dashboard_composition_sha256="c" * 64,
        )
        self.assertTrue(any("saved_revision does not match" in item for item in issues))


if __name__ == "__main__":
    unittest.main()
