from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from datalens_dev_mcp.pipeline.decision_patches import (
    apply_decision_contract_to_chart_plan,
    decision_contract_drift_issues,
    record_user_decision_patch,
    resolve_active_decision_contract,
)
from datalens_dev_mcp.pipeline.requirements_workspace import update_user_decision
from datalens_dev_mcp.pipeline.safe_apply import (
    create_safe_apply_plan,
    validate_safe_apply_plan_exhaustive,
)


class UserDecisionPatchTests(unittest.TestCase):
    def test_scope_precedence_and_semantic_role_resolution_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._record(
                root,
                "DEC-PROJECT",
                {
                    "scope": {"kind": "project"},
                    "metric_semantics": {"comparator": "target"},
                    "visual_spec_overlay": {"colors": {"focus": "#111111"}},
                    "required_semantic_roles": ["neutral"],
                },
            )
            self._record(
                root,
                "DEC-FAMILY",
                {
                    "scope": {"kind": "family", "ids": ["bar"]},
                    "visual_spec_overlay": {"colors": {"focus": "#222222"}},
                    "required_semantic_roles": ["warning"],
                },
            )
            self._record(
                root,
                "DEC-OBJECT",
                {
                    "scope": {"kind": "object", "id": "widget_1"},
                    "visual_spec_overlay": {"colors": {"focus": "#333333"}},
                    "required_semantic_roles": ["success"],
                    "forbidden_semantic_roles": ["warning"],
                },
            )

            contract = resolve_active_decision_contract(
                root,
                {"widget_id": "widget_1", "family": "bar"},
            )

        self.assertEqual(contract["metric_semantics"]["comparator"], "target")
        self.assertEqual(contract["visual_spec_overlay"]["colors"]["focus"], "#333333")
        self.assertEqual(contract["required_semantic_roles"], ["neutral", "success"])
        self.assertEqual(contract["forbidden_semantic_roles"], ["warning"])
        self.assertEqual(len(contract["matched_revision_ids"]), 3)

    def test_supersedes_removes_old_revision_from_active_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = self._record(
                root,
                "DEC-OLD",
                {
                    "scope": {"kind": "project"},
                    "visual_spec_overlay": {"labels": {"direct_labels": True}},
                },
            )
            self._record(
                root,
                "DEC-NEW",
                {
                    "scope": {"kind": "project"},
                    "visual_spec_overlay": {"labels": {"direct_labels": False}},
                    "supersedes": [old["revision_id"]],
                },
            )

            contract = resolve_active_decision_contract(root, {"family": "bar"})

        self.assertEqual(contract["visual_spec_overlay"]["labels"]["direct_labels"], False)
        self.assertEqual(len(contract["matched_revision_ids"]), 1)

    def test_applied_contract_is_hash_bound_and_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._record(
                root,
                "DEC-1",
                {
                    "scope": {"kind": "object", "ids": ["widget_1"]},
                    "metric_semantics": {"semantic_direction": "higher_is_better"},
                    "visual_spec_overlay": {"tooltip": {"bucket_label": "single_interval"}},
                    "required_semantic_roles": ["success"],
                },
            )
            source = {
                "widget_id": "widget_1",
                "family": "bar",
                "chart_decision_record": {
                    "renderer_visual_spec": {
                        "family": "bar",
                        "tooltip": {"include_values": True},
                    }
                },
            }
            applied = apply_decision_contract_to_chart_plan(root, source)["chart_plan"]
            self.assertEqual(decision_contract_drift_issues(root, applied), [])
            applied["chart_decision_record"]["renderer_visual_spec"]["tooltip"]["bucket_label"] = "range"
            issues = decision_contract_drift_issues(root, applied)

        self.assertTrue(any("renderer_visual_spec drift" in issue for issue in issues))

    def test_invalid_patch_is_rejected_without_decision_ledger_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = update_user_decision(
                root,
                decision_text="Use an unknown visual section",
                decision_id="DEC-BAD",
                decision_patch={
                    "scope": {"kind": "project"},
                    "visual_spec_overlay": {"unsupported": {"x": 1}},
                },
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["category"], "invalid_decision_patch")
            self.assertFalse((root / "requirements" / "user_decisions.v2.json").exists())
            self.assertNotIn("DEC-BAD", (root / "requirements" / "user_decisions.md").read_text())

    def test_safe_apply_plan_blocks_after_decision_ledger_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._record(
                root,
                "DEC-1",
                {
                    "scope": {"kind": "project"},
                    "metric_semantics": {"comparator": "target"},
                },
            )
            plan = create_safe_apply_plan(
                project_root=str(root),
                actions=[],
                approved=True,
                user_request_text="update dashboard",
            )
            self._record(
                root,
                "DEC-2",
                {
                    "scope": {"kind": "project"},
                    "metric_semantics": {"comparator": "sla"},
                },
            )
            validation = validate_safe_apply_plan_exhaustive(plan)

        self.assertTrue(any("decision_ledger_sha256 is stale" in issue for issue in validation["issues"]))

    def _record(self, root: Path, decision_id: str, patch: dict[str, object]) -> dict[str, object]:
        result = record_user_decision_patch(
            root,
            decision_id=decision_id,
            decision_text=decision_id,
            decision_patch=patch,
        )
        self.assertTrue(result["ok"], result)
        return result


if __name__ == "__main__":
    unittest.main()
