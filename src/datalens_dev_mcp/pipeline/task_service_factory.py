from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.autonomous_task_service import AutonomousTaskService
from datalens_dev_mcp.pipeline.discovery_stage_services import persisted_discovery_stage_services
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_planning_stage_services import task_planning_stage_services


def create_autonomous_task_service(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    execution_grant: dict[str, Any],
    build_identity_hash: str,
    target_binding_hash: str,
    stage_services: dict[str, Any] | None = None,
) -> AutonomousTaskService:
    resolved_services = persisted_discovery_stage_services(journal, contract)
    resolved_services.update(task_planning_stage_services(journal, contract))
    resolved_services.update(stage_services or {})
    return AutonomousTaskService(
        journal,
        contract,
        execution_grant=execution_grant,
        build_identity_hash=build_identity_hash,
        target_binding_hash=target_binding_hash,
        stage_services=resolved_services,
    )
