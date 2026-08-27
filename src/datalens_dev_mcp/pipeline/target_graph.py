from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


TARGET_GRAPH_SCHEMA_ID = "datalens_target_graph"


def build_target_graph(
    *,
    root_ids: list[str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    provider_calls: list[dict[str, Any]],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    deduplicated_nodes = {
        (str(node.get("object_type") or ""), str(node.get("object_id") or "")): node
        for node in nodes
        if node.get("object_id")
    }
    deduplicated_edges = {
        (
            str(edge.get("source") or ""),
            str(edge.get("target") or ""),
            str(edge.get("relation") or "depends_on"),
        ): edge
        for edge in edges
        if edge.get("source") and edge.get("target")
    }
    payload = {
        "schema_id": TARGET_GRAPH_SCHEMA_ID,
        "root_ids": sorted(set(str(item) for item in root_ids if item)),
        "nodes": [deduplicated_nodes[key] for key in sorted(deduplicated_nodes)],
        "edges": [deduplicated_edges[key] for key in sorted(deduplicated_edges)],
        "provider_calls": list(provider_calls),
        "limitations": sorted(set(limitations or [])),
        "bounded": True,
    }
    payload["graph_hash"] = target_graph_hash(payload)
    return payload


def target_graph_hash(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("graph_hash", None)
    return canonical_hash(material)


def validate_target_graph(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != TARGET_GRAPH_SCHEMA_ID:
        issues.append("target graph schema_id is invalid")
    supplied = str(value.get("graph_hash") or "")
    if not supplied or supplied != target_graph_hash(value):
        issues.append("target graph hash mismatch")
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        issues.append("target graph nodes must be an array")
    elif len(nodes) != len({(item.get("object_type"), item.get("object_id")) for item in nodes if isinstance(item, dict)}):
        issues.append("target graph nodes are duplicated")
    return tuple(issues)
