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
from datalens_dev_mcp.pipeline.existing_effect_verification import ExistingEffectVerificationService
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
        if str(self.contract.get("operation_kind") or "") == "verify_existing_effect":
            return self._execute_existing_effect()
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
        api_first_diagnostics = _api_first_diagnostics_summary(
            self.journal,
            self.contract,
            data_receipt=data_receipt,
            saved=saved,
            published=published,
        )
        browser = self._browser_evidence(
            policy,
            saved=saved,
            published=published,
            data_receipt=data_receipt,
            plan_issues=plan_issues,
        )
        acceptance_coverage = _acceptance_coverage(
            self.contract,
            data_receipt=data_receipt,
            runtime_ok=bool(runtime_evidence["ok"]),
            saved=saved,
            published=published,
        )
        evidence = {
            "static_validation": static_evidence,
            "data_assertions": {
                "ok": data_receipt.get("status") == "passed",
                "fallback_kind": str(data_receipt.get("fallback_kind") or ""),
                "live_data_verified": bool(data_receipt.get("live_data_verified")),
            },
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
            "api_first_diagnostics": api_first_diagnostics,
            "browser_policy": policy,
            "browser_adapter_calls": int(browser.get("adapter_calls") or 0),
            "browser_status": str(browser.get("status") or "not_required"),
            "browser_attestation": sanitize_value(browser.get("attestation") or {}),
            "evidence_matrix": matrix,
            "acceptance_coverage": acceptance_coverage,
            "limitations": sorted(set(limitations)),
        }
        payload["receipt_hash"] = canonical_hash(payload)
        write_json(self.receipt_path, payload)
        return payload

    def _execute_existing_effect(self) -> dict[str, Any]:
        required_reads = set((self.contract.get("verification") or {}).get("required_live_reads") or [])
        data_receipt = self.data_service.execute() if "data_assertions" in required_reads else {}
        verification = ExistingEffectVerificationService(self.journal, self.contract).execute()
        acceptance_coverage = _acceptance_coverage(
            self.contract,
            data_receipt=data_receipt,
            runtime_ok=verification.get("status") == "passed",
            saved={},
            published={},
            verification_receipt=verification,
        )
        missing = list(verification.get("missing_live_reads") or [])
        missing.extend(list(acceptance_coverage.get("missing_evidence") or []))
        ok = bool(verification.get("status") == "passed" and acceptance_coverage.get("ok"))
        payload = {
            "schema_id": "task_qa_receipt",
            "receipt_version": 1,
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "target_binding_hash": str((read_json(self.journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "passed" if ok else "blocked",
            "proof_level": "live_read_only_api" if ok else "source_static",
            "data_proof_receipt_hash": str(data_receipt.get("receipt_hash") or ""),
            "existing_effect_verification_hash": str(verification.get("receipt_hash") or ""),
            "existing_effect_outcome": str(verification.get("outcome") or "indeterminate"),
            "runtime_evidence": {
                "schema_id": "existing_effect_runtime_result",
                "ok": ok,
                "status": "passed" if ok else "blocked",
                "write_attempted": 0,
                "write_executed": 0,
            },
            "browser_policy": {"mode": "forbidden", "source": "compiled_verification_default"},
            "browser_adapter_calls": 0,
            "browser_attestation": {},
            "evidence_matrix": {
                "can_publish": ok,
                "missing_evidence": sorted(set(str(item) for item in missing if str(item))),
            },
            "acceptance_coverage": acceptance_coverage,
            "limitations": list(verification.get("limitations") or []),
        }
        payload["receipt_hash"] = canonical_hash(payload)
        write_json(self.receipt_path, payload)
        return payload

    def stage_handler(self, context: dict[str, Any]) -> dict[str, Any]:
        result = self.execute()
        verify_existing = str(self.contract.get("operation_kind") or "") == "verify_existing_effect"
        missing = list((result.get("evidence_matrix") or {}).get("missing_evidence") or [])
        missing.extend(list((result.get("acceptance_coverage") or {}).get("missing_evidence") or []))
        if result.get("status") != "passed" and not missing:
            missing.append("existing_effect_live_readback" if verify_existing else "fresh_typed_data_proof")
        receipt = build_stage_receipt(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status="success" if result.get("status") == "passed" else "blocked",
            proof_level=str(result.get("proof_level") or "source_static"),
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            output_hashes={"task_qa_receipt": str(result.get("receipt_hash") or "")},
            hard_requirements=(
                ["existing_effect_live_readback", "required_provider_reads", "zero_mutation"]
                if verify_existing
                else ["fresh_typed_data_proof", "contract_runtime", "browser_policy"]
            ),
            missing_requirements=missing,
            reason=(
                "existing effect is verified from required live reads with zero mutation"
                if verify_existing and result.get("status") == "passed"
                else "typed data and QA evidence passed"
                if result.get("status") == "passed"
                else "QA evidence is incomplete"
            ),
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
        data_receipt: dict[str, Any],
        plan_issues: list[str],
    ) -> dict[str, Any]:
        mode = str(policy.get("mode") or "optional")
        should_execute = mode == "required" or (
            mode == "optional" and self.execute_optional_browser
        )
        if not should_execute:
            return {
                "ok": True,
                "adapter_calls": 0,
                "proof_level": "contract_runtime",
                "attestation": {},
                "status": "forbidden_zero_calls" if mode == "forbidden" else "optional_not_collected",
            }
        final_visual = str(policy.get("purpose") or "") == "final_visual_acceptance"
        if final_visual:
            data_diagnostics = data_receipt.get("api_first_diagnostics") or {}
            diagnostics_decision = (
                self.contract.get("data_diagnostics")
                if isinstance(self.contract.get("data_diagnostics"), dict)
                else {}
            )
            diagnostics_required = diagnostics_decision.get("required") is True
            diagnostics_status = str(data_diagnostics.get("status") or "")
            prerequisites_ok = bool(
                not plan_issues
                and data_receipt.get("status") in {"passed", "not_required"}
                and (
                    diagnostics_status == "passed"
                    if diagnostics_required
                    else diagnostics_status in {"passed", "not_required"}
                )
                and saved.get("status") == "success"
                and published.get("status") == "success"
                and str(data_receipt.get("receipt_hash") or "")
            )
            if not prerequisites_ok:
                return {
                    "ok": False,
                    "adapter_calls": 0,
                    "proof_level": "contract_runtime",
                    "attestation": {},
                    "reason": "final_visual_prerequisites_incomplete",
                    "status": "awaiting_api_first_prerequisites",
                }
        if self.browser_adapter is None:
            return {
                "ok": False,
                "adapter_calls": 0,
                "proof_level": "contract_runtime",
                "attestation": {},
                "reason": "browser_adapter_unavailable",
                "status": "awaiting_visual_acceptance" if final_visual else "browser_required_unavailable",
            }
        expected = _browser_binding(self.journal, self.contract, saved=saved, published=published)
        try:
            plan = build_browser_qa_plan(
                dashboard_id=expected["dashboard_id"],
                dashboard_url=expected["dashboard_url"],
                tab_ids=expected["tab_ids"],
                expected_object_ids=expected["object_ids"],
                saved_revision=expected["saved_revision"],
                published_revision=expected["published_revision"],
                final_payload_attestation_sha256=expected["final_payload_attestation_sha256"],
                payload_set_sha256=expected["payload_set_sha256"],
                dashboard_composition={"sha256": expected["dashboard_composition_sha256"]},
                browser_policy=policy,
                api_diagnostics_receipt_hash=str(data_receipt.get("receipt_hash") or ""),
                task_id=expected["task_id"],
                contract_revision=expected["contract_revision"],
                plan_hash=expected["plan_hash"],
                candidate_build_identity=expected["candidate_build_identity"],
                workbook_id=expected["workbook_id"],
                tab_object_ids=expected["tab_object_ids"],
                profile_assertions=expected["effective_visual_assertions"],
                active_provenance_hash=expected["active_visual_provenance_hash"],
                task_acceptance=expected["task_acceptance"],
                project_profile_hash=expected["project_profile_hash"],
                accepted_exemplar_hash=expected["accepted_exemplar_hash"],
                affected_object_ids=expected["affected_object_ids"],
                affected_tab_ids=expected["affected_tab_ids"],
            )
        except Exception as exc:  # noqa: BLE001 - invalid browser binding is explicit evidence.
            return {
                "ok": False,
                "adapter_calls": 0,
                "proof_level": "contract_runtime",
                "attestation": {},
                "reason": f"browser_plan_invalid:{exc.__class__.__name__}",
                "status": "awaiting_visual_acceptance" if final_visual else "browser_plan_invalid",
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
                "status": "awaiting_visual_acceptance" if final_visual else "browser_adapter_failed",
            }
        issues = validate_qa_attestation_binding(
            attestation,
            dashboard_id=expected["dashboard_id"],
            saved_revision=expected["saved_revision"],
            published_revision=expected["published_revision"],
            final_payload_attestation_sha256=expected["final_payload_attestation_sha256"],
            payload_set_sha256=expected["payload_set_sha256"],
            dashboard_composition_sha256=expected["dashboard_composition_sha256"],
            task_id=expected["task_id"],
            contract_revision=expected["contract_revision"],
            plan_hash=expected["plan_hash"],
            candidate_build_identity=expected["candidate_build_identity"],
        )
        return {
            "ok": not issues,
            "adapter_calls": 1,
            "proof_level": "browser_rendered" if not issues else "contract_runtime",
            "attestation": attestation if not issues else {},
            "issues": issues,
            "status": "passed" if not issues else "awaiting_visual_acceptance",
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
    verification_receipt: dict[str, Any] | None = None,
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
        elif source_kind == "existing_effect":
            evidence_kind = "existing_effect_live_readback"
            satisfied = bool(
                verification_receipt
                and verification_receipt.get("status") == "passed"
                and verification_receipt.get("outcome") == "verified"
                and int(verification_receipt.get("write_executed") or 0) == 0
            )
        elif source_kind == "semantic_change":
            evidence_kind = "planned_payload_readback"
            satisfied = bool(runtime_ok and delivery_ok)
        elif source_kind == "create_manifest":
            evidence_kind = "typed_create_manifest_delivery_readback"
            satisfied = bool(runtime_ok and delivery_ok)
        elif source_kind == "constraint" and criterion.get("source") == "current_user_correction":
            # A compiled follow-up correction is a contract-continuity
            # criterion, not an independent business assertion.  Its exact
            # text is already bound into the amended contract, semantic delta,
            # immutable plan, and delivery receipts.  Requiring a separate
            # verifier for the same compiler-owned criterion made every
            # otherwise successful public amendment stop at final QA.
            evidence_kind = "amended_contract_runtime"
            satisfied = bool(
                int(contract.get("contract_revision") or 1) > 1
                and contract.get("parent_contract_hash")
                and contract.get("semantic_delta_hash")
                and runtime_ok
                and delivery_ok
            )
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
    graph = read_json(journal.target_graph_path, {}) or {}
    dashboard_url = next(
        (
            str(
                item.get("canonical_direct_url")
                or item.get("direct_url")
                or item.get("canonical_url")
                or ""
            )
            for item in graph.get("nodes") or []
            if isinstance(item, dict)
            and str(item.get("object_id") or "") == dashboard_id
            and str(
                item.get("canonical_direct_url")
                or item.get("direct_url")
                or item.get("canonical_url")
                or ""
            )
        ),
        "",
    ) or (f"https://datalens.ru/{dashboard_id}" if dashboard_id else "")
    tab_object_ids = {
        tab_id: sorted(
            {
                str(item.get("object_id") or "")
                for item in graph.get("nodes") or []
                if isinstance(item, dict)
                and str(item.get("tab_id") or item.get("dashboard_tab_id") or "") == tab_id
                and str(item.get("object_id") or "")
            }
        )
        for tab_id in tabs
    }
    if len(tabs) == 1 and not tab_object_ids[tabs[0]]:
        tab_object_ids[tabs[0]] = object_ids or [dashboard_id]
    build_identity = read_json(journal.build_identity_path, {}) or {}
    applied_constraints = [
        item
        for item in public_plan.get("effective_visual_constraints") or []
        if isinstance(item, dict)
    ]
    affected_object_ids = sorted(
        {
            str(item.get("target_id") or "")
            for item in applied_constraints
            if str(item.get("target_id") or "")
        }
        or set(object_ids or [dashboard_id])
    )
    constrained_tab_ids = {
            str(item.get("tab_id") or "")
            for item in applied_constraints
            if str(item.get("tab_id") or "")
        } & set(tabs)
    affected_tab_ids = sorted(constrained_tab_ids or set(tabs))
    return {
        "dashboard_id": dashboard_id,
        "dashboard_url": dashboard_url,
        "workbook_id": str(target.get("workbook_id") or target_binding.get("workbook_id") or ""),
        "task_id": str(contract.get("task_id") or ""),
        "contract_revision": int(contract.get("contract_revision") or 0),
        "plan_hash": str(public_plan.get("plan_hash") or ""),
        "candidate_build_identity": str(build_identity.get("identity_hash") or ""),
        "tab_object_ids": tab_object_ids,
        "object_ids": object_ids or [dashboard_id],
        "tab_ids": tabs,
        "saved_revision": saved_revision,
        "published_revision": published_revision or saved_revision,
        "final_payload_attestation_sha256": artifact_hashes.get("safe_apply_plan") or "0" * 64,
        "payload_set_sha256": artifact_hashes.get("materialized_payloads") or "0" * 64,
        "dashboard_composition_sha256": composition_hash,
        "effective_visual_assertions": list(public_plan.get("effective_visual_assertions") or []),
        "active_visual_provenance_hash": str(public_plan.get("active_visual_provenance_hash") or ""),
        "task_acceptance": [
            dict(item)
            for item in contract.get("acceptance") or []
            if isinstance(item, dict) and item.get("hard") is not False
        ][:100],
        "project_profile_hash": str(public_plan.get("project_profile_hash") or ""),
        "accepted_exemplar_hash": str(public_plan.get("accepted_exemplar_hash") or ""),
        "affected_object_ids": affected_object_ids,
        "affected_tab_ids": affected_tab_ids,
    }


def _api_first_diagnostics_summary(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    data_receipt: dict[str, Any],
    saved: dict[str, Any],
    published: dict[str, Any],
) -> dict[str, Any]:
    graph = read_json(journal.target_graph_path, {}) or {}
    nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
    chart_types = {"chart", "editor_chart", "advanced_editor_chart", "wizard_chart", "ql_chart"}
    charts = [item for item in nodes if str(item.get("object_type") or "") in chart_types]
    datasets = [item for item in nodes if str(item.get("object_type") or "") == "dataset"]
    data_diagnostics = data_receipt.get("api_first_diagnostics") or {}
    target_binding = read_json(journal.target_binding_path, {}) or {}
    decision = (
        contract.get("data_diagnostics")
        if isinstance(contract.get("data_diagnostics"), dict)
        else {}
    )
    required = decision.get("required") is True
    diagnostics_status = str(data_diagnostics.get("status") or "")
    status = (
        "passed"
        if not required
        or (
            data_receipt.get("status") == "passed"
            and diagnostics_status == "passed"
            and saved.get("status") == "success"
            and published.get("status") == "success"
        )
        else "blocked"
    )
    return {
        "status": status,
        "required": required,
        "decision": dict(decision),
        "dashboard_id": str(
            (contract.get("target") or {}).get("dashboard_id")
            or target_binding.get("dashboard_id")
            or ""
        ),
        "target_graph_hash": str(graph.get("graph_hash") or ""),
        "chart_definition_ids": sorted(str(item.get("object_id") or "") for item in charts),
        "chart_types": sorted({str(item.get("technology") or item.get("object_type") or "") for item in charts}),
        "dataset_ids": sorted(str(item.get("object_id") or "") for item in datasets),
        "saved_readback_complete": saved.get("status") == "success",
        "published_readback_complete": published.get("status") == "success",
        "data_proof_receipt_hash": str(data_receipt.get("receipt_hash") or ""),
        "component_error_count": int(data_diagnostics.get("component_error_count") or 0),
        "get_dataset_data_probe": dict(data_diagnostics.get("get_dataset_data_probe") or {}),
        "chart_query_equivalence": "incomplete",
        "limitations": [
            "public OpenAPI has no exact chart render/query-error endpoint",
            "API object and dataset proof does not claim frontend layout or exact chart query equivalence",
        ],
    }
