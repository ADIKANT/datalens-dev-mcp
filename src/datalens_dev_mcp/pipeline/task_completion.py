from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal


class TaskCompletionEvaluator:
    def evaluate(self, journal: ProjectJournal, contract: dict[str, Any], *, proof_target: str) -> dict[str, Any]:
        state, _ = journal.replay()
        required = ["typed_stage_receipts"]
        missing: list[str] = []
        if state.current_state != "COMPLETED":
            missing.append("terminal completion state")
        if proof_target == "live":
            required.append("live_target_binding")
            target_binding = read_json(journal.target_binding_path, {}) or {}
            if target_binding.get("source") != "live_discovery":
                missing.append("live target binding")
        if not state.receipt_uris:
            missing.append("stage receipts")
        return {
            "ok": not missing,
            "state": state.current_state,
            "highest_proof_level": "source_static" if not missing else "none",
            "required_evidence": required,
            "satisfied_evidence": [item for item in required if item not in missing],
            "missing_evidence": missing,
            "limitations": [] if not missing else ["completion is not supported by all required typed evidence"],
        }
