from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.assertion_spec_compiler import ALIASES
from datalens_dev_mcp.pipeline.browser_qa import (
    build_browser_qa_plan,
    validate_qa_attestation_binding,
)
from datalens_dev_mcp.pipeline.evidence_matrix import build_evidence_matrix, normalize_browser_policy
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.public_plan_builder import PublicPlanBuilder
from datalens_dev_mcp.pipeline.task_data_proof_service import TaskDataProofService
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.validators.redaction import sanitize_value


class TaskQaService:
    def __init__(
        self,
        journal: ProjectJournal,
        contract: dict[str, Any],
        *,
        client: Any | None = None,
        browser_adapter: Any | None = None,
        execute_optional_browser: bool = False,
    ) -> None:
        self.journal = journal
        self.contract = contract
        self.data_service = TaskDataProofService(journal, contract, client=client)
        self.browser_adapter = browser_adapter
        self.execute_optional_browser = execute_optional_browser

    @property
    def receipt_path(self) -> Path:
        return self.journal.root / "evidence" / "qa-receipt.json"

    def execute(self) -> dict[str, Any]:
        data_receipt = self.data_service.execute()
        plan_issues = list(PublicPlanBuilder(self.journal, self.contract).validate_current())
        static_evidence = {"ok": not plan_issues, "status": "passed" if not plan_issues else "failed"}
        runtime_evidence = {
            "schema_id": "render_contract_result",
            "ok": not plan_issues,
            "status": "passed" if not plan_issues else "failed",
            "plan_hash": str((read_json(self.journal.root / "plans" / "plan.json", {}) or {}).get("plan_hash") or ""),
            "issues": plan_issues,
        }
        runtime_evidence["result_hash"] = canonical_hash(runtime_evidence)
        saved = read_json(self.journal.saved_readback_receipt_path, {}) or {}
        published = read_json(self.journal.published_readback_receipt_path, {}) or {}
        policy = normalize_browser_policy(
            dict(self.contract.get("browser_policy") or {}),
            change_class=_change_class(self.contract),
        )
        browser = self._browser_evidence(policy, saved=saved, published=published)
        acceptance_coverage = _acceptance_coverage(
            self.contract,
            data_receipt=data_receipt,
            runtime_ok=bool(runtime_evidence["ok"]),
            saved=saved,
            published=published,
        )
        evidence = {
            "static_validation": static_evidence,
            "data_assertions": {"ok": data_receipt.get("status") == "passed"},
            "contract_harness": runtime_evidence,
            "composition_validation": static_evidence,
            "saved_readback": {
                "ok": saved.get("status") == "success" or not (self.contract.get("delivery") or {}).get("save")
            },
            "published_readback": {
                "ok": published.get("status") == "success" or not (self.contract.get("delivery") or {}).get("publish")
            },
            "browser_attestation": browser.get("attestation") or {},
        }
        matrix = build_evidence_matrix(
            change_class=_change_class(self.contract),
            browser_policy=policy,
            evidence=evidence,
            stage="completion",
        )
        limitations = list(data_receipt.get("limitations") or [])
        limitations.extend(str(item) for item in browser.get("issues") or [] if str(item))
        if browser.get("reason"):
            limitations.append(f"browser evidence unavailable: {browser['reason']}")
        if policy["mode"] == "optional" and not browser.get("attestation"):
            limitations.append("optional browser evidence was not collected")
        if policy["mode"] == "forbidden":
            limitations.append("browser execution was forbidden; contract runtime evidence used")
        ok = bool(
            data_receipt.get("status") == "passed"
            and runtime_evidence["ok"]
            and matrix.get("can_publish")
            and browser.get("ok")
            and acceptance_coverage["ok"]
        )
        payload = {
            "schema_id": "task_qa_receipt",
            "receipt_version": 1,
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "target_binding_hash": str((read_json(self.journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "passed" if ok else "blocked",
            "proof_level": str(browser.get("proof_level") or "contract_runtime"),
            "data_proof_receipt_hash": str(data_receipt.get("receipt_hash") or ""),
            "runtime_evidence": runtime_evidence,
            "browser_policy": policy,
            "browser_adapter_calls": int(browser.get("adapter_calls") or 0),
            "browser_attestation": sanitize_value(browser.get("attestation") or {}),
            "evidence_matrix": matrix,
            "acceptance_coverage": acceptance_coverage,
            "limitations": sorted(set(limitations)),
        }
        payload["receipt_hash"] = canonical_hash(payload)
        write_json(self.receipt_path, payload)
        return payload

    def stage_handler(self, context: dict[str, Any]) -> dict[str, Any]:
        result = self.execute()
        missing = list((result.get("evidence_matrix") or {}).get("missing_evidence") or [])
        missing.extend(list((result.get("acceptance_coverage") or {}).get("missing_evidence") or []))
        if result.get("status") != "passed" and not missing:
            missing.append("fresh_typed_data_proof")
        receipt = build_stage_receipt(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status="success" if result.get("status") == "passed" else "blocked",
            proof_level=str(result.get("proof_level") or "source_static"),
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            output_hashes={"task_qa_receipt": str(result.get("receipt_hash") or "")},
            hard_requirements=["fresh_typed_data_proof", "contract_runtime", "browser_policy"],
            missing_requirements=missing,
            reason="typed data and QA evidence passed" if result.get("status") == "passed" else "QA evidence is incomplete",
            observed_facts=[
                f"browser mode={((result.get('browser_policy') or {}).get('mode', 'optional'))}",
                f"browser calls={result.get('browser_adapter_calls', 0)}",
            ],
        )
        receipt["limitations"] = list(result.get("limitations") or [])
        return receipt

    def _browser_evidence(
        self,
        policy: dict[str, Any],
        *,
        saved: dict[str, Any],
        published: dict[str, Any],
    ) -> dict[str, Any]:
        mode = str(policy.get("mode") or "optional")
        should_execute = mode == "required" or (mode == "optional" and self.execute_optional_browser)
        if not should_execute:
            return {"ok": True, "adapter_calls": 0, "proof_level": "contract_runtime", "attestation": {}}
        if self.browser_adapter is None:
            return {"ok": False, "adapter_calls": 0, "proof_level": "contract_runtime", "attestation": {}}
        expected = _browser_binding(self.journal, self.contract, saved=saved, published=published)
        try:
            plan = build_browser_qa_plan(
                dashboard_id=expected["dashboard_id"],
                tab_ids=expected["tab_ids"],
                expected_object_ids=expected["object_ids"],
                saved_revision=expected["saved_revision"],
                published_revision=expected["published_revision"],
                final_payload_attestation_sha256=expected["final_payload_attestation_sha256"],
                payload_set_sha256=expected["payload_set_sha256"],
                dashboard_composition={"sha256": expected["dashboard_composition_sha256"]},
            )
        except Exception as exc:  # noqa: BLE001 - invalid browser binding is explicit evidence.
            return {
                "ok": False,
                "adapter_calls": 0,
                "proof_level": "contract_runtime",
                "attestation": {},
                "reason": f"browser_plan_invalid:{exc.__class__.__name__}",
            }
        try:
            attestation = self.browser_adapter(plan)
        except Exception as exc:  # noqa: BLE001 - browser adapter availability is typed evidence.
            return {
                "ok": False,
                "adapter_calls": 1,
                "proof_level": "contract_runtime",
                "attestation": {},
                "reason": exc.__class__.__name__,
            }
        issues = validate_qa_attestation_binding(
            attestation,
            dashboard_id=expected["dashboard_id"],
            saved_revision=expected["saved_revision"],
            published_revision=expected["published_revision"],
            final_payload_attestation_sha256=expected["final_payload_attestation_sha256"],
            payload_set_sha256=expected["payload_set_sha256"],
            dashboard_composition_sha256=expected["dashboard_composition_sha256"],
        )
        return {
            "ok": not issues,
            "adapter_calls": 1,
            "proof_level": "browser_rendered" if not issues else "contract_runtime",
            "attestation": attestation if not issues else {},
            "issues": issues,
        }


def task_qa_stage_services(
    journal: ProjectJournal,
    contract: dict[str, Any],
) -> dict[str, Any]:
    service = TaskQaService(journal, contract)
    return {
        "run_qa": service.stage_handler,
        "verify_read_only_result": service.stage_handler,
    }


def _change_class(contract: dict[str, Any]) -> str:
    text = " ".join(
        f"{item.get('kind', '')} {item.get('statement', '')}"
        for item in contract.get("acceptance") or []
        if isinstance(item, dict)
    ).lower()
    if "selector" in text or "filter" in text:
        return "selector_behavior"
    if "layout" in text or "dashboard" in text:
        return "dashboard_layout"
    if "publish_only" in str(contract.get("mode") or ""):
        return "publish_only"
    if any(token in text for token in ("renderer", "javascript", "tooltip", "legend")):
        return "renderer_logic"
    return "source_labels_only"


def _acceptance_coverage(
    contract: dict[str, Any],
    *,
    data_receipt: dict[str, Any],
    runtime_ok: bool,
    saved: dict[str, Any],
    published: dict[str, Any],
) -> dict[str, Any]:
    data_results = {
        str(item.get("criterion_hash") or ""): item
        for item in data_receipt.get("assertions") or []
        if isinstance(item, dict) and item.get("criterion_hash")
    }
    delivery = contract.get("delivery") or {}
    delivery_ok = bool(
        (not delivery.get("save") or saved.get("status") == "success")
        and (not delivery.get("publish") or published.get("status") == "success")
    )
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for index, criterion in enumerate(contract.get("acceptance") or []):
        if not isinstance(criterion, dict) or criterion.get("hard") is False:
            continue
        source_kind = str(criterion.get("kind") or "business")
        criterion_hash = canonical_hash(
            {
                "kind": source_kind,
                "statement": str(criterion.get("statement") or ""),
                "hard": bool(criterion.get("hard", True)),
            }
        )
        canonical_kind = ALIASES.get(source_kind, source_kind)
        result = data_results.get(criterion_hash, {})
        if canonical_kind in {
            "not_empty", "expected_empty", "unique_key", "no_nulls", "min_max_date",
            "row_count_between", "value_domain", "filter_effect", "sort_total_order",
            "ratio_consistency", "saved_vs_published_consistency",
        }:
            evidence_kind = "data_assertion"
            satisfied = result.get("status") == "passed"
        elif source_kind == "semantic_change":
            evidence_kind = "planned_payload_readback"
            satisfied = bool(runtime_ok and delivery_ok)
        else:
            evidence_kind = "unsupported_hard_acceptance"
            satisfied = False
        evidence_name = f"hard_acceptance:{index}"
        if not satisfied:
            missing.append(evidence_name)
        rows.append(
            {
                "acceptance_index": index,
                "criterion_hash": criterion_hash,
                "kind": source_kind,
                "evidence_kind": evidence_kind,
                "satisfied": satisfied,
            }
        )
    return {"ok": not missing, "criteria": rows, "missing_evidence": missing}


def _browser_binding(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    saved: dict[str, Any],
    published: dict[str, Any],
) -> dict[str, Any]:
    public_plan = read_json(journal.root / "plans" / "plan.json", {}) or {}
    artifact_hashes = {
        str(item.get("kind") or ""): str(item.get("sha256") or "")
        for item in public_plan.get("artifacts") or []
        if isinstance(item, dict)
    }
    target = contract.get("target") or {}
    target_binding = read_json(journal.target_binding_path, {}) or {}
    scoped_ids = (public_plan.get("scope") or {}).get("allowed_objects") or []
    object_ids = [str(item) for item in target.get("object_ids") or scoped_ids if str(item)]
    saved_revisions = [str(item.get("revision") or "") for item in saved.get("objects") or [] if item.get("revision")]
    published_revisions = [
        str(item.get("revision") or "") for item in published.get("objects") or [] if item.get("revision")
    ]
    saved_revision = saved_revisions[0] if len(set(saved_revisions)) == 1 else str(target.get("saved_revision") or "")
    published_revision = (
        published_revisions[0]
        if len(set(published_revisions)) == 1
        else str(target.get("published_revision") or saved_revision)
    )
    dashboard_id = str(
        target.get("dashboard_id")
        or target_binding.get("dashboard_id")
        or (object_ids[0] if object_ids else "")
    )
    tabs = [
        str(item)
        for item in ((contract.get("scope") or {}).get("allowed_tabs") or (public_plan.get("scope") or {}).get("allowed_tabs") or [])
        if str(item)
    ] or ["main"]
    composition_hash = canonical_hash({"dashboard_id": dashboard_id, "object_ids": object_ids, "tabs": tabs})
    return {
        "dashboard_id": dashboard_id,
        "object_ids": object_ids or [dashboard_id],
        "tab_ids": tabs,
        "saved_revision": saved_revision,
        "published_revision": published_revision or saved_revision,
        "final_payload_attestation_sha256": artifact_hashes.get("safe_apply_plan") or "0" * 64,
        "payload_set_sha256": artifact_hashes.get("materialized_payloads") or "0" * 64,
        "dashboard_composition_sha256": composition_hash,
    }
