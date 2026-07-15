from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.sql_performance import dl_diagnose_impl


def dl_diagnose(
    mode: str,
    payload: dict[str, Any] | None = None,
    project_root: str = ".",
    max_items: int = 20,
) -> dict[str, Any]:
    """Run bounded SQL, grain, graph, performance, or optimization diagnostics."""
    return dl_diagnose_impl(mode=mode, payload=payload, project_root=project_root, max_items=max_items)
