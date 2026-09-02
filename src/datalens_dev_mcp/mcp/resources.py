from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.methods import get_method_schema, list_methods
from datalens_dev_mcp.editor.style_registry import load_style_registry
from datalens_dev_mcp.editor.style_scanner import TAB_ORDER
from datalens_dev_mcp.mcp.task_resources import list_task_resources, read_task_resource
from datalens_dev_mcp.pipeline.artifacts import read_text
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.route_contract import route_contract_document
from datalens_dev_mcp.runtime_resources import resource_text

STATIC_RESOURCES = {
    "datalens://project/requirements": "requirements/implementation_plan.md",
}
PACKAGED_KNOWLEDGE_RESOURCES = {
    "datalens://knowledge/formulas": ("schemas/datalens-knowledge/formula-registry.json", "application/json"),
    "datalens://knowledge/wizard-authoring": ("templates/datalens/wizard/wizard_template_registry.json", "application/json"),
    "datalens://knowledge/javascript-editor-authoring": (
        "schemas/datalens-knowledge/editor-visualization-contracts.json",
        "application/json",
    ),
    "datalens://knowledge/chart-selection": ("config/datalens_chart_decision_rules.json", "application/json"),
    "datalens://knowledge/error-diagnosis": ("schemas/datalens-knowledge/error-registry.json", "application/json"),
    "datalens://knowledge/save-publish-lifecycle": ("config/datalens_delivery_policy.json", "application/json"),
}


def list_resources(*, project_root: str | Path = ".") -> list[dict[str, str]]:
    resources = [
        {
            "uri": uri,
            "name": uri.removeprefix("datalens://"),
            "title": uri.removeprefix("datalens://").replace("/", " ").replace("-", " ").title(),
            "mimeType": "text/markdown",
        }
        for uri in STATIC_RESOURCES
    ]
    resources.append(
        {
            "uri": "datalens://knowledge/ordinary-workflow",
            "name": "Ordinary DataLens workflow",
            "title": "Ordinary DataLens Workflow",
            "mimeType": "text/markdown",
        }
    )
    resources.extend(
        {
            "uri": uri,
            "name": uri.removeprefix("datalens://knowledge/").replace("-", " "),
            "title": uri.removeprefix("datalens://knowledge/").replace("-", " ").title(),
            "mimeType": mime,
        }
        for uri, (_path, mime) in PACKAGED_KNOWLEDGE_RESOURCES.items()
    )
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
                "uri": "datalens://inspections/target-graph/{graph_hash}",
                "name": "External inspection target graph",
                "title": "External Inspection Target Graph",
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
            {
                "uri": "datalens://style-registry/profiles/{profile_id}/tabs/{tab_name}",
                "name": "Protected portfolio style tab",
                "title": "Protected Portfolio Style Tab",
                "mimeType": "text/plain",
            },
        ]
    )
    resources.extend(list_task_resources(project_root))
    return resources


