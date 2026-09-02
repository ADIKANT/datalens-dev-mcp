from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.dataset_context_profile import validate_dataset_context_profile
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from datalens_dev_mcp.pipeline.task_planning_stage_services import task_planning_stage_services
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt, validate_stage_receipt


class TaskStageReceiptTests(unittest.TestCase):
    def test_typed_receipt_is_bound_to_task_contract_and_transition(self) -> None:
        digest = "a" * 64
        receipt = build_stage_receipt(
            task_id="task-1", contract_hash=digest, transition="RESOLVED -> BASELINE_READ", status="success",
            build_identity_hash="c" * 64,
        )
        self.assertFalse(validate_stage_receipt(
            receipt, task_id="task-1", contract_hash=digest, transition="RESOLVED -> BASELINE_READ"
        ))
        self.assertIn("contract_hash mismatch", " ".join(validate_stage_receipt(
            receipt, task_id="task-1", contract_hash="b" * 64, transition="RESOLVED -> BASELINE_READ"
        )))

    def test_plain_success_is_not_a_receipt(self) -> None:
        issues = validate_stage_receipt(
            {"status": "success"}, task_id="task-1", contract_hash="a" * 64,
            transition="RESOLVED -> BASELINE_READ",
        )
        self.assertIn("typed stage receipt", " ".join(issues))

    def test_data_proof_stage_follows_typed_change_impact_decision(self) -> None:
        for required in (False, True):
            with self.subTest(required=required), tempfile.TemporaryDirectory() as tmp:
                contract = create_task_contract(
                    raw_request="Update a synthetic dashboard",
                    mode="update",
                    route="editor_advanced",
                    workspace=WorkspaceContract(project_root=tmp),
                ).to_dict()
                contract["data_diagnostics"] = {
                    **dict(contract["data_diagnostics"]),
                    "required": required,
                }
                journal = ProjectJournal(tmp, contract["task_id"])
                if required:
                    journal.root.mkdir(parents=True, exist_ok=True)
                    journal.target_graph_path.write_text(
                        '{"nodes":[{"object_id":"dataset-1","object_type":"dataset"}]}',
                        encoding="utf-8",
                    )
                sentinel = {"status": "context_probe_called", "ok": True}
                with patch.object(
                    TaskDatasetContextService,
                    "stage_handler",
                    return_value=sentinel,
                ) as context_probe:
                    result = task_planning_stage_services(journal, contract)["plan_data_proof"](
                        {"transition": "ROUTE_BOUND -> DATA_PROOF_PLANNED"}
                    )

                if required:
                    self.assertEqual(result, sentinel)
                    context_probe.assert_called_once()
                else:
                    self.assertEqual(result["status"], "success")
                    self.assertIn("dataset probe not applicable", result["observed_facts"])
                    context_probe.assert_not_called()
                    profile = read_json(journal.root / "data" / "context-profile.json", {})
                    proof_plan = read_json(journal.root / "plans" / "data-proof-plan.json", {})
                    self.assertFalse(validate_dataset_context_profile(profile))
                    self.assertEqual(proof_plan["status"], "not_applicable")
                    self.assertFalse(proof_plan["provider_calls_required"])

    def test_direct_editor_source_skips_invented_dataset_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            contract = create_task_contract(
                raw_request="Fix UNKNOWN_IDENTIFIER in an existing Editor source",
                mode="update",
                route="editor_advanced",
                workspace=WorkspaceContract(project_root=tmp),
            ).to_dict()
            contract["data_diagnostics"] = {
                **dict(contract["data_diagnostics"]),
                "required": True,
                "reason_classes": ["source_change"],
            }
            journal = ProjectJournal(tmp, contract["task_id"])
            journal.root.mkdir(parents=True, exist_ok=True)
            journal.target_graph_path.write_text(
                '{"nodes":[{"object_id":"editor-1","object_type":"editor_chart"}]}',
                encoding="utf-8",
            )

            with patch.object(TaskDatasetContextService, "stage_handler") as context_probe:
                result = task_planning_stage_services(journal, contract)["plan_data_proof"](
                    {"transition": "ROUTE_BOUND -> DATA_PROOF_PLANNED"}
                )

            self.assertEqual(result["status"], "success")
            self.assertIn("direct Editor source", " ".join(result["observed_facts"]))
            context_probe.assert_not_called()
            proof_plan = read_json(journal.root / "plans" / "data-proof-plan.json", {})
            self.assertEqual(proof_plan["status"], "direct_editor_source")
            self.assertEqual(proof_plan["proof_mode"], "direct_editor_source")
            self.assertFalse(proof_plan["provider_calls_required"])


if __name__ == "__main__":
    unittest.main()
