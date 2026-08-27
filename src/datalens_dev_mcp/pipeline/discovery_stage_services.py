from __future__ import annotations

from typing import Any, Callable

from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt


def persisted_discovery_stage_services(
    journal: ProjectJournal,
    contract: dict[str, Any],
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    def baseline(context: dict[str, Any]) -> dict[str, Any]:
        discovery = read_json(journal.discovery_path, {}) or {}
        target = read_json(journal.target_binding_path, {}) or {}
        graph = read_json(journal.target_graph_path, {}) or {}
        missing = []
        if target.get("source") != "live_discovery":
            missing.append("live_target_binding")
        if not graph.get("graph_hash"):
            missing.append("target_graph")
        return _receipt(
            context,
            status="blocked" if missing else "success",
            hard_requirements=["live_target_binding", "target_graph", "baseline_snapshots"],
            missing_requirements=missing,
            output_hashes={
                "target_binding": str(target.get("binding_hash") or ""),
                "target_graph": str(graph.get("graph_hash") or ""),
                "discovery": str(discovery.get("discovery_hash") or ""),
            },
            provider_calls=list(discovery.get("provider_calls") or []),
            observed_facts=[
                f"target node count={len(graph.get('nodes') or [])}",
                f"baseline count={len(discovery.get('baseline_refs') or [])}",
            ],
            reason="live target discovery is unavailable" if missing else "fresh live target baseline is bound",
        )

    def reference(context: dict[str, Any]) -> dict[str, Any]:
        reference_binding = read_json(journal.reference_binding_path, {}) or {}
        style_binding = read_json(journal.style_binding_path, {}) or {}
        missing = []
        if not reference_binding.get("binding_hash"):
            missing.append("reference_binding")
        if not style_binding.get("binding_hash"):
            missing.append("style_binding")
        return _receipt(
            context,
            status="blocked" if missing else "success",
            hard_requirements=["reference_binding", "style_binding"],
            missing_requirements=missing,
            output_hashes={
                "reference_binding": str(reference_binding.get("binding_hash") or ""),
                "style_binding": str(style_binding.get("binding_hash") or ""),
            },
            observed_facts=[
                f"reference source={reference_binding.get('source_kind', '')}",
                f"style technology={style_binding.get('technology', '')}",
            ],
            reason="exact reference/style binding is unavailable" if missing else "exact reference/style binding is persisted",
        )

    def route(context: dict[str, Any]) -> dict[str, Any]:
        target = read_json(journal.target_binding_path, {}) or {}
        style = read_json(journal.style_binding_path, {}) or {}
        technology = str(style.get("technology") or target.get("technology") or "")
        missing = [] if technology else ["target_technology"]
        return _receipt(
            context,
            status="blocked" if missing else "success",
            hard_requirements=["target_technology"],
            missing_requirements=missing,
            output_hashes={"route_binding": technology},
            observed_facts=[f"preserved technology={technology}"],
            reason="target technology is unresolved" if missing else "route is bound to fresh target technology",
        )

    def _receipt(
        context: dict[str, Any],
        *,
        status: str,
        hard_requirements: list[str],
        missing_requirements: list[str],
        output_hashes: dict[str, str],
        reason: str,
        provider_calls: list[dict[str, Any]] | None = None,
        observed_facts: list[str] | None = None,
    ) -> dict[str, Any]:
        return build_stage_receipt(
            task_id=journal.task_id,
            contract_hash=str(contract.get("contract_hash") or ""),
            transition=str(context.get("transition") or ""),
            status=status,
            build_identity_hash=str(context.get("build_identity_hash") or ""),
            target_binding_hash=str(context.get("target_binding_hash") or ""),
            output_hashes=output_hashes,
            provider_calls=provider_calls or [],
            hard_requirements=hard_requirements,
            missing_requirements=missing_requirements,
            reason=reason,
            observed_facts=observed_facts or [],
        )

    return {
        "read_baseline": baseline,
        "bind_reference": reference,
        "bind_route": route,
    }
