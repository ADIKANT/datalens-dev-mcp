from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.methods import get_method_schema, list_methods
from datalens_dev_mcp.pipeline.artifacts import read_text
from datalens_dev_mcp.pipeline.route_contract import route_contract_document

STATIC_RESOURCES = {
    "datalens://project/requirements": "requirements/implementation_plan.md",
}


def list_resources() -> list[dict[str, str]]:
    resources = [
        {
            "uri": uri,
            "name": uri.removeprefix("datalens://"),
            "title": uri.removeprefix("datalens://").replace("/", " ").replace("-", " ").title(),
            "mimeType": "text/markdown",
        }
        for uri in STATIC_RESOURCES
    ]
    resources.extend(
        [
            {
                "uri": "datalens://routes/contract",
                "name": "Route contract",
                "title": "Route Contract",
                "mimeType": "text/markdown",
            },
            {
                "uri": "datalens://api/methods",
                "name": "API method catalog",
                "title": "API Method Catalog",
                "mimeType": "application/json",
            },
            {
                "uri": "datalens://artifacts/{name}",
                "name": "Project artifact by name",
                "title": "Project Artifact",
                "mimeType": "text/plain",
            },
            {
                "uri": "datalens://dashboard/{dashboard_id}/baseline",
                "name": "Dashboard baseline",
                "title": "Dashboard Baseline",
                "mimeType": "application/json",
            },
            {
                "uri": "datalens://dashboard/{dashboard_id}/readback/latest",
                "name": "Latest saved dashboard readback",
                "title": "Latest Saved Dashboard Readback",
                "mimeType": "application/json",
            },
        ]
    )
    return resources


def read_resource(uri: str, *, project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    if uri in STATIC_RESOURCES:
        text = read_text(root / STATIC_RESOURCES[uri], default="")
        return {"uri": uri, "mimeType": "text/markdown", "text": text}
    if uri == "datalens://routes/contract":
        return {"uri": uri, "mimeType": "text/markdown", "text": route_contract_document()}
    if uri == "datalens://api/methods":
        payload = [item.__dict__ for item in list_methods()]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(payload, indent=2)}
    if uri.startswith("datalens://artifacts/"):
        name = uri.removeprefix("datalens://artifacts/")
        path = root / "artifacts" / name
        return {"uri": uri, "mimeType": "text/plain", "text": read_text(path, default="")}
    if uri.startswith("datalens://dashboard/") and uri.endswith("/baseline"):
        dashboard_id = uri.removeprefix("datalens://dashboard/").removesuffix("/baseline")
        path = root / "artifacts" / "baselines" / f"{dashboard_id}.json"
        return {"uri": uri, "mimeType": "application/json", "text": read_text(path, default="{}")}
    if uri.startswith("datalens://dashboard/") and uri.endswith("/readback/latest"):
        dashboard_id = uri.removeprefix("datalens://dashboard/").removesuffix("/readback/latest")
        path = root / "artifacts" / "readback" / f"{dashboard_id}.saved.latest.json"
        return {"uri": uri, "mimeType": "application/json", "text": read_text(path, default="{}")}
    if uri.startswith("datalens://api/methods/"):
        name = uri.rsplit("/", 1)[-1]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(get_method_schema(name), indent=2)}
    raise KeyError(f"Unknown resource {uri}")
