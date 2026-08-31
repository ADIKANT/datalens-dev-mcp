from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.dataset_context_profile import build_dataset_context_profile
from datalens_dev_mcp.pipeline.dataset_data_failures import classify_dataset_data_failure
from datalens_dev_mcp.pipeline.dataset_data_normalizer import normalize_dataset_data_response
from datalens_dev_mcp.pipeline.dataset_parameters import extract_dashboard_parameter_defaults
from datalens_dev_mcp.pipeline.dataset_probe_planner import DatasetProbePlanner
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


class TaskDatasetContextService:
    def __init__(
        self,
        journal: ProjectJournal,
        contract: dict[str, Any],
        *,
        client: Any | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.journal = journal
        self.contract = contract
        if client is None:
            from datalens_dev_mcp.api.client import DataLensApiClient
            from datalens_dev_mcp.config import DataLensConfig

            client = DataLensApiClient(DataLensConfig.from_env())
        self.client = client
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))

    @property
    def profile_path(self) -> Path:
        return self.journal.root / "data" / "context-profile.json"

    @property
    def proof_plan_path(self) -> Path:
        return self.journal.root / "plans" / "data-proof-plan.json"

    def persist_not_applicable(self, *, reason: str) -> dict[str, Any]:
        """Persist bounded proof artifacts when a live dataset probe is not required."""

        graph = read_json(self.journal.target_graph_path, {}) or {}
        dataset = next(
            (
                item
                for item in graph.get("nodes") or []
                if isinstance(item, dict) and item.get("object_type") == "dataset"
            ),
            {},
        )
        observed_at = _utc_now()
        query_set_hash = canonical_hash(
            {
                "status": "not_applicable",
                "reason": reason,
                "contract_hash": str(self.contract.get("contract_hash") or ""),
                "target_graph_hash": str(graph.get("graph_hash") or ""),
            }
        )
        schema_hash = str(dataset.get("schema_hash") or canonical_hash([]))
        plan = {
            "schema_id": "dataset_probe_plan",
            "status": "not_applicable",
            "reason": reason,
            "dataset_id": str(dataset.get("object_id") or ""),
            "dataset_revision": str(dataset.get("saved_revision") or ""),
            "dataset_schema_hash": schema_hash,
            "query_set_hash": query_set_hash,
            "queries": [],
            "provider_calls_required": False,
        }
        plan["plan_hash"] = canonical_hash(plan)
        profile = build_dataset_context_profile(
            dataset_id=str(dataset.get("object_id") or ""),
            workbook_id=str((self.contract.get("target") or {}).get("workbook_id") or ""),
            dataset_revision=str(dataset.get("saved_revision") or ""),
            query_set_hash=query_set_hash,
            schema_hash=schema_hash,
            field_catalog=[],
            rows=[],
            pages_read=0,
            requested_limit=0,
            deterministic=False,
            limitations=[reason, "dataset probe not applicable"],
            observed_at=observed_at,
            proof_level="source_static",
            fallback_kind="not_applicable",
        )
        write_json(self.proof_plan_path, plan)
        write_json(self.profile_path, profile)
        return {"profile": profile, "query_plan": plan, "provider_calls": []}

    def acquire(self, *, fresh: bool = False, mode: str = "context_probe") -> dict[str, Any]:
        graph = read_json(self.journal.target_graph_path, {}) or {}
        parameter_defaults = (
            {}
            if mode == "diagnostic_probe"
            else extract_dashboard_parameter_defaults(
                [
                    read_json(path, {}) or {}
                    for path in sorted((self.journal.root / "snapshots").glob("baseline-*.json"))
                ]
            )
        )
        planned = DatasetProbePlanner().plan(
            self.contract,
            graph,
            mode=mode,
            parameter_defaults=parameter_defaults,
        )
        if not planned.get("ok"):
            return {"ok": False, "status": "blocked", "issues": planned.get("issues") or []}
        plan = dict(planned["plan"])
        plan_path = (
            self.proof_plan_path
            if mode == "context_probe"
            else self.journal.root / "plans" / f"{mode.replace('_', '-')}-plan.json"
        )
        write_json(plan_path, deepcopy(plan))
        query = dict(plan["queries"][0])
        cache_key = canonical_hash(
            {
                "operation_contract_hash": self.contract.get("contract_hash"),
                "api_contract_hash": query.get("api_contract_hash"),
                "target_binding_hash": (read_json(self.journal.target_binding_path, {}) or {}).get("binding_hash"),
                "dataset_id": plan.get("dataset_id"),
                "dataset_revision": plan.get("dataset_revision"),
                "dataset_schema_hash": plan.get("dataset_schema_hash"),
                "query_hash": query.get("query_hash"),
            }
        )
        cache_path = self.journal.root / "data" / "cache" / f"{cache_key}.json"
        cached = read_json(cache_path, {}) or {}
        cache_hit = bool(
            not fresh
            and cached.get("cache_key") == cache_key
            and float(cached.get("expires_epoch") or 0) >= time.time()
            and isinstance(cached.get("normalized_page"), dict)
        )
        provider_calls: list[dict[str, Any]] = []
        fallback_kind = ""
        if cache_hit:
            normalized = dict(cached["normalized_page"])
            observed_at = str(cached.get("observed_at") or normalized.get("observed_at") or _utc_now())
        else:
            payload = dict(query.get("payload") or {})
            observed_at = _utc_now()
            try:
                response = self.client.rpc_readonly("getDatasetData", payload)
                normalized = normalize_dataset_data_response(
                    response,
                    request_hash=str(query.get("query_hash") or canonical_hash(payload)),
                    observed_at=observed_at,
                )
            except Exception as exc:  # noqa: BLE001 - experimental provider boundary is explicit evidence.
                normalized = {
                    "schema_id": "normalized_dataset_data_page",
                    "request_hash": str(query.get("query_hash") or canonical_hash(payload)),
                    "schema_hash": str(plan.get("dataset_schema_hash") or ""),
                    "observed_at": observed_at,
                    "schema": list(plan.get("field_catalog") or []),
                    "typed_rows": [],
                    "plain_rows": [],
                    "row_count": 0,
                }
                failure_family = classify_dataset_data_failure(exc)
                fallback_kind = f"dataset_schema_only:{failure_family}"
                provider_calls.append(
                    {
                        "method": "getDatasetData",
                        "request_hash": canonical_hash(payload),
                        "status": "unavailable",
                        "error_family": failure_family,
                    }
                )
            else:
                response_hash = canonical_hash(response)
                provider_calls.append(
                    {
                        "method": "getDatasetData",
                        "request_hash": canonical_hash(payload),
                        "response_hash": response_hash,
                        "status": "success",
                    }
                )
                raw_path = self.journal.root / "data" / "raw" / f"page-{cache_key[:20]}.json"
                write_json(raw_path, deepcopy(response))
                write_json(
                    cache_path,
                    {
                        "schema_id": "dataset_context_cache_entry",
                        "cache_key": cache_key,
                        "observed_at": observed_at,
                        "expires_epoch": time.time() + self.cache_ttl_seconds,
                        "normalized_page": normalized,
                        "raw_artifact_uri": self.journal.receipt_uri(
                            raw_path.relative_to(self.journal.root).as_posix()
                        ),
                    },
                )

        rows = list(normalized.get("plain_rows") or [])
        row_count = len(rows)
        cell_count = sum(len(row) for row in rows)
        byte_count = len(
            json.dumps(normalized.get("typed_rows") or [], ensure_ascii=False, default=str).encode("utf-8")
        )
        budget = plan["budget"]
        exhausted = (
            row_count > int(budget["max_rows_total"])
            or cell_count > int(budget["max_cells_total"])
            or byte_count > int(budget["max_bytes_total"])
        )
        limitations = list(plan.get("limitations") or [])
        if exhausted:
            limitations.append("data context budget exhausted")
        if fallback_kind:
            limitations.extend(["getDatasetData unavailable", "schema-only planning fallback"])
        profile = build_dataset_context_profile(
            dataset_id=str(plan.get("dataset_id") or ""),
            workbook_id=str((self.contract.get("target") or {}).get("workbook_id") or ""),
            dataset_revision=str(plan.get("dataset_revision") or ""),
            query_set_hash=str(plan.get("query_set_hash") or ""),
            schema_hash=str(normalized.get("schema_hash") or plan.get("dataset_schema_hash") or ""),
            field_catalog=list(plan.get("field_catalog") or []),
            rows=rows,
            pages_read=0 if fallback_kind else 1,
            requested_limit=int((query.get("payload") or {}).get("limit") or 100),
            deterministic=bool((query.get("paging") or {}).get("deterministic")),
            limitations=limitations,
            observed_at=observed_at,
            proof_level="source_static" if fallback_kind else "live_read_only_api",
            fallback_kind=fallback_kind,
        )
        profile_path = (
            self.profile_path
            if mode == "context_probe"
            else self.journal.root / "evidence" / f"{mode.replace('_', '-')}-context-profile.json"
        )
        write_json(profile_path, deepcopy(profile))
        return {
            "ok": not exhausted,
            "status": "blocked_budget" if exhausted else "completed",
            "profile": profile,
            "query_plan": plan,
            "provider_calls": provider_calls,
            "cache_hit": cache_hit,
            "raw_rows_inline": False,
            "budget_observed": {"rows": row_count, "cells": cell_count, "bytes": byte_count},
            "normalized_page": normalized,
            "profile_path": profile_path.relative_to(self.journal.root).as_posix(),
            "plan_path": plan_path.relative_to(self.journal.root).as_posix(),
        }

    def stage_handler(self, context: dict[str, Any]) -> dict[str, Any]:
        result = self.acquire(fresh=False, mode="context_probe")
        profile = dict(result.get("profile") or {})
        plan = dict(result.get("query_plan") or {})
        status = "success" if result.get("ok") else "blocked"
        missing = [] if result.get("ok") else ["bounded_dataset_context"]
        return build_stage_receipt(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status=status,
            proof_level=str(profile.get("proof_level") or "source_static"),
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            input_hashes={
                "target_graph": str((read_json(self.journal.target_graph_path, {}) or {}).get("graph_hash") or ""),
            },
            output_hashes={
                "dataset_context_profile": str(profile.get("profile_hash") or ""),
                "dataset_query_set": str(plan.get("query_set_hash") or ""),
                "dataset_schema": str(profile.get("schema_hash") or ""),
            },
            provider_calls=list(result.get("provider_calls") or []),
            hard_requirements=["bounded_dataset_context", "sample_claim_limitations", "raw_rows_externalized"],
            missing_requirements=missing,
            reason=(
                "bounded dataset context profile is persisted"
                if result.get("ok")
                else "dataset context budget was exhausted or planning failed"
            ),
            observed_facts=[
                f"rows observed={((profile.get('sample_scope') or {}).get('rows_observed', 0))}",
                f"dataset semantics={profile.get('dataset_data_semantics', 'unknown_experimental')}",
                f"cache hit={bool(result.get('cache_hit'))}",
            ],
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
