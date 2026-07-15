from __future__ import annotations

from typing import Any

from datalens_dev_mcp.knowledge.reference import build_reference_response


def dl_reference(
    mode: str = "search",
    query: str = "",
    name: str = "",
    limit: int = 5,
    max_chars: int = 6000,
    project_root: str = ".",
) -> dict[str, Any]:
    return build_reference_response(
        mode=mode,
        query=query,
        name=name,
        limit=limit,
        max_chars=max_chars,
        project_root=project_root,
    )
