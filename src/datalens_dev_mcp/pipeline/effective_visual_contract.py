from __future__ import annotations

from copy import deepcopy
from typing import Any

from datalens_dev_mcp.pipeline.project_decision_context import VISUAL_PROFILE_CATEGORIES
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


EFFECTIVE_VISUAL_CONTRACT_SCHEMA_ID = "datalens_effective_visual_contract"
VISUAL_PRECEDENCE = (
    "universal_default",
    "portfolio_family",
    "accepted_exemplar",
    "project_profile",
    "task_correction",
    "exact_reference",
    "live_target",
    "current_user",
)
_BUCKETS = ("required", "preserve", "forbidden", "defaults")
_ASSERTION_IDS = {
    "layout": "semantic_row_geometry_contract",
    "kpi": "kpi_separation_contract",
    "tables": "table_columns_contract",
    "series": "line_series_retention_contract",
    "legend": "legend_visibility_contract",
    "axes": "axis_unit_scale_contract",
    "tooltip": "tooltip_fields_contract",
    "selectors": "selector_placement_contract",
    "data_states": "data_state_contract",
}


def resolve_effective_visual_contract(
    contract: dict[str, Any],
    *,
    target_graph: dict[str, Any],
    baselines: dict[str, dict[str, Any]],
    style_binding: dict[str, Any],
    decision_context: dict[str, Any] | None = None,
    changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the one operational visual contract for a task.

    Every slot is selected once according to ``VISUAL_PRECEDENCE``.  A source
    can constrain an existing action, but never introduces a target or action.
    """

    context = decision_context or {}
    requested = list(changes or _contract_changes(contract))
    layers: dict[str, list[dict[str, Any]]] = {
        "universal_default": [_typed_layer(_universal_defaults(), bucket="defaults")],
        "portfolio_family": [_typed_layer(_portfolio_contract(style_binding), bucket="defaults")],
        "accepted_exemplar": [
            _typed_layer(dict(context.get("accepted_exemplar_visual_contract") or {}), bucket="required")
        ],
        "project_profile": [_typed_layer(dict(context.get("typed_profile") or {}), bucket="required")],
        "task_correction": [
            _decision_layer(item)
            for item in context.get("task_corrections") or []
            if isinstance(item, dict)
        ],
        "exact_reference": [_exact_reference_layer(contract, style_binding)],
        "live_target": [_live_target_layer(contract, target_graph, style_binding)],
        "current_user": [_current_user_layer(requested)],
    }
    layers["project_profile"].extend(
        _decision_layer(item)
        for item in context.get("typed_decisions") or []
        if isinstance(item, dict)
    )

    chosen: dict[tuple[str, ...], dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    for rank, source in enumerate(VISUAL_PRECEDENCE):
        source_values: dict[tuple[str, ...], dict[str, Any]] = {}
        for layer in layers[source]:
            for row in _flatten_layer(layer, source=source, rank=rank):
                key = tuple(row["path"])
                prior = source_values.get(key)
                if prior is not None and prior["value"] != row["value"]:
                    conflicts.append(
                        {
                            "path": ".".join(key),
                            "source": source,
                            "values": [prior["value"], row["value"]],
                            "reason": "same-precedence visual decisions disagree",
                        }
                    )
                    continue
                source_values[key] = row
        for key, row in source_values.items():
            chosen[key] = row
            provenance_rows.append(
                {
                    "path": ".".join(key),
                    "source": source,
                    "bucket": row["bucket"],
                    "decision_id": row.get("decision_id", ""),
                }
            )

    if conflicts:
        return {
            "status": "blocked",
            "schema_id": EFFECTIVE_VISUAL_CONTRACT_SCHEMA_ID,
            "reason": "effective visual contract has an unresolved focused conflict",
            "conflicts": conflicts,
        }

    effective = {bucket: {} for bucket in _BUCKETS}
    for row in chosen.values():
        _set_path(effective[row["bucket"]], row["path"], deepcopy(row["value"]))

    provenance = {
        "precedence": list(reversed(VISUAL_PRECEDENCE)),
        "applied": sorted(provenance_rows, key=lambda item: (item["path"], item["source"])),
        "decision_context_hash": str(context.get("context_hash") or ""),
        "project_profile_hash": str(context.get("project_profile_hash") or ""),
        "accepted_exemplar_hash": str(context.get("accepted_exemplar_hash") or ""),
        "reference_binding_hash": str(style_binding.get("reference_binding_hash") or ""),
        "live_target_graph_hash": str(target_graph.get("graph_hash") or ""),
        "baseline_set_hash": canonical_hash(sorted(baselines)),
    }
    active_provenance_hash = canonical_hash(provenance)
    assertions = _build_assertions(
        effective,
        contract=contract,
        target_graph=target_graph,
        active_provenance_hash=active_provenance_hash,
        provenance_rows=provenance_rows,
    )
    payload: dict[str, Any] = {
        "schema_id": EFFECTIVE_VISUAL_CONTRACT_SCHEMA_ID,
        "target": _target_projection(contract, target_graph),
        "technology": _technology(contract, target_graph, style_binding),
        **effective,
        "assertions": assertions,
        "provenance": {**provenance, "active_provenance_hash": active_provenance_hash},
    }
    payload["contract_hash"] = canonical_hash(payload)
    return {"status": "success", **payload}


def constraints_for_action(
    effective_contract: dict[str, Any],
    change: dict[str, Any],
    *,
    target_id: str,
    tab_id: str = "",
) -> dict[str, Any]:
    """Return bounded effective constraints actually applicable to one action."""

    categories = _change_categories(change)
    if not categories:
        categories = {
            category
            for bucket in _BUCKETS
            for category in (effective_contract.get(bucket) or {})
        }
    categories.add("advanced_editor")
    projection: dict[str, Any] = {
        "contract_hash": str(effective_contract.get("contract_hash") or ""),
        "target_id": target_id,
        "tab_id": tab_id,
        "technology": str(effective_contract.get("technology") or ""),
    }
    for bucket in _BUCKETS:
        values = effective_contract.get(bucket) if isinstance(effective_contract.get(bucket), dict) else {}
        selected = {key: deepcopy(values[key]) for key in sorted(categories) if key in values}
        if selected:
            projection[bucket] = selected
    projection["assertions"] = [
        deepcopy(item)
        for item in effective_contract.get("assertions") or []
        if isinstance(item, dict)
        and (not item.get("applies_to_object_ids") or target_id in item.get("applies_to_object_ids"))
        and (not item.get("applies_to_tab_ids") or tab_id in item.get("applies_to_tab_ids"))
    ]
    return projection


def _typed_layer(profile: dict[str, Any], *, bucket: str) -> dict[str, Any]:
    if not profile:
        return {}
    if any(key in profile for key in _BUCKETS):
        return {key: deepcopy(profile.get(key) or {}) for key in _BUCKETS if profile.get(key)}
    return {bucket: deepcopy(profile)}


def _decision_layer(item: dict[str, Any]) -> dict[str, Any]:
    category = str(item.get("category") or "")
    if category not in VISUAL_PROFILE_CATEGORIES or "typed_value" not in item:
        return {}
    value = deepcopy(item.get("typed_value"))
    if isinstance(value, dict) and any(key in value for key in _BUCKETS):
        layer = {
            bucket: {category: deepcopy(value[bucket])}
            for bucket in _BUCKETS
            if bucket in value
        }
    else:
        layer = {"required": {category: value}}
    layer["_decision_id"] = str(item.get("decision_id") or "")
    return layer


def _exact_reference_layer(contract: dict[str, Any], style_binding: dict[str, Any]) -> dict[str, Any]:
    reference = contract.get("reference") if isinstance(contract.get("reference"), dict) else {}
    if not reference.get("required_exact_style"):
        return {}
    visual = style_binding.get("reference_visual_contract")
    if isinstance(visual, dict) and visual:
        return _typed_layer(visual, bucket="required")
    return {
        "preserve": {
            "advanced_editor": {
                "protected_region_hash": str(style_binding.get("protected_runtime_hash") or ""),
                "semantic_slot_hash": str(style_binding.get("semantic_slot_hash") or ""),
            }
        }
    }


def _live_target_layer(
    contract: dict[str, Any],
    target_graph: dict[str, Any],
    style_binding: dict[str, Any],
) -> dict[str, Any]:
    nodes = [item for item in target_graph.get("nodes") or [] if isinstance(item, dict)]
    technology = _technology(contract, target_graph, style_binding)
    preserve: dict[str, Any] = {
        "layout": {"policy": "preserve_fresh_saved_geometry"},
        "advanced_editor": {
            "protected_regions": deepcopy(style_binding.get("protected_regions") or []),
            "semantic_slots": deepcopy(style_binding.get("semantic_slots") or []),
            "protected_region_hash": str(style_binding.get("protected_runtime_hash") or ""),
            "semantic_slot_hash": str(style_binding.get("semantic_slot_hash") or ""),
        },
    }
    if technology:
        preserve["manual_overrides"] = {"technology": technology}
    live_sections: dict[str, Any] = {}
    for category in VISUAL_PROFILE_CATEGORIES:
        values = [item.get(category) for item in nodes if isinstance(item.get(category), dict)]
        if len(values) == 1:
            live_sections[category] = deepcopy(values[0])
    preserve.update(live_sections)
    return {"preserve": preserve}


def _current_user_layer(changes: list[dict[str, Any]]) -> dict[str, Any]:
    required: dict[str, Any] = {}
    forbidden: dict[str, Any] = {}
    for change in changes:
        visual = change.get("visual_contract") or change.get("visual")
        if isinstance(visual, dict):
            typed = _typed_layer(visual, bucket="required")
            required = _deep_merge(required, typed.get("required") or {})
            forbidden = _deep_merge(forbidden, typed.get("forbidden") or {})
        category = str(change.get("category") or "")
        if category in VISUAL_PROFILE_CATEGORIES and "typed_value" in change:
            required[category] = deepcopy(change.get("typed_value"))
        if "value" in change:
            for inferred in _change_categories(change):
                slot = str(change.get("slot_id") or change.get("field") or "value")
                _set_path(required, (inferred, slot), deepcopy(change.get("value")))
        negative = change.get("forbidden")
        if isinstance(negative, dict):
            forbidden = _deep_merge(forbidden, negative)
    layer: dict[str, Any] = {}
    if required:
        layer["required"] = required
    if forbidden:
        layer["forbidden"] = forbidden
    return layer


def _flatten_layer(
    layer: dict[str, Any],
    *,
    source: str,
    rank: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    decision_id = str(layer.get("_decision_id") or "")
    for bucket in _BUCKETS:
        value = layer.get(bucket)
        if not isinstance(value, dict):
            continue
        for path, item in _flatten_dict(value):
            rows.append(
                {
                    "path": path,
                    "value": item,
                    "bucket": bucket,
                    "source": source,
                    "rank": rank,
                    "decision_id": decision_id,
                }
            )
    return rows


def _flatten_dict(value: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    rows: list[tuple[tuple[str, ...], Any]] = []
    for key, item in value.items():
        path = (*prefix, str(key))
        if isinstance(item, dict) and item:
            rows.extend(_flatten_dict(item, path))
        else:
            rows.append((path, deepcopy(item)))
    return rows


def _set_path(target: dict[str, Any], path: tuple[str, ...] | list[str], value: Any) -> None:
    cursor = target
    for key in path[:-1]:
        cursor = cursor.setdefault(str(key), {})
    if path:
        cursor[str(path[-1])] = value


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _contract_changes(contract: dict[str, Any]) -> list[dict[str, Any]]:
    import json

    rows: list[dict[str, Any]] = []
    for item in contract.get("acceptance") or []:
        if not isinstance(item, dict) or item.get("kind") != "semantic_change":
            continue
        try:
            value = json.loads(str(item.get("statement") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _change_categories(change: dict[str, Any]) -> set[str]:
    category = str(change.get("category") or "").strip()
    if category in VISUAL_PROFILE_CATEGORIES:
        return {category}
    text = " ".join(str(change.get(key) or "") for key in ("slot_id", "field", "kind", "operation")).lower()
    aliases = {
        "title": "titles",
        "hint": "hints",
        "kpi": "kpi",
        "table": "tables",
        "column": "tables",
        "series": "series",
        "line": "series",
        "legend": "legend",
        "axis": "axes",
        "tooltip": "tooltip",
        "selector": "selectors",
        "filter": "selectors",
        "format": "formatting",
        "color": "colors",
        "theme": "theme",
        "layout": "layout",
        "tab": "tabs",
        "empty": "data_states",
        "no_data": "data_states",
    }
    return {value for token, value in aliases.items() if token in text}


def _build_assertions(
    effective: dict[str, Any],
    *,
    contract: dict[str, Any],
    target_graph: dict[str, Any],
    active_provenance_hash: str,
    provenance_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    constrained = _deep_merge(
        dict(effective.get("required") or {}),
        dict(effective.get("forbidden") or {}),
    )
    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    scope = contract.get("scope") if isinstance(contract.get("scope"), dict) else {}
    object_ids = sorted(
        {
            *[str(value) for value in target.get("object_ids") or []],
            *[str(value) for value in scope.get("allowed_objects") or []],
        }
        - {""}
    )
    graph_tab_ids = {
        str(item.get("tab_id") or "")
        for item in target_graph.get("nodes") or []
        if isinstance(item, dict) and str(item.get("tab_id") or "")
    }
    scoped_tab_ids = {str(value) for value in scope.get("allowed_tabs") or []} - {""}
    tab_ids = sorted((scoped_tab_ids & graph_tab_ids) or graph_tab_ids)
    assertions: list[dict[str, Any]] = []
    for category, assertion_id in _ASSERTION_IDS.items():
        if category not in constrained:
            continue
        sources = {
            str(item.get("source") or "")
            for item in provenance_rows
            if str(item.get("path") or "").startswith(category + ".")
        }
        assertion_scope = "task" if "current_user" in sources or "task_correction" in sources else "project"
        if sources == {"accepted_exemplar"}:
            assertion_scope = "exemplar"
        elif sources == {"portfolio_family"}:
            assertion_scope = "portfolio"
        assertions.append(
            {
                "assertion_id": assertion_id,
                "scope": assertion_scope,
                "source_ref": f"effective_visual_contract:{category}",
                "profile_or_exemplar_hash": active_provenance_hash,
                "applies_to_object_ids": object_ids,
                "applies_to_tab_ids": tab_ids,
                "expected": deepcopy(constrained[category]),
            }
        )
    return assertions


def _target_projection(contract: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
    return {
        "workbook_id": str(
            target.get("workbook_id")
            or next(
                (item.get("workbook_id") for item in nodes if item.get("workbook_id")),
                "",
            )
            or ""
        ),
        "dashboard_id": str(target.get("dashboard_id") or ""),
        "object_ids": sorted({str(item.get("object_id") or "") for item in nodes} - {""}),
        "saved_revisions": {
            str(item.get("object_id") or ""): str(item.get("saved_revision") or "")
            for item in nodes
            if item.get("object_id")
        },
    }


def _technology(
    contract: dict[str, Any],
    graph: dict[str, Any],
    style_binding: dict[str, Any],
) -> str:
    technologies = {
        str(item.get("technology") or "")
        for item in graph.get("nodes") or []
        if isinstance(item, dict)
        and "chart" in str(item.get("object_type") or "")
        and str(item.get("technology") or "")
    }
    if len(technologies) == 1:
        return next(iter(technologies))
    return str(style_binding.get("technology") or contract.get("route") or ("mixed" if technologies else ""))


def _portfolio_contract(style_binding: dict[str, Any]) -> dict[str, Any]:
    value = style_binding.get("portfolio_visual_contract")
    return dict(value) if isinstance(value, dict) else {}


def _universal_defaults() -> dict[str, Any]:
    return {
        "layout": {"overflow": "do_not_clip"},
        "advanced_editor": {"preserve_unknown_runtime": True},
        "data_states": {"errors": "surface", "empty": "explicit"},
    }
