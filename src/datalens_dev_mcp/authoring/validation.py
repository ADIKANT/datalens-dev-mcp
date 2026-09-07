"""Pure batch validation for typed authoring drafts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from datalens_dev_mcp.authoring.artifacts import resolve_artifact
from datalens_dev_mcp.authoring.models import ValidationResult
from datalens_dev_mcp.dashboard.composition import object_references, validate_dashboard_contract
from datalens_dev_mcp.dataset.contracts import TECHNICAL_MEASURES, extract_dataset_fields, validate_dataset_fields
from datalens_dev_mcp.editor.validation import validate_editor_draft

EDITOR_OBJECT_TYPES = frozenset(
    {"editor_chart", "advanced-chart_node", "table_node", "d3_node", "markdown_node", "control_node"}
)
WIZARD_VISUALIZATIONS = frozenset(
    {
        "area",
        "area_100p",
        "bar",
        "bar_100p",
        "column",
        "column_100p",
        "combined_chart",
        "donut",
        "flat_table",
        "funnel",
        "geolayer",
        "indicator",
        "line",
        "pie",
        "pivot_table",
        "scatter",
        "treemap",
    }
)
WIZARD_SETTINGS = frozenset(
    {
        "dataset_id",
        "visualization",
        "roles",
        "title",
        "title_mode",
        "table",
        "sort",
        "column_titles",
        "grid",
        "legend",
        "labels_position",
        "subtotals",
    }
)
SUPPORTED_OBJECT_TYPES = frozenset({"dataset", "wizard_chart", "dashboard", *EDITOR_OBJECT_TYPES})
KNOWN_NOT_CHECKED_TYPES = frozenset({"connection", "workbook", "ql_chart", "html_page"})


def validate_drafts(drafts: Sequence[Mapping[str, Any]]) -> ValidationResult:
    """Validate a concrete authoring batch without contacting DataLens."""
    if not isinstance(drafts, Sequence) or isinstance(drafts, (str, bytes, bytearray)):
        raise TypeError("drafts must be a sequence of inline objects or artifact references")
    if not drafts:
        return {
            "ok": False,
            "items": [],
            "errors": [
                {
                    "code": "batch_empty",
                    "path": "drafts",
                    "message": "validate_drafts requires at least one draft",
                }
            ],
            "provider_writes": 0,
            "proof_level": "static_validity_only",
        }

    resolved: list[dict[str, Any] | None] = []
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(drafts):
        fallback_ref = f"draft-{index}"
        raw_ref = raw.get("client_ref") if isinstance(raw, Mapping) else None
        item = {
            "index": index,
            "client_ref": str(raw_ref or fallback_ref),
            "object_type": "unknown",
            "status": "invalid",
            "checks": [],
            "errors": [],
            "warnings": [],
            "proof_level": "static_validity_only",
        }
        items.append(item)
        if not isinstance(raw, Mapping):
            item["errors"].append(_error("draft_shape_invalid", f"drafts/{index}", "draft must be an object"))
            resolved.append(None)
            continue
        try:
            draft = resolve_artifact(dict(raw))
        except (OSError, ValueError, TypeError) as exc:
            item["errors"].append(_error("artifact_unreadable", f"drafts/{index}/artifact_path", _compact_error(exc)))
            resolved.append(None)
            continue
        if "artifact_path" in raw:
            item["checks"].append("artifact_resolved")
        resolved.append(draft)
        client_ref = draft.get("client_ref")
        if not isinstance(client_ref, str) or not client_ref.strip():
            item["errors"].append(
                _error("client_ref_missing", f"drafts/{index}/client_ref", "draft requires a nonempty client_ref")
            )
        else:
            item["client_ref"] = client_ref
        object_type = draft.get("object_type")
        if isinstance(object_type, str) and object_type.strip():
            item["object_type"] = object_type
        else:
            item["errors"].append(
                _error("object_type_missing", f"drafts/{index}/object_type", "draft requires object_type")
            )

    _validate_client_refs(resolved, items)
    dependency_graph = _validate_dependencies(resolved, items)
    for ref in _cycle_refs(dependency_graph):
        for index, draft in enumerate(resolved):
            if draft is not None and draft.get("client_ref") == ref:
                items[index]["errors"].append(
                    _error("dependency_cycle", f"drafts/{index}/depends_on", "dependency cycle in draft batch")
                )

    for draft, item in zip(resolved, items, strict=True):
        if draft is None:
            continue
        object_type = item["object_type"]
        if object_type in SUPPORTED_OBJECT_TYPES:
            errors, checks = _validate_supported_draft(draft, object_type)
            item["errors"].extend(errors)
            item["checks"].extend(checks)
            item["status"] = "invalid" if item["errors"] else "valid"
        elif object_type in KNOWN_NOT_CHECKED_TYPES:
            item["status"] = "not_checked"
            item["warnings"].append(
                _error(
                    "object_type_not_checked",
                    f"drafts/{item['index']}/object_type",
                    f"no static draft validator is available for {object_type}",
                )
            )
        else:
            item["status"] = "unsupported"
            item["errors"].append(
                _error(
                    "object_type_unsupported",
                    f"drafts/{item['index']}/object_type",
                    f"unsupported draft object type: {object_type}",
                )
            )

    _validate_selector_consumers(resolved, items)
    for item in items:
        if item["errors"] and item["status"] == "valid":
            item["status"] = "invalid"

    return {
        "ok": all(item["status"] == "valid" for item in items),
        "items": items,
        "errors": [],
        "provider_writes": 0,
        "proof_level": "static_validity_only",
    }


def _validate_selector_consumers(resolved: list[dict[str, Any] | None], items: list[dict[str, Any]]) -> None:
    by_ref = {
        str(draft["client_ref"]): draft
        for draft in resolved
        if draft is not None and isinstance(draft.get("client_ref"), str) and draft["client_ref"]
    }
    for index, draft in enumerate(resolved):
        if draft is None or draft.get("object_type") != "control_node":
            continue
        contract = draft.get("visual_contract") or draft.get("config") or {}
        selector = contract.get("selector") if isinstance(contract, Mapping) else None
        if not isinstance(selector, Mapping):
            continue
        param_name = selector.get("param_name")
        consumers = selector.get("consumers") or []
        if not isinstance(param_name, str) or not param_name or not isinstance(consumers, list):
            continue
        for consumer_index, consumer in enumerate(consumers):
            consumer_ref = consumer.get("client_ref") if isinstance(consumer, Mapping) else consumer
            path = f"drafts/{index}/bindings/consumers/{consumer_index}"
            if not isinstance(consumer_ref, str) or consumer_ref not in by_ref:
                items[index]["errors"].append(
                    _error("selector_consumer_missing", path, f"unknown selector consumer: {consumer_ref}")
                )
                continue
            consumer_parameter = consumer.get("parameter") if isinstance(consumer, Mapping) else param_name
            bindings = by_ref[consumer_ref].get("bindings") or {}
            source = bindings.get("source") if isinstance(bindings, Mapping) else None
            params = source.get("params") if isinstance(source, Mapping) else None
            if consumer_parameter != param_name or not isinstance(params, Mapping) or param_name not in params:
                items[index]["errors"].append(
                    _error(
                        "selector_consumer_parameter_unbound",
                        path,
                        f"consumer {consumer_ref} does not declare selector parameter {param_name}",
                    )
                )


def _validate_client_refs(resolved: list[dict[str, Any] | None], items: list[dict[str, Any]]) -> None:
    counts = Counter(
        draft["client_ref"]
        for draft in resolved
        if draft is not None and isinstance(draft.get("client_ref"), str) and draft["client_ref"]
    )
    duplicate_refs = {ref for ref, count in counts.items() if count > 1}
    for index, draft in enumerate(resolved):
        if draft is not None and draft.get("client_ref") in duplicate_refs:
            items[index]["errors"].append(
                _error(
                    "client_ref_duplicate",
                    f"drafts/{index}/client_ref",
                    f"duplicate client_ref: {draft['client_ref']}",
                )
            )


def _validate_dependencies(resolved: list[dict[str, Any] | None], items: list[dict[str, Any]]) -> dict[str, set[str]]:
    known = {
        str(draft["client_ref"])
        for draft in resolved
        if draft is not None and isinstance(draft.get("client_ref"), str) and draft["client_ref"]
    }
    graph: dict[str, set[str]] = {}
    for index, draft in enumerate(resolved):
        if draft is None or not isinstance(draft.get("client_ref"), str) or not draft["client_ref"]:
            continue
        explicit = draft.get("depends_on") or []
        if not isinstance(explicit, list) or any(not isinstance(value, str) or not value for value in explicit):
            items[index]["errors"].append(
                _error(
                    "dependency_shape_invalid",
                    f"drafts/{index}/depends_on",
                    "depends_on must be an array of nonempty client_ref strings",
                )
            )
            explicit = []
        try:
            dependencies = set(explicit) | object_references(draft)
        except ValueError as exc:
            items[index]["errors"].append(_error("object_reference_invalid", f"drafts/{index}", _compact_error(exc)))
            dependencies = set(explicit)
        missing = sorted(dependencies - known)
        if missing:
            items[index]["errors"].append(
                _error(
                    "dependency_missing",
                    f"drafts/{index}/depends_on",
                    "unknown dependency: " + ", ".join(missing),
                )
            )
        graph[str(draft["client_ref"])] = dependencies & known
    return graph


def _cycle_refs(graph: dict[str, set[str]]) -> set[str]:
    cycles: set[str] = set()
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visiting:
            cycles.update(visiting[visiting.index(ref) :])
            return
        if ref in visited:
            return
        visiting.append(ref)
        for dependency in graph.get(ref, set()):
            visit(dependency)
        visiting.pop()
        visited.add(ref)

    for ref in graph:
        visit(ref)
    return cycles


def _validate_supported_draft(draft: Mapping[str, Any], object_type: str) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(draft.get("name"), str) or not str(draft.get("name")).strip():
        errors.append(_error("object_name_missing", "name", "draft requires a nonempty object name"))
    if object_type in EDITOR_OBJECT_TYPES:
        editor_draft = deepcopy(dict(draft))
        if object_type != "editor_chart":
            editor_draft.setdefault("variant", object_type)
        report = validate_editor_draft(editor_draft)
        errors.extend(deepcopy(report["issues"]))
        return errors, ["editor_static_contract"]
    if object_type == "wizard_chart":
        errors.extend(_validate_wizard(draft))
        return errors, ["wizard_static_contract"]
    if object_type == "dataset":
        specification = draft.get("dataset")
        snapshot = draft.get("snapshot")
        if isinstance(specification, Mapping):
            errors.extend(_validate_typed_dataset(specification))
            fields = specification.get("fields")
            if isinstance(fields, list) and fields:
                errors.extend(validate_dataset_fields(fields)["issues"])
        elif isinstance(snapshot, Mapping):
            fields = extract_dataset_fields(snapshot)
            if not fields:
                errors.append(
                    _error("dataset_fields_missing", "snapshot", "Dataset snapshot requires discoverable typed fields")
                )
            else:
                errors.extend(validate_dataset_fields(fields)["issues"])
        else:
            errors.append(
                _error(
                    "dataset_contract_missing",
                    "dataset",
                    "Dataset draft requires a nested dataset object or a provider snapshot",
                )
            )
        return errors, ["dataset_static_contract"]
    dashboard = draft.get("dashboard")
    if not isinstance(dashboard, Mapping):
        snapshot = draft.get("snapshot")
        dashboard = snapshot.get("data", snapshot) if isinstance(snapshot, Mapping) else None
    if not isinstance(dashboard, Mapping):
        errors.append(
            _error("dashboard_contract_missing", "dashboard", "Dashboard draft requires dashboard or snapshot content")
        )
    else:
        errors.extend(validate_dashboard_contract(dict(dashboard))["issues"])
    return errors, ["dashboard_static_contract"]


def _validate_wizard(draft: Mapping[str, Any]) -> list[dict[str, str]]:
    specification = draft.get("wizard")
    if not isinstance(specification, Mapping):
        return [_error("wizard_contract_missing", "wizard", "Wizard draft requires a wizard object")]
    errors: list[dict[str, str]] = []
    for setting in sorted(set(specification) - WIZARD_SETTINGS):
        errors.append(
            _error(
                "wizard_setting_unsupported",
                f"wizard/{setting}",
                f"unsupported Wizard setting: {setting}",
            )
        )
    dataset_id = specification.get("dataset_id")
    object_ref = (
        isinstance(dataset_id, Mapping)
        and set(dataset_id) == {"$object_ref"}
        and isinstance(dataset_id.get("$object_ref"), str)
        and bool(dataset_id["$object_ref"])
    )
    if not (isinstance(dataset_id, str) and dataset_id.strip()) and not object_ref:
        errors.append(_error("wizard_dataset_missing", "wizard/dataset_id", "Wizard draft requires dataset_id"))
    visualization = specification.get("visualization")
    if not isinstance(visualization, str) or visualization not in WIZARD_VISUALIZATIONS:
        errors.append(
            _error(
                "wizard_visualization_unsupported",
                "wizard/visualization",
                f"unsupported Wizard visualization: {visualization or '<missing>'}",
            )
        )
    roles = specification.get("roles")
    if not isinstance(roles, Mapping) or not roles:
        errors.append(_error("wizard_roles_missing", "wizard/roles", "Wizard draft requires nonempty field roles"))
        return errors
    for role, values in roles.items():
        if not isinstance(role, str) or not isinstance(values, list) or not values:
            errors.append(
                _error("wizard_role_invalid", f"wizard/roles/{role}", "Wizard roles require nonempty GUID arrays")
            )
            continue
        if any(not isinstance(value, str) or not value or value.lower() in TECHNICAL_MEASURES for value in values):
            errors.append(
                _error(
                    "wizard_field_guid_invalid",
                    f"wizard/roles/{role}",
                    "Wizard roles require Dataset GUIDs, not technical measures",
                )
            )
    return errors


def _validate_typed_dataset(specification: Mapping[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    supported = {"connection_id", "source", "fields", "parameters", "description"}
    for setting in sorted(set(specification) - supported):
        errors.append(
            _error(
                "dataset_setting_unsupported",
                f"dataset/{setting}",
                f"unsupported Dataset setting: {setting}",
            )
        )
    connection_id = specification.get("connection_id")
    if not isinstance(connection_id, str) or not connection_id:
        errors.append(
            _error(
                "dataset_connection_missing",
                "dataset/connection_id",
                "typed Dataset requires a nonempty connection_id",
            )
        )
    source = specification.get("source")
    if not isinstance(source, Mapping):
        errors.append(_error("dataset_source_missing", "dataset/source", "typed Dataset requires a source object"))
    else:
        for setting in sorted(set(source) - {"alias", "source_type", "parameters"}):
            errors.append(
                _error(
                    "dataset_source_setting_unsupported",
                    f"dataset/source/{setting}",
                    f"unsupported Dataset source setting: {setting}",
                )
            )
        if not isinstance(source.get("alias"), str) or not source.get("alias"):
            errors.append(
                _error("dataset_source_alias_missing", "dataset/source/alias", "Dataset source requires an alias")
            )
        if not isinstance(source.get("source_type"), str) or not source.get("source_type"):
            errors.append(
                _error(
                    "dataset_source_type_missing",
                    "dataset/source/source_type",
                    "Dataset source requires a source_type",
                )
            )
        parameters = source.get("parameters", {})
        if not isinstance(parameters, Mapping):
            errors.append(
                _error(
                    "dataset_source_parameters_invalid",
                    "dataset/source/parameters",
                    "Dataset source parameters must be an object",
                )
            )
    fields = specification.get("fields")
    if not isinstance(fields, list) or not fields:
        errors.append(
            _error("dataset_fields_missing", "dataset/fields", "typed Dataset requires a nonempty fields array")
        )
    else:
        for index, field in enumerate(fields):
            if not isinstance(field, Mapping):
                continue
            kind = str(field.get("kind") or field.get("type") or "").lower()
            if kind not in {"dimension", "measure"}:
                errors.append(
                    _error(
                        "dataset_field_kind_invalid",
                        f"dataset/fields/{index}/kind",
                        "Dataset field kind must be dimension or measure",
                    )
                )
            if not isinstance(field.get("title") or field.get("name"), str) or not (
                field.get("title") or field.get("name")
            ):
                errors.append(
                    _error(
                        "dataset_field_title_missing",
                        f"dataset/fields/{index}/title",
                        "Dataset field requires a nonempty title",
                    )
                )
            formula = field.get("formula")
            if formula is None and (not isinstance(field.get("source"), str) or not field.get("source")):
                errors.append(
                    _error(
                        "dataset_field_source_missing",
                        f"dataset/fields/{index}/source",
                        "Dataset direct field requires a source",
                    )
                )
            elif formula is not None and (not isinstance(formula, str) or not formula):
                errors.append(
                    _error(
                        "dataset_field_formula_invalid",
                        f"dataset/fields/{index}/formula",
                        "Dataset calculation requires a nonempty formula",
                    )
                )
    parameters = specification.get("parameters", [])
    if not isinstance(parameters, list):
        errors.append(
            _error(
                "dataset_parameters_invalid",
                "dataset/parameters",
                "Dataset parameters must be an array",
            )
        )
    return errors


def _dataset_fields(draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    direct = draft.get("fields")
    if isinstance(direct, list):
        return [dict(value) for value in direct if isinstance(value, Mapping)]
    dataset = draft.get("dataset")
    if isinstance(dataset, Mapping) and isinstance(dataset.get("fields"), list):
        return [dict(value) for value in dataset["fields"] if isinstance(value, Mapping)]
    snapshot = draft.get("snapshot")
    return extract_dataset_fields(snapshot) if isinstance(snapshot, Mapping) else []


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _compact_error(exc: Exception) -> str:
    if isinstance(exc, OSError):
        return "artifact file is unavailable"
    return str(exc) or type(exc).__name__
