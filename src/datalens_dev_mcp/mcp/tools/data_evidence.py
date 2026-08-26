from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.data_evidence import (
    build_data_evidence_probe_plan,
    diagnose_empty_dataset_result,
    evaluate_data_evidence,
    record_data_evidence,
)
from datalens_dev_mcp.pipeline.data_proof_planner import prove_dataset_data
from datalens_dev_mcp.mcp.tools.rpc import dl_get_dataset_data


def dl_build_data_evidence_probe_plan(
    project_root: str = ".",
    provider_config: dict[str, Any] | None = None,
    probe_operation: str = "table_discovery",
    table_ref: str = "",
    columns: list[str] | None = None,
    where_clause: str = "",
    cte_sql: str = "",
    graph_config: dict[str, Any] | None = None,
    sample_limit: int = 50,
    environment: str = "dev",
    artifact_name: str = "latest",
) -> dict[str, Any]:
    return build_data_evidence_probe_plan(
        project_root=project_root,
        provider_config=provider_config,
        probe_operation=probe_operation,
        table_ref=table_ref,
        columns=columns,
        where_clause=where_clause,
        cte_sql=cte_sql,
        graph_config=graph_config,
        sample_limit=sample_limit,
        environment=environment,
        artifact_name=artifact_name,
    )


def dl_record_data_evidence(
    project_root: str = ".",
    evidence: dict[str, Any] | None = None,
    artifact_name: str = "latest",
) -> dict[str, Any]:
    return record_data_evidence(project_root=project_root, evidence=evidence, artifact_name=artifact_name)


def dl_evaluate_data_evidence(
    table_ref: str = "",
    inventory: dict[str, Any] | None = None,
    targeted_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate_data_evidence(table_ref=table_ref, inventory=inventory, targeted_evidence=targeted_evidence)


def dl_preview_dataset_data(
    dataset_id: str,
    columns: list[str],
    workbook_id: str = "",
    filters: list[dict[str, Any]] | None = None,
    params: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
    max_pages: int = 1,
    tie_breaker_fields: list[str] | None = None,
    inline_row_limit: int = 20,
    inline_byte_budget: int = 8_000,
    project_root: str = ".",
    artifact_name: str = "dataset-preview",
) -> dict[str, Any]:
    return dl_get_dataset_data(
        dataset_id=dataset_id,
        columns=columns,
        workbook_id=workbook_id,
        filters=filters,
        params=params,
        sort=sort,
        limit=limit,
        offset=offset,
        max_pages=max_pages,
        tie_breaker_fields=tie_breaker_fields,
        inline_row_limit=inline_row_limit,
        inline_byte_budget=inline_byte_budget,
        project_root=project_root,
        artifact_name=artifact_name,
    )


def dl_prove_dataset_data(
    spec: dict[str, Any],
    project_root: str = ".",
    artifact_name: str = "data-proof",
) -> dict[str, Any]:
    """Evaluate a declarative, bounded set of typed assertions over getDatasetData rows."""
    return prove_dataset_data(spec, project_root=project_root, artifact_name=artifact_name)


def dl_diagnose_empty_dataset_result(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    return diagnose_empty_dataset_result(spec)
