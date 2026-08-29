from __future__ import annotations

from typing import Any

from datalens_dev_mcp.serialization import stable_sha256
from copy import deepcopy


def build_cache_marker(
    *,
    source: str,
    version: str = "",
    content_hash: str = "",
    freshness: str = "current",
    inputs: Any = None,
) -> dict[str, Any]:
    identity = deepcopy({
        "source": source,
        "source_revision": version,
        "content_hash": content_hash,
        "freshness": freshness,
        "inputs": inputs,
    })
    return {"schema_id": "datalens_cache_marker", **identity, "marker": stable_sha256(identity)}


def cache_marker_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(left.get("marker")) and left.get("marker") == right.get("marker")
