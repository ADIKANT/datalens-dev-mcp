from __future__ import annotations

from typing import Any

from datalens_dev_mcp.local_config import load_local_config, sanitize_local_config


def dl_get_local_config(config_path: str = "", project_root: str = ".") -> dict[str, Any]:
    config = load_local_config(config_path or None, project_root=project_root)
    return {"ok": True, "config": sanitize_local_config(config)}
