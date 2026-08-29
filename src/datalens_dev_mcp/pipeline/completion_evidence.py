from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.delivery_stage_receipts import validate_delivery_receipt
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.proof_levels import PROOF_LEVELS
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


class CompletionEvidenceService:
    def __init__(self, journal: ProjectJournal, contract: dict[str, Any]) -> None:
        self.journal = journal
        self.contract = contract

    @property
    def receipt_path(self) -> Path:
        return self.journal.root / "evidence" / "completion-evidence.json"

    def build(self) -> dict[str, Any]:
        state, _ = self.journal.replay()
        delivery = self.contract.get("delivery") or {}
        browser = self.contract.get("browser_policy") or {}
        verification = self.contract.get("verification") or {}
        verify_existing = self.contract.get("operation_kind") == "verify_existing_effect"
        required = ["public_plan", "target_binding", "qa_receipt", "typed_stage_receipts"]
        if not verify_existing or "data_assertions" in (verification.get("required_live_reads") or []):
            required.append("fresh_data_proof")
        if verify_existing:
            required.append("existing_effect_verification")
        if delivery.get("save"):
            required.extend(["save_receipt", "saved_readback_receipt"])
        if delivery.get("publish"):
            required.extend(["publish_receipt", "published_readback_receipt"])
        if browser.get("mode") == "required":
            required.append("browser_attestation")
        evidence = self._evidence()
        satisfied = [name for name in required if evidence.get(name, {}).get("ok") is True]
        missing = [name for name in required if name not in satisfied]
        limitations = list((evidence.get("fresh_data_proof") or {}).get("limitations") or [])
        limitations.extend((evidence.get("qa_receipt") or {}).get("limitations") or [])
        levels = [
            str(item.get("proof_level") or "")
            for item in evidence.values()
            if isinstance(item, dict) and item.get("ok") is True and item.get("proof_level") in PROOF_LEVELS
        ]
        highest = max(levels, key=PROOF_LEVELS.index) if levels else "source_static"
        payload = {
            "schema_id": "completion_evidence",
            "receipt_version": 1,
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "target_binding_hash": str((read_json(self.journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
            "evaluated_from_state": state.current_state,
            "state": "COMPLETED" if not missing else state.current_state,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "ok": not missing,
            "highest_proof_level": highest,
            "required_evidence": required,
            "satisfied_evidence": satisfied,
            "missing_evidence": missing,
            "evidence_hashes": {
                name: str(item.get("receipt_hash") or item.get("artifact_hash") or "")
                for name, item in evidence.items()
                if isinstance(item, dict) and (item.get("receipt_hash") or item.get("artifact_hash"))
            },
            "limitations": sorted(set(str(item) for item in limitations if str(item))),
        }
        payload["receipt_hash"] = canonical_hash(payload)
        return payload

    def write(self) -> dict[str, Any]:
        payload = self.build()
        write_json(self.receipt_path, payload)
        return payload

    def read_verified(self) -> dict[str, Any]:
        payload = read_json(self.receipt_path, {}) or {}
        if not payload:
            return {}
        material = dict(payload)
        digest = material.pop("receipt_hash", "")
        if digest != canonical_hash(material):
            return {}
        if payload.get("task_id") != self.journal.task_id:
            return {}
        if payload.get("contract_hash") != self.contract.get("contract_hash"):
            return {}
        current_target = (read_json(self.journal.target_binding_path, {}) or {}).get("binding_hash")
        if payload.get("target_binding_hash") != current_target:
            return {}
        current = self.build()
        for key in ("required_evidence", "satisfied_evidence", "missing_evidence", "evidence_hashes", "ok"):
            if payload.get(key) != current.get(key):
                return {}
        return payload

    def _evidence(self) -> dict[str, dict[str, Any]]:
        plan = read_json(self.journal.root / "plans" / "plan.json", {}) or {}
        target = read_json(self.journal.target_binding_path, {}) or {}
        data = read_json(self.journal.root / "evidence" / "data-proof-receipt.json", {}) or {}
        qa = read_json(self.journal.root / "evidence" / "qa-receipt.json", {}) or {}
        existing_effect = read_json(
            self.journal.root / "evidence" / "existing-effect-verification.json", {}
        ) or {}
        save = read_json(self.journal.save_stage_receipt_path, {}) or {}
        saved = read_json(self.journal.saved_readback_receipt_path, {}) or {}
        publish = read_json(self.journal.publish_stage_receipt_path, {}) or {}
        published = read_json(self.journal.published_readback_receipt_path, {}) or {}
        state, _ = self.journal.replay()
        contract_hash = str(self.contract.get("contract_hash") or "")
        values = {
            "public_plan": {
                "ok": bool(plan.get("plan_hash") and plan.get("contract_hash") == contract_hash),
                "artifact_hash": str(plan.get("plan_hash") or ""),
                "proof_level": "source_static",
            },
            "target_binding": {
                "ok": bool(target.get("binding_hash")),
                "artifact_hash": str(target.get("binding_hash") or ""),
                "proof_level": "live_read_only_api" if target.get("source") == "live_discovery" else "source_static",
            },
            "fresh_data_proof": {
                **data,
                "ok": bool(data.get("fresh") and data.get("status") == "passed" and data.get("live_data_verified")),
            },
            "qa_receipt": {**qa, "ok": qa.get("status") == "passed"},
            "existing_effect_verification": {
                **existing_effect,
                "ok": bool(
                    existing_effect.get("status") == "passed"
                    and existing_effect.get("outcome") == "verified"
                    and int(existing_effect.get("write_executed") or 0) == 0
                ),
                "proof_level": "live_read_only_api",
            },
            "typed_stage_receipts": {
                "ok": bool(state.receipt_uris),
                "proof_level": "source_static",
            },
            "save_receipt": _delivery_evidence(save, "datalens_save_stage_receipt", self.journal, contract_hash),
            "saved_readback_receipt": _delivery_evidence(
                saved, "datalens_saved_readback_receipt", self.journal, contract_hash, proof_level="save_readback"
            ),
            "publish_receipt": _delivery_evidence(
                publish, "datalens_publish_stage_receipt", self.journal, contract_hash
            ),
            "published_readback_receipt": _delivery_evidence(
                published,
                "datalens_published_readback_receipt",
                self.journal,
                contract_hash,
                proof_level="publish_readback",
            ),
            "browser_attestation": {
                "ok": bool((qa.get("browser_attestation") or {}).get("ok")),
                "artifact_hash": str((qa.get("browser_attestation") or {}).get("sha256") or ""),
                "proof_level": "browser_rendered",
            },
        }
        return values


def _delivery_evidence(
    receipt: dict[str, Any],
    schema_id: str,
    journal: ProjectJournal,
    contract_hash: str,
    *,
    proof_level: str = "",
) -> dict[str, Any]:
    issues = validate_delivery_receipt(
        receipt,
        schema_id=schema_id,
        task_id=journal.task_id,
        contract_hash=contract_hash,
    ) if receipt else ("missing",)
    return {
        "ok": not issues and receipt.get("status") == "success",
        "receipt_hash": str(receipt.get("receipt_hash") or ""),
        "proof_level": proof_level,
    }