def read_resource(uri: str, *, project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    if uri.startswith("datalens://tasks/"):
        return read_task_resource(uri, project_root=root)
    if uri.startswith("datalens://inspections/target-graph/"):
        graph_hash = uri.removeprefix("datalens://inspections/target-graph/").strip()
        if not graph_hash or any(character not in "0123456789abcdef" for character in graph_hash.lower()):
            raise KeyError("Invalid inspection target graph URI")
        state_root = ProjectJournal(root, "inspection-resource").storage_root.parent
        path = _path_within(state_root, Path("inspections"), f"target-graph-{graph_hash}.json")
        return {"uri": uri, "mimeType": "application/json", "text": read_text(path, default="{}")}
    if uri.startswith("datalens://style-registry/profiles/"):
        return _read_style_profile_tab(uri, project_root=root)
    if uri in STATIC_RESOURCES:
        relative = Path(STATIC_RESOURCES[uri])
        text = read_text(_path_within(root, relative.parent, relative.name), default="")
        return {"uri": uri, "mimeType": "text/markdown", "text": text}
    if uri == "datalens://knowledge/ordinary-workflow":
        return {"uri": uri, "mimeType": "text/markdown", "text": _ordinary_workflow_resource()}
    if uri in PACKAGED_KNOWLEDGE_RESOURCES:
        path, mime = PACKAGED_KNOWLEDGE_RESOURCES[uri]
        return {"uri": uri, "mimeType": mime, "text": resource_text(path)}
    if uri == "datalens://routes/contract":
        return {"uri": uri, "mimeType": "text/markdown", "text": route_contract_document()}
    if uri == "datalens://api/methods":
        payload = [item.__dict__ for item in list_methods()]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(payload, indent=2)}
    if uri.startswith("datalens://artifacts/"):
        name = uri.removeprefix("datalens://artifacts/")
        path = _path_within(root, Path("artifacts"), name)
        return {"uri": uri, "mimeType": "text/plain", "text": read_text(path, default="")}
    if uri.startswith("datalens://dashboard/") and uri.endswith("/baseline"):
        dashboard_id = uri.removeprefix("datalens://dashboard/").removesuffix("/baseline")
        path = _path_within(root, Path("artifacts/baselines"), f"{dashboard_id}.json")
        return {"uri": uri, "mimeType": "application/json", "text": read_text(path, default="{}")}
    if uri.startswith("datalens://dashboard/") and uri.endswith("/readback/latest"):
        dashboard_id = uri.removeprefix("datalens://dashboard/").removesuffix("/readback/latest")
        path = _path_within(root, Path("artifacts/readback"), f"{dashboard_id}.saved.latest.json")
        return {"uri": uri, "mimeType": "application/json", "text": read_text(path, default="{}")}
    if uri.startswith("datalens://api/methods/"):
        name = uri.rsplit("/", 1)[-1]
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(get_method_schema(name), indent=2)}
    raise KeyError(f"Unknown resource {uri}")


def _ordinary_workflow_resource() -> str:
    return """# Ordinary DataLens workflow

1. Start one task with `dl_task_start` from the exact project root.
2. Read `execution_brief`; use its target, reference, technology, delivery,
   missing fields, `confirmation_action`, and complete `next_call`.
3. Read only the linked knowledge resource needed for formulas, Wizard, Editor, errors, or delivery.
4. For a mutation, show the compact brief once and wait for confirmation unless
   `confirmation_required` is false. Questions preserve the plan; corrections
   create a new plan and require a new confirmation.
5. On explicit confirmation of the exact unchanged current plan, call
   `dl_task_resume` with `confirmation_action.fixed_arguments` and the user's
   text in its declared confirmation field. Never bypass this with direct
   `dl_execute`.
6. Use Browser only for final read-only visual acceptance after API readbacks and applicable data diagnostics.
7. Send corrections through `dl_task_resume.follow_up`; the server infers their relation to the task.
"""


def _read_style_profile_tab(uri: str, *, project_root: Path) -> dict[str, Any]:
    remainder = uri.removeprefix("datalens://style-registry/profiles/")
    profile_id, separator, tab_name = remainder.partition("/tabs/")
    if not separator or tab_name not in TAB_ORDER or not profile_id:
        raise KeyError("Invalid portfolio style resource URI")
    registry_path = _path_within(project_root, Path(".datalens-mcp"), "style-registry.json")
    registry = load_style_registry(registry_path)
    registry_root = Path(str((registry.get("source") or {}).get("root") or "")).resolve()
    project_resolved = project_root.expanduser().resolve()
    try:
        registry_root.relative_to(project_resolved)
    except ValueError as exc:
        raise KeyError("Portfolio style registry root must remain inside the project root") from exc
    for profile in registry.get("profiles") or []:
        if str(profile.get("id") or "") != profile_id:
            continue
        source = Path(str((profile.get("source") or {}).get("absolute_path") or "")).resolve()
        try:
            source.relative_to(registry_root)
        except ValueError as exc:
            raise KeyError("Portfolio style source must remain inside the registry root") from exc
        path = source / tab_name
        text = path.read_text(encoding="utf-8")
        expected = str((profile.get("tab_hashes") or {}).get(tab_name) or "")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise KeyError("Portfolio style tab changed; rebuild the style registry")
        mime = "application/json" if tab_name.endswith(".json") else "text/javascript"
        return {"uri": uri, "mimeType": mime, "text": text}
    raise KeyError("Unknown portfolio style profile")


def _path_within(project_root: Path, declared_directory: Path, relative_path: str) -> Path:
    root = project_root.expanduser().resolve()
    base = (root / declared_directory).resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise KeyError("Resource directory must remain inside the configured project root") from exc
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise KeyError("Resource path must remain inside its declared artifact directory") from exc
    return candidate
