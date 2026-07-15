from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.data_evidence import (
    build_data_evidence_probe_plan,
    evaluate_data_evidence,
    record_data_evidence,
)


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
