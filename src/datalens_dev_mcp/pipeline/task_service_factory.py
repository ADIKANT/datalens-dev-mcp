from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.autonomous_task_service import AutonomousTaskService
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal


def create_autonomous_task_service(
    journal: ProjectJournal,
    contract: dict[str, Any],
    *,
    execution_grant: dict[str, Any],
) -> AutonomousTaskService:
    return AutonomousTaskService(journal, contract, execution_grant=execution_grant)
