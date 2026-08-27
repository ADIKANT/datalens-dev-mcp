from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.completion_evidence import CompletionEvidenceService
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt


class TaskCompletionEvaluator:
    def evaluate(self, journal: ProjectJournal, contract: dict[str, Any], *, proof_target: str) -> dict[str, Any]:
        state, _ = journal.replay()
        evidence = CompletionEvidenceService(journal, contract).read_verified()
        if not evidence:
            missing = ["valid completion evidence receipt"]
            limitations = ["completion evidence is missing, stale, or hash-invalid"]
            blocker = state.blocker if isinstance(state.blocker, dict) else {}
            if state.current_state == "BLOCKED" and blocker.get("code") == "BLOCKED_DISCOVERY":
                missing.append("live target binding")
                if blocker.get("reason"):
                    limitations.append(str(blocker["reason"]))
            return {
                "ok": False,
                "state": state.current_state,
                "highest_proof_level": "source_static",
                "required_evidence": [],
                "satisfied_evidence": [],
                "missing_evidence": missing,
                "limitations": limitations,
                "completion_receipt_uri": "",
            }
        result = dict(evidence)
        result["state"] = state.current_state
        result["ok"] = bool(evidence.get("ok") and state.current_state == "COMPLETED")
        if proof_target == "live" and evidence.get("highest_proof_level") == "source_static":
            result["ok"] = False
            result["missing_evidence"] = [*list(result.get("missing_evidence") or []), "live proof"]
        result["completion_receipt_uri"] = journal.receipt_uri("evidence/completion-evidence.json")
        return result


def completion_stage_service(
    journal: ProjectJournal,
    contract: dict[str, Any],
):
    service = CompletionEvidenceService(journal, contract)

    def verify_completion(context: dict[str, Any]) -> dict[str, Any]:
        evidence = service.write()
        receipt = build_stage_receipt(
            task_id=journal.task_id,
            contract_hash=str(contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status="success" if evidence.get("ok") else "blocked",
            proof_level=str(evidence.get("highest_proof_level") or "source_static"),
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            output_hashes={"completion_evidence": str(evidence.get("receipt_hash") or "")},
            hard_requirements=list(evidence.get("required_evidence") or []),
            missing_requirements=list(evidence.get("missing_evidence") or []),
            reason="all required typed evidence is satisfied" if evidence.get("ok") else "completion evidence is incomplete",
        )
        receipt["limitations"] = list(evidence.get("limitations") or [])
        return receipt

    return {"verify_completion": verify_completion}
