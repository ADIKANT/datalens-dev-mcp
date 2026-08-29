from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.validators.redaction import sanitize_value


class ExistingEffectVerificationService:
    """Verify a compiled existing effect from fresh persisted read evidence only."""

    def __init__(self, journal: ProjectJournal, contract: dict[str, Any]) -> None:
        self.journal = journal
        self.contract = contract

    @property
    def receipt_path(self) -> Path:
        return self.journal.root / "evidence" / "existing-effect-verification.json"

    def execute(self) -> dict[str, Any]:
        target = read_json(self.journal.target_binding_path, {}) or {}
        graph = read_json(self.journal.target_graph_path, {}) or {}
        discovery = read_json(self.journal.discovery_path, {}) or {}
        data = read_json(self.journal.root / "evidence" / "data-proof-receipt.json", {}) or {}
        nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
        provider_calls = [item for item in discovery.get("provider_calls") or [] if isinstance(item, dict)]
        successful_reads = [
            item
            for item in provider_calls
            if str(item.get("effect") or "read") == "read"
            and str(item.get("status") or "").lower() in {"success", "succeeded", "passed", "ok"}
        ]
        revisions = _revisions(target, nodes)
        required = list((self.contract.get("verification") or {}).get("required_live_reads") or [])
        checks = {
            "current_object": bool(target.get("source") == "live_discovery" and graph.get("graph_hash") and nodes and successful_reads),
            "saved_or_published_revision": bool(revisions and successful_reads),
            "relations": bool(graph.get("graph_hash") and isinstance(graph.get("edges"), list) and successful_reads),
            "data_assertions": bool(
                data.get("fresh")
                and data.get("live_data_verified")
                and data.get("status") == "passed"
                and _not_empty_passed(data)
            ),
            "runtime_assertions_if_applicable": False,
        }
        effect = dict(self.contract.get("effect") or {})
        outcome, effect_reason = _evaluate_effect(
            str(effect.get("kind") or "none"),
            checks=checks,
            revisions=revisions,
            nodes=nodes,
        )
        missing_reads = [name for name in required if not checks.get(name, False)]
        acceptance = [item for item in self.contract.get("acceptance") or [] if isinstance(item, dict)]
        if not acceptance:
            outcome = "indeterminate"
            effect_reason = "acceptance contract is empty"
        verified = outcome == "verified" and not missing_reads and bool(acceptance)
        payload = {
            "schema_id": "datalens_existing_effect_verification_receipt",
            "receipt_version": 1,
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "target_binding_hash": str(target.get("binding_hash") or ""),
            "target_graph_hash": str(graph.get("graph_hash") or ""),
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "operation_kind": str(self.contract.get("operation_kind") or ""),
            "effect": effect,
            "outcome": "verified" if verified else outcome,
            "status": "passed" if verified else "blocked",
            "effect_reason": effect_reason,
            "required_live_reads": required,
            "read_checks": {name: bool(checks.get(name, False)) for name in required},
            "missing_live_reads": missing_reads,
            "acceptance_count": len(acceptance),
            "provider_calls": sanitize_value(provider_calls),
            "successful_provider_read_count": len(successful_reads),
            "revision_observations": revisions,
            "relation_count": len(graph.get("edges") or []),
            "write_attempted": 0,
            "write_executed": 0,
            "remediation": {
                "enabled": False,
                "requires_new_user_scope": True,
            },
            "limitations": _limitations(outcome, missing_reads, effect_reason),
        }
        payload["receipt_hash"] = canonical_hash(payload)
        write_json(self.receipt_path, payload)
        return payload


def _revisions(target: dict[str, Any], nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for node in nodes:
        saved = str(node.get("saved_revision") or node.get("saved_id") or "")
        published = str(node.get("published_revision") or node.get("published_id") or "")
        if saved or published:
            rows.append(
                {
                    "object_id": str(node.get("object_id") or ""),
                    "saved_revision": saved,
                    "published_revision": published,
                }
            )
    if not rows:
        saved = str(target.get("saved_revision") or "")
        published = str(target.get("published_revision") or "")
        if saved or published:
            rows.append(
                {
                    "object_id": str(target.get("object_id") or target.get("dashboard_id") or ""),
                    "saved_revision": saved,
                    "published_revision": published,
                }
            )
    return rows


def _evaluate_effect(
    kind: str,
    *,
    checks: dict[str, bool],
    revisions: list[dict[str, str]],
    nodes: list[dict[str, Any]],
) -> tuple[str, str]:
    if kind == "published":
        if not revisions:
            return "not_verified", "no saved or published revision was observed"
        matching = [
            item
            for item in revisions
            if item["published_revision"]
            and (not item["saved_revision"] or item["published_revision"] == item["saved_revision"])
        ]
        return (
            ("verified", "fresh readback shows a current published revision")
            if matching
            else ("not_verified", "published revision is missing or differs from current saved revision")
        )
    if kind == "saved":
        return (
            ("verified", "fresh readback shows a saved revision")
            if any(item["saved_revision"] for item in revisions)
            else ("not_verified", "saved revision is missing")
        )
    if kind == "restored":
        return (
            ("verified", "current object and relation graph are present")
            if nodes and checks.get("relations")
            else ("not_verified", "restored object or relation graph is incomplete")
        )
    if kind == "data_appeared":
        return (
            ("verified", "fresh bounded dataset assertion is non-empty")
            if checks.get("data_assertions")
            else ("not_verified", "fresh bounded non-empty dataset assertion did not pass")
        )
    if kind == "deleted":
        return "indeterminate", "absence verification requires a parent relation target or explicit absence locator"
    if kind == "moved":
        return "indeterminate", "move verification requires an explicit destination workbook relation"
    if kind == "changed":
        return "indeterminate", "generic change wording does not identify the semantic effect to compare"
    return "indeterminate", "compiled effect kind is not independently verifiable"


def _not_empty_passed(data: dict[str, Any]) -> bool:
    assertions = [item for item in data.get("assertions") or [] if isinstance(item, dict)]
    return bool(
        int(data.get("row_count") or 0) > 0
        and any(item.get("kind") == "not_empty" and item.get("status") == "passed" for item in assertions)
    )


def _limitations(outcome: str, missing_reads: list[str], reason: str) -> list[str]:
    rows = [f"missing required live read: {item}" for item in missing_reads]
    if outcome != "verified" and reason:
        rows.append(reason)
    return sorted(set(rows))
