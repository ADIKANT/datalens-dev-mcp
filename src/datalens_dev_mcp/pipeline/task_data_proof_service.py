from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.request_compiler import project_method_request
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.assertion_spec_compiler import AssertionSpecCompiler
from datalens_dev_mcp.pipeline.data_assertions import evaluate_data_assertions, unexpected_empty_diagnostics
from datalens_dev_mcp.pipeline.data_sample_budget import sensitive_field_guids
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.validators.redaction import sanitize_value


class TaskDataProofService:
    def __init__(
        self,
        journal: ProjectJournal,
        contract: dict[str, Any],
        *,
        client: Any | None = None,
    ) -> None:
        self.journal = journal
        self.contract = contract
        self.context_service = TaskDatasetContextService(journal, contract, client=client)

    @property
    def receipt_path(self) -> Path:
        return self.journal.root / "evidence" / "data-proof-receipt.json"

    @property
    def plan_path(self) -> Path:
        return self.journal.root / "plans" / "task-data-proof-plan.json"

    def execute(self) -> dict[str, Any]:
        public_plan = read_json(self.journal.root / "plans" / "plan.json", {}) or {}
        planning_profile = read_json(self.journal.root / "data" / "context-profile.json", {}) or {}
        target_binding = read_json(self.journal.target_binding_path, {}) or {}
        plan_binding = read_json(self.journal.root / "plans" / "plan-binding.json", {}) or {}
        binding_issues = _binding_issues(public_plan, planning_profile, target_binding, plan_binding)
        if binding_issues:
            return self._write_receipt(
                status="blocked",
                proof_level="source_static",
                fallback_kind="stale_planning_binding",
                assertions=[],
                provider_calls=[],
                limitations=binding_issues,
                live_data_verified=False,
                assertion_plan_hash="",
                schema_hash="",
            )
        diagnostics_decision = (
            self.contract.get("data_diagnostics")
            if isinstance(self.contract.get("data_diagnostics"), dict)
            else {}
        )
        if diagnostics_decision.get("required") is False:
            reason = "dataset proof is not applicable because the compiled change has no data impact"
            query_plan = read_json(self.context_service.proof_plan_path, {}) or {}
            return self._write_receipt(
                status="passed",
                proof_level="source_static",
                fallback_kind="not_applicable",
                assertions=[],
                provider_calls=[],
                limitations=[reason, "validateDataset and getDatasetData were intentionally not called"],
                live_data_verified=False,
                assertion_plan_hash=str(query_plan.get("plan_hash") or ""),
                schema_hash=str(planning_profile.get("schema_hash") or ""),
                api_first_diagnostics={
                    "status": "not_required",
                    "decision": dict(diagnostics_decision),
                    "component_error_count": 0,
                    "component_error_families": [],
                    "provider_calls": [],
                    "limitations": [],
                    "chart_query_equivalence": "not_applicable",
                },
            )
        api_first_diagnostics = self._api_first_structural_diagnostics()
        if api_first_diagnostics.get("status") in {"blocked", "failed"}:
            return self._write_receipt(
                status="blocked",
                proof_level="live_read_only_api",
                fallback_kind="api_first_dataset_validation_failed",
                assertions=[],
                provider_calls=list(api_first_diagnostics.get("provider_calls") or []),
                limitations=list(api_first_diagnostics.get("limitations") or []),
                live_data_verified=False,
                assertion_plan_hash="",
                schema_hash="",
                api_first_diagnostics=api_first_diagnostics,
            )
        acquired = self.context_service.acquire(fresh=True, mode="assertion_probe")
        probe_plan = dict(acquired.get("query_plan") or {})
        assertion_plan = AssertionSpecCompiler().compile(
            self.contract,
            probe_plan,
            planning_profile=planning_profile,
            target_binding=target_binding,
        )
        write_json(self.plan_path, deepcopy(assertion_plan))
        if not assertion_plan.get("ok"):
            return self._write_receipt(
                status="blocked",
                proof_level="source_static",
                fallback_kind="assertion_plan_invalid",
                assertions=[],
                provider_calls=list(acquired.get("provider_calls") or []),
                limitations=list(assertion_plan.get("issues") or []),
                live_data_verified=False,
                assertion_plan_hash=str(assertion_plan.get("plan_hash") or ""),
                schema_hash="",
                api_first_diagnostics=api_first_diagnostics,
            )
        profile = dict(acquired.get("profile") or {})
        normalized = dict(acquired.get("normalized_page") or {})
        live = profile.get("proof_level") == "live_read_only_api" and not profile.get("fallback_kind")
        schema_hash = str(normalized.get("schema_hash") or profile.get("schema_hash") or "")
        planning_probe_was_applicable = str(planning_profile.get("fallback_kind") or "") != "not_applicable"
        if (
            live
            and planning_probe_was_applicable
            and schema_hash != str(planning_profile.get("schema_hash") or "")
        ):
            return self._write_receipt(
                status="blocked",
                proof_level="live_read_only_api",
                fallback_kind="schema_drift_requires_replan",
                assertions=[],
                provider_calls=list(acquired.get("provider_calls") or []),
                limitations=["dataset schema changed after plan materialization; replan is required"],
                live_data_verified=False,
                assertion_plan_hash=str(assertion_plan.get("plan_hash") or ""),
                schema_hash=schema_hash,
                api_first_diagnostics=api_first_diagnostics,
            )
        rows = list(normalized.get("plain_rows") or []) if live else []
        schema = list(normalized.get("schema") or probe_plan.get("field_catalog") or [])
        limit = int((assertion_plan.get("sample") or {}).get("limit") or 100)
        paging = {
            "complete": bool(live and len(rows) < limit),
            "pages_read": 1 if live else 0,
            "bounded_sample": True,
        }
        evaluated = (
            evaluate_data_assertions(
                assertions=list(assertion_plan.get("assertions") or []),
                schema=schema,
                rows=rows,
                paging=paging,
            )
            if live
            else _insufficient_assertions(assertion_plan)
        )
        evaluated["results"] = _bind_assertion_results(
            list(assertion_plan.get("assertions") or []),
            list(evaluated.get("results") or []),
        )
        sensitive_kinds = _sensitive_assertion_kinds(
            list(assertion_plan.get("assertions") or []),
            sensitive_field_guids(schema),
        )
        expected_empty = any(item.get("kind") == "expected_empty" for item in assertion_plan.get("assertions") or [])
        provider_calls = list(acquired.get("provider_calls") or [])
        provider_calls = [
            *list(api_first_diagnostics.get("provider_calls") or []),
            *provider_calls,
        ]
        query = next(
            (dict(item) for item in probe_plan.get("queries") or [] if isinstance(item, dict)),
            {},
        )
        query_payload = dict(query.get("payload") or {})
        api_first_diagnostics = {
            **api_first_diagnostics,
            "status": (
                "passed"
                if api_first_diagnostics.get("status") in {"passed", "not_required"}
                and profile.get("proof_level") == "live_read_only_api"
                and not profile.get("fallback_kind")
                else "blocked"
            ),
            "get_dataset_data_probe": {
                "request_hash": str(query.get("query_hash") or canonical_hash(query_payload)),
                "field_count": len(query_payload.get("columns") or []),
                "filter_count": len(query_payload.get("filters") or []),
                "param_count": len(query_payload.get("params") or []),
                "sort_count": len(query_payload.get("sort") or []),
                "limit": int(query_payload.get("limit") or 0),
                "outcome": (
                    "api_runtime_pass"
                    if profile.get("proof_level") == "live_read_only_api" and not profile.get("fallback_kind")
                    else "api_runtime_error_observed"
                ),
            },
        }
        diagnostics: list[dict[str, Any]] = []
        if live and not rows and not expected_empty:
            diagnostic = self.context_service.acquire(fresh=True, mode="diagnostic_probe")
            provider_calls.extend(list(diagnostic.get("provider_calls") or []))
            diagnostic_profile = dict(diagnostic.get("profile") or {})
            diagnostic_page = dict(diagnostic.get("normalized_page") or {})
            diagnostic_live = diagnostic_profile.get(
                "proof_level"
            ) == "live_read_only_api" and not diagnostic_profile.get("fallback_kind")
            diagnostic_rows = list(diagnostic_page.get("plain_rows") or []) if diagnostic_live else []
            diagnostic_plan = dict(diagnostic.get("query_plan") or {})
            diagnostic_query = next(
                (dict(item) for item in diagnostic_plan.get("queries") or [] if isinstance(item, dict)),
                {},
            )
            diagnostics.append(
                {
                    "check": "unfiltered_dataset_probe",
                    "mode": "diagnostic_probe",
                    "status": (
                        "non_empty_without_parameters"
                        if diagnostic_rows
                        else "still_empty"
                        if diagnostic_live
                        else "probe_unavailable"
                    ),
                    "row_count": len(diagnostic_rows),
                    "query_hash": str(diagnostic_query.get("query_hash") or ""),
                    "requested_parameter_count": len((diagnostic_query.get("payload") or {}).get("params") or []),
                    "raw_rows_inline": False,
                }
            )
            diagnostics.extend(unexpected_empty_diagnostics(assertion_plan))
        limitations = list((profile.get("sample_scope") or {}).get("limitations") or [])
        if not live:
            limitations.extend(["fresh getDatasetData proof unavailable", "dataset schema only"])
        if diagnostics:
            limitations.append("unexpected empty result requires diagnostic probes")
        status = "passed" if live and evaluated.get("ok") else str(evaluated.get("status") or "insufficient_evidence")
        return self._write_receipt(
            status=status,
            proof_level="live_read_only_api" if live else "source_static",
            fallback_kind=str(profile.get("fallback_kind") or ""),
            assertions=list(evaluated.get("results") or []),
            provider_calls=provider_calls,
            limitations=limitations,
            live_data_verified=bool(live and evaluated.get("ok")),
            assertion_plan_hash=str(assertion_plan.get("plan_hash") or ""),
            schema_hash=schema_hash,
            diagnostics=diagnostics,
            row_count=len(rows),
            paging=paging,
            sensitive_assertion_kinds=sensitive_kinds,
            api_first_diagnostics=api_first_diagnostics,
        )

    def _api_first_structural_diagnostics(self) -> dict[str, Any]:
        decision = (
            self.contract.get("data_diagnostics")
            if isinstance(self.contract.get("data_diagnostics"), dict)
            else {}
        )
        if decision.get("required") is not True or decision.get("validate_dataset") is not True:
            return {
                "status": "not_required",
                "decision": dict(decision),
                "component_error_count": 0,
                "component_error_families": [],
                "provider_calls": [],
                "limitations": [],
                "chart_query_equivalence": "incomplete",
            }
        graph = read_json(self.journal.target_graph_path, {}) or {}
        datasets = [
            item
            for item in graph.get("nodes") or []
            if isinstance(item, dict) and str(item.get("object_type") or "") == "dataset"
        ]
        chart_methods = {
            "wizard_chart": "getWizardChart",
            "editor_chart": "getEditorChart",
            "advanced_editor_chart": "getEditorChart",
            "ql_chart": "getQLChart",
            "chart": "getEditorChart",
        }
        charts = [
            item
            for item in graph.get("nodes") or []
            if isinstance(item, dict) and str(item.get("object_type") or "") in chart_methods
        ]
        workbook_id = str((self.contract.get("target") or {}).get("workbook_id") or "")
        provider_calls: list[dict[str, Any]] = []
        component_errors: list[dict[str, Any]] = []
        limitations = [
            "public OpenAPI has no exact chart render/query-error endpoint",
            "bounded getDatasetData is not claimed equivalent to the final chart query",
        ]
        chart_definition_hashes: dict[str, str] = {}
        for node in charts:
            chart_id = str(node.get("object_id") or "")
            method = chart_methods[str(node.get("object_type") or "")]
            chart_payload = {"chartId": chart_id, "branch": "saved"}
            try:
                chart_definition = self.context_service.client.rpc_readonly(method, chart_payload)
            except Exception as exc:  # noqa: BLE001 - typed provider boundary.
                provider_calls.append(
                    {
                        "method": method,
                        "request_hash": canonical_hash(chart_payload),
                        "status": "unavailable",
                        "error_family": exc.__class__.__name__,
                    }
                )
                limitations.append(f"{method} unavailable for {chart_id}")
                continue
            response_hash = canonical_hash(chart_definition)
            chart_definition_hashes[chart_id] = response_hash
            provider_calls.append(
                {
                    "method": method,
                    "request_hash": canonical_hash(chart_payload),
                    "response_hash": response_hash,
                    "status": "success",
                }
            )
        for node in datasets:
            dataset_id = str(node.get("object_id") or "")
            read_payload: dict[str, Any] = {"datasetId": dataset_id}
            if workbook_id:
                read_payload["workbookId"] = workbook_id
            try:
                readback = self.context_service.client.rpc_readonly("getDataset", read_payload)
            except Exception as exc:  # noqa: BLE001 - typed provider boundary.
                provider_calls.append(
                    {
                        "method": "getDataset",
                        "request_hash": canonical_hash(read_payload),
                        "status": "unavailable",
                        "error_family": exc.__class__.__name__,
                    }
                )
                limitations.append(f"getDataset unavailable for {dataset_id}")
                continue
            provider_calls.append(
                {
                    "method": "getDataset",
                    "request_hash": canonical_hash(read_payload),
                    "response_hash": canonical_hash(readback),
                    "status": "success",
                }
            )
            dataset_payload = _dataset_payload(readback)
            compiled = project_method_request(
                "validateDataset",
                dataset_payload,
                object_type="dataset",
                operation="validate",
                object_id=dataset_id,
                workbook_id=workbook_id,
                mode="validate",
            )
            if not compiled.get("ok"):
                provider_calls.append(
                    {
                        "method": "validateDataset",
                        "status": "blocked_before_provider",
                        "request_hash": str(compiled.get("final_request_sha256") or ""),
                    }
                )
                limitations.extend(str(item) for item in compiled.get("issues") or [])
                continue
            validate_payload = dict(compiled.get("payload") or {})
            try:
                validation = self.context_service.client.rpc_readonly(
                    "validateDataset",
                    validate_payload,
                )
            except Exception as exc:  # noqa: BLE001 - typed provider boundary.
                provider_calls.append(
                    {
                        "method": "validateDataset",
                        "request_hash": canonical_hash(validate_payload),
                        "status": "unavailable",
                        "error_family": exc.__class__.__name__,
                    }
                )
                limitations.append(f"validateDataset unavailable for {dataset_id}")
                continue
            provider_calls.append(
                {
                    "method": "validateDataset",
                    "request_hash": canonical_hash(validate_payload),
                    "response_hash": canonical_hash(validation),
                    "status": "success",
                }
            )
            component_errors.extend(_component_error_projection(validation, dataset_id=dataset_id))
        unavailable = any(item.get("status") != "success" for item in provider_calls)
        return {
            "status": "failed" if component_errors else "blocked" if unavailable else "passed",
            "decision": dict(decision),
            "dataset_ids": sorted(str(item.get("object_id") or "") for item in datasets),
            "chart_definition_ids": sorted(chart_definition_hashes),
            "chart_definition_hashes": dict(sorted(chart_definition_hashes.items())),
            "component_error_count": len(component_errors),
            "component_error_families": sorted(
                {str(item.get("family") or "unknown") for item in component_errors}
            ),
            "component_errors": component_errors,
            "provider_calls": provider_calls,
            "limitations": sorted(set(limitations)),
            "chart_query_equivalence": "incomplete",
        }

    def _write_receipt(
        self,
        *,
        status: str,
        proof_level: str,
        fallback_kind: str,
        assertions: list[dict[str, Any]],
        provider_calls: list[dict[str, Any]],
        limitations: list[str],
        live_data_verified: bool,
        assertion_plan_hash: str,
        schema_hash: str,
        diagnostics: list[dict[str, Any]] | None = None,
        row_count: int = 0,
        paging: dict[str, Any] | None = None,
        sensitive_assertion_kinds: set[str] | None = None,
        api_first_diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_binding = read_json(self.journal.target_binding_path, {}) or {}
        planning_profile = read_json(self.journal.root / "data" / "context-profile.json", {}) or {}
        payload = {
            "schema_id": "task_data_proof_receipt",
            "receipt_version": 1,
            "task_id": self.journal.task_id,
            "contract_hash": str(self.contract.get("contract_hash") or ""),
            "target_binding_hash": str(target_binding.get("binding_hash") or ""),
            "planning_profile_hash": str(planning_profile.get("profile_hash") or ""),
            "planning_query_set_hash": str(planning_profile.get("query_set_hash") or ""),
            "assertion_plan_hash": assertion_plan_hash,
            "schema_hash": schema_hash,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "fresh": True,
            "proof_level": proof_level,
            "fallback_kind": fallback_kind,
            "live_data_verified": live_data_verified,
            "dataset_data_semantics": "unknown_experimental",
            "api_first_diagnostics": sanitize_value(api_first_diagnostics or {
                "status": "not_required",
                "component_error_count": 0,
                "component_error_families": [],
                "provider_calls": [],
                "limitations": [],
                "chart_query_equivalence": "incomplete",
            }),
            "status": status,
            "assertions": _sanitize_assertions(assertions, sensitive_assertion_kinds or set()),
            "provider_calls": sanitize_value(provider_calls),
            "row_count": int(row_count),
            "paging": dict(paging or {}),
            "unexpected_empty_diagnostics": sanitize_value(diagnostics or []),
            "limitations": sorted({str(item) for item in limitations if str(item)}),
            "raw_rows_inline": False,
        }
        payload["receipt_hash"] = canonical_hash(payload)
        write_json(self.receipt_path, payload)
        return payload


def _dataset_payload(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else response
    dataset = result.get("dataset") if isinstance(result, dict) and isinstance(result.get("dataset"), dict) else result
    return dict(dataset) if isinstance(dataset, dict) else {}


def _component_error_projection(value: Any, *, dataset_id: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"component_errors", "componentErrors"} and isinstance(nested, (dict, list)):
                items = nested if isinstance(nested, list) else [nested]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    family = str(
                        item.get("code")
                        or item.get("type")
                        or item.get("kind")
                        or item.get("component")
                        or "unknown"
                    )
                    errors.append(
                        {
                            "dataset_id": dataset_id,
                            "family": family[:160],
                            "error_hash": canonical_hash(item),
                        }
                    )
            else:
                errors.extend(_component_error_projection(nested, dataset_id=dataset_id))
    elif isinstance(value, list):
        for nested in value:
            errors.extend(_component_error_projection(nested, dataset_id=dataset_id))
    return errors


def _binding_issues(
    public_plan: dict[str, Any],
    planning_profile: dict[str, Any],
    target_binding: dict[str, Any],
    plan_binding: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if public_plan.get("dataset_context_profile_hash") != planning_profile.get("profile_hash"):
        issues.append("planning context profile hash is stale")
    if public_plan.get("query_set_hash") != planning_profile.get("query_set_hash"):
        issues.append("planning query set hash is stale")
    if public_plan.get("dataset_schema_hash") != planning_profile.get("schema_hash"):
        issues.append("planning dataset schema hash is stale")
    if not target_binding.get("binding_hash"):
        issues.append("target binding is missing")
    if plan_binding.get("target_binding_hash") != target_binding.get("binding_hash"):
        issues.append("target binding changed after plan materialization; replan is required")
    if public_plan.get("plan_binding_hash") != plan_binding.get("binding_hash"):
        issues.append("public plan binding is stale")
    return issues


def _insufficient_assertions(plan: dict[str, Any]) -> dict[str, Any]:
    results = [
        {
            "kind": str(item.get("kind") or "unknown"),
            "status": "insufficient_evidence",
            "explanation": "Fresh rows were unavailable; static schema cannot prove this assertion.",
            "metrics": {},
        }
        for item in plan.get("assertions") or []
    ]
    return {"ok": False, "status": "insufficient_evidence", "results": results}


def _bind_assertion_results(
    assertions: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bound: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        assertion = assertions[index] if index < len(assertions) else {}
        item = dict(result)
        if isinstance(assertion.get("acceptance_index"), int):
            item["acceptance_index"] = int(assertion["acceptance_index"])
        if assertion.get("criterion_hash"):
            item["criterion_hash"] = str(assertion["criterion_hash"])
        bound.append(item)
    return bound


def _sanitize_assertions(
    assertions: list[dict[str, Any]],
    sensitive_kinds: set[str],
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in assertions:
        value = sanitize_value(item)
        if str(item.get("kind") or "") in sensitive_kinds:
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            value["metrics"] = {
                key: sanitize_value(metric)
                for key, metric in metrics.items()
                if key.endswith("_count") or key in {"sample_only", "paging_complete"}
            }
            value["metrics"]["values_redacted_or_hashed"] = True
        sanitized.append(value)
    return sanitized


def _sensitive_assertion_kinds(
    assertions: list[dict[str, Any]],
    sensitive_fields: set[str],
) -> set[str]:
    kinds: set[str] = set()
    for item in assertions:
        fields = item.get("fields") if isinstance(item.get("fields"), list) else [item.get("field")]
        referenced = {str(field) for field in fields if str(field)}
        referenced.update(
            str(item.get(key) or "") for key in ("numerator", "denominator", "ratio") if str(item.get(key) or "")
        )
        if referenced & sensitive_fields:
            kinds.add(str(item.get("kind") or "unknown"))
    return kinds
