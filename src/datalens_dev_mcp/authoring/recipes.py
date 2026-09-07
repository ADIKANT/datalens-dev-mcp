from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from typing import Any

from datalens_dev_mcp.authoring.models import DraftBundle
from datalens_dev_mcp.authoring.profiles import _deep_merge, get_authoring_defaults


def _registry() -> dict[str, Any]:
    resource = files("datalens_dev_mcp.assets.recipes").joinpath("registry.json")
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("recipe registry must contain an object")
    return value


def list_recipes() -> dict[str, dict[str, Any]]:
    registry = _registry()
    base = dict(registry["base_visual_contract"])
    result: dict[str, dict[str, Any]] = {}
    for recipe_id, raw in registry["recipes"].items():
        recipe = deepcopy(raw)
        recipe["id"] = recipe_id
        recipe["visual_contract"] = _deep_merge(base, dict(recipe.get("visual_contract") or {}))
        result[recipe_id] = recipe
    return result


def compile_recipe(
    recipe_id: str,
    bindings: Mapping[str, Any],
    presentation: Mapping[str, Any] | None = None,
    output_dir: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    reference: Mapping[str, Any] | None = None,
    user_config_path: str | Path | None = None,
) -> DraftBundle:
    recipes = list_recipes()
    if recipe_id not in recipes:
        raise ValueError(f"unknown recipe_id: {recipe_id}")
    recipe = recipes[recipe_id]
    missing = [key for key in recipe["required_bindings"] if key not in bindings]
    if missing:
        raise ValueError(f"missing recipe bindings: {', '.join(missing)}")
    defaults = get_authoring_defaults(
        project_root=project_root,
        family=recipe_id,
        explicit=presentation,
        reference=reference,
        user_config_path=user_config_path,
    )
    values = defaults["values"]
    contract = _apply_profile(recipe["visual_contract"], values)
    contract = _bind_contract(contract, bindings)
    technology = str(values.get("technology") or recipe["technology"])
    if "technology" not in (presentation or {}) and "technology" not in (reference or {}):
        configured = "technology" in values and values["technology"] != "wizard"
        technology = str(values["technology"]) if configured else str(recipe["technology"])
    draft: dict[str, Any] = {
        "recipe_id": recipe_id,
        "technology": technology,
        "object_type": _object_type_for(recipe, technology),
        "bindings": deepcopy(dict(bindings)),
        "config": contract,
        "visual_contract": contract,
        "example": deepcopy(recipe["example"]),
    }
    if recipe_id == "native_detail_table" and technology == "wizard":
        draft.update(_native_table_draft(bindings, contract))
    if recipe_id == "categorical_bar" and technology == "wizard":
        draft.update(_categorical_bar_draft(bindings, contract))
    if recipe_id == "cross_tab_totals" and technology == "wizard":
        draft.update(_pivot_draft(bindings, contract))
    if recipe_id == "time_comparison" and technology == "wizard":
        draft.update(_time_comparison_draft(bindings, contract))
    renderer_name = recipe.get("renderer")
    renderer_text = ""
    if renderer_name:
        renderer_text = files("datalens_dev_mcp.assets.recipes").joinpath(str(renderer_name)).read_text(encoding="utf-8")
        variant = draft["object_type"]
        draft["variant"] = variant
        draft["tabs"] = _editor_tabs(str(variant), renderer_text, contract, bindings)
        if variant == "control_node":
            draft["name"] = contract["object_name"]["value"] or str(bindings["parameter"]["name"])
            draft["client_ref"] = str(bindings.get("client_ref") or "selector")
    file_map: dict[str, str] = {}
    if output_dir is not None:
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        bundle_path = destination / "draft.json"
        bundle_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        file_map["draft.json"] = str(bundle_path)
        if renderer_text:
            renderer_path = destination / "renderer.js"
            renderer_path.write_text(renderer_text, encoding="utf-8")
            file_map["renderer.js"] = str(renderer_path)
    return {
        "ok": True,
        "recipe_id": recipe_id,
        "draft": draft,
        "files": file_map,
        "summary": {
            "technology": technology,
            "object_type": draft["object_type"],
            "visual_contract": contract,
            "renderer_reused": bool(renderer_name),
            "network_calls": 0,
            "datalens_writes": 0,
        },
        "defaults": defaults,
    }


def _time_comparison_draft(bindings: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    dataset_id = bindings.get("dataset_id")
    name = contract["object_name"]["value"]
    if not isinstance(dataset_id, str) or not dataset_id.strip() or not name:
        raise ValueError("time_comparison requires dataset_id and object_name or metric label")
    refs = {}
    for key in ("date", "metric", "comparison"):
        value = bindings[key]
        if not isinstance(value, Mapping) or not isinstance(value.get("field_guid"), str) or not value["field_guid"]:
            raise ValueError(f"{key} requires an explicit field_guid; comparison formulas are not inferred")
        refs[key] = value["field_guid"]
    comparison = bindings["comparison"]
    if not comparison.get("method") or not comparison.get("alignment"):
        raise ValueError("comparison requires explicit method and alignment semantics")
    if refs["comparison"] == refs["metric"]:
        raise ValueError("current and comparison must be distinct fields")
    title = contract["visible_title"]
    return {
        "name": name, "client_ref": str(bindings.get("client_ref") or "time_comparison"),
        "wizard": {
            "visualization": "line", "dataset_id": dataset_id,
            "roles": {"x": [refs["date"]], "y": [refs["metric"], refs["comparison"]]},
            "title": str(title.get("text") or name),
            "title_mode": "show" if title.get("visible") and title.get("owner") == "chart" else "hide",
            "grid": {"x": contract["axes_gridlines"]["x_grid"], "y": contract["axes_gridlines"]["y_grid"]},
            "legend": "hide" if contract["legend"]["mode"] == "hidden" else "show",
            "sort": deepcopy(bindings.get("sort") or [{"field_guid": refs["date"], "direction": "asc"}]),
        },
    }


def _pivot_draft(bindings: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    dataset_id = bindings.get("dataset_id")
    name = contract["object_name"]["value"]
    if not isinstance(dataset_id, str) or not dataset_id.strip() or not name:
        raise ValueError("cross_tab_totals requires dataset_id and object_name")
    roles = {}
    for source, role in (("rows", "rows"), ("columns", "columns"), ("measures", "y")):
        values = bindings[source]
        if not isinstance(values, list) or not values:
            raise ValueError(f"cross_tab_totals requires nonempty {source}")
        if any(not isinstance(v, Mapping) or not isinstance(v.get("field_guid"), str) or not v["field_guid"] for v in values):
            raise ValueError(f"{source} require field_guid from Dataset readback")
        roles[role] = [v["field_guid"] for v in values]
    title, table = contract["visible_title"], contract["table"]
    if table.get("total_position") not in {"bottom_and_right", "none"}:
        raise ValueError("cross_tab_totals supports bottom_and_right or none")
    return {
        "name": name, "client_ref": str(bindings.get("client_ref") or "cross_tab_totals"),
        "wizard": {
            "visualization": "pivot_table", "dataset_id": dataset_id, "roles": roles,
            "title": str(title.get("text") or name),
            "title_mode": "show" if title.get("visible") and title.get("owner") == "chart" else "hide",
            "subtotals": [roles["rows"][0], roles["columns"][0]] if table.get("total_position") != "none" else [],
            "table": {"pagination": table.get("pagination", True), "page_size": table.get("page_size", 100),
                      "size": table.get("size", "m")},
            "sort": deepcopy(bindings.get("sort") or []),
        },
    }


def _categorical_bar_draft(bindings: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    dataset_id = bindings.get("dataset_id")
    name = contract["object_name"]["value"]
    if not isinstance(dataset_id, str) or not dataset_id.strip() or not name:
        raise ValueError("categorical_bar requires dataset_id and object_name or metric label")
    refs = {}
    for key in ("category", "metric"):
        value = bindings[key]
        if not isinstance(value, Mapping) or not isinstance(value.get("field_guid"), str) or not value["field_guid"]:
            raise ValueError(f"{key} requires a field_guid from Dataset readback")
        refs[key] = value["field_guid"]
    # Horizontal bars: measure X, category Y (not the column-chart mapping).
    roles = {"x": [refs["metric"]], "y": [refs["category"]]}
    if contract["labels"].get("visible"):
        roles["labels"] = [refs["metric"]]
    title = contract["visible_title"]
    return {
        "name": name, "client_ref": str(bindings.get("client_ref") or "categorical_bar"),
        "wizard": {
            "visualization": "bar", "dataset_id": dataset_id, "roles": roles,
            "title": str(title.get("text") or name),
            "title_mode": "show" if title.get("visible") and title.get("owner") == "chart" else "hide",
            "grid": {"x": contract["axes_gridlines"]["x_grid"], "y": contract["axes_gridlines"]["y_grid"]},
            "legend": "hide" if contract["legend"]["mode"] == "hidden" else "show",
            "labels_position": contract["labels"].get("position", "outside"),
            "sort": deepcopy(bindings.get("sort") or []),
        },
    }


def _native_table_draft(bindings: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    dataset_id = bindings.get("dataset_id")
    name = contract["object_name"]["value"]
    if not isinstance(dataset_id, str) or not dataset_id.strip() or not name:
        raise ValueError("native_detail_table requires dataset_id and object_name")
    columns = bindings["columns"]
    if not isinstance(columns, list) or not columns:
        raise ValueError("native_detail_table requires nonempty columns with field_guid")
    guids, titles = [], {}
    for column in columns:
        if not isinstance(column, Mapping) or not isinstance(column.get("field_guid"), str) or not column["field_guid"]:
            raise ValueError("each native table column requires field_guid from Dataset readback")
        guid = column["field_guid"]
        if guid in guids:
            raise ValueError("native table columns must have distinct field GUIDs")
        guids.append(guid)
        if column.get("label"):
            titles[guid] = str(column["label"])
    title = contract["visible_title"]
    table = contract["table"]
    return {
        "name": name,
        "client_ref": str(bindings.get("client_ref") or "native_detail_table"),
        "wizard": {
            "visualization": "flat_table", "dataset_id": dataset_id,
            "roles": {"columns": guids}, "column_titles": titles,
            "title": str(title.get("text") or name),
            "title_mode": "show" if title.get("visible") and title.get("owner") == "chart" else "hide",
            "table": {"pagination": table.get("pagination", True), "page_size": table.get("page_size", 100),
                      "totals": table.get("total_position") == "bottom", "size": table.get("size", "m")},
            "sort": deepcopy(bindings.get("sort") or []),
        },
    }


def _apply_profile(contract: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(contract))
    if isinstance(values.get("visible_title"), Mapping):
        result["visible_title"] = _deep_merge(result["visible_title"], values["visible_title"])
    elif isinstance(values.get("title"), Mapping):
        result["visible_title"] = _deep_merge(result["visible_title"], values["title"])
    if isinstance(values.get("hint"), Mapping):
        result["hint"] = _deep_merge(result["hint"], values["hint"])
    if values.get("theme"):
        result["states_theme"]["theme"] = values["theme"]
    if values.get("spacing") is not None:
        result["geometry"]["spacing"] = values["spacing"]
    for key in result:
        if isinstance(values.get(key), Mapping):
            result[key] = _deep_merge(result[key], values[key])
    return result


def _bind_contract(contract: Mapping[str, Any], bindings: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(contract))
    metric = bindings.get("metric") if isinstance(bindings.get("metric"), Mapping) else {}
    object_name = bindings.get("object_name") or metric.get("label") or ""
    result["object_name"]["value"] = str(object_name)
    if metric:
        if not result["visible_title"].get("text"):
            result["visible_title"]["text"] = str(metric.get("label") or "")
        result["labels"]["unit"] = metric.get("unit") or result["labels"].get("unit")
        result["tooltip"]["unit"] = metric.get("unit") or True
    comparison = bindings.get("comparison") if isinstance(bindings.get("comparison"), Mapping) else {}
    if comparison:
        result["comparison"] = _deep_merge(result["comparison"], comparison)
    parameter = bindings.get("parameter") if isinstance(bindings.get("parameter"), Mapping) else {}
    if parameter:
        result["selector"] = _deep_merge(
            result["selector"],
            {
                "param_name": parameter.get("name", ""),
                "type": parameter.get("type", "string"),
                "default": parameter.get("default"),
            },
        )
    if isinstance(bindings.get("consumers"), list):
        result["selector"]["consumers"] = list(bindings["consumers"])
    if isinstance(bindings.get("columns"), list):
        result["table"]["columns"] = deepcopy(bindings["columns"])
    return result


def _object_type_for(recipe: Mapping[str, Any], technology: str) -> str:
    if technology in {"advanced_chart", "advanced-chart_node"}:
        return "advanced-chart_node"
    if technology in {"selector", "control_node"}:
        return "control_node"
    if technology in {"table", "table_node"}:
        return "table_node"
    if technology in {"gravity", "d3_node"}:
        return "d3_node"
    if technology in {"markdown", "markdown_node"}:
        return "markdown_node"
    return str(recipe["object_type"])


def _editor_tabs(
    variant: str,
    renderer: str,
    contract: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> dict[str, str]:
    tabs = {
        "meta.json": json.dumps({"variant": variant}, sort_keys=True),
        "params.js": "module.exports = {};\n",
    }
    if variant != "control_node":
        tabs["sources.js"] = "module.exports = {source: {kind: 'binding'}};\n"
    if variant == "control_node":
        parameter = bindings.get("parameter") or {}
        name = parameter.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("selector requires a parameter name")
        options = bindings.get("options")
        if not isinstance(options, list):
            raise ValueError("selector requires explicit options; dynamic sources need a source-backed draft")
        normalized = []
        for option in options:
            if isinstance(option, Mapping):
                if "value" not in option or "title" not in option:
                    raise ValueError("selector options require title and value")
                normalized.append({"title": str(option["title"]), "value": str(option["value"])})
            elif isinstance(option, (str, int, float)) and not isinstance(option, bool):
                normalized.append({"title": str(option), "value": str(option)})
            else:
                raise ValueError("selector option must be a scalar or title/value object")
        if len({option["value"] for option in normalized}) != len(normalized):
            raise ValueError("selector option values must be unique")
        default = parameter.get("default")
        defaults = default if isinstance(default, list) else ([] if default is None else [default])
        defaults = [str(value) for value in defaults]
        if any(value not in {option["value"] for option in normalized} for value in defaults):
            raise ValueError("selector default must be present in options")
        if contract["selector"]["mode"] != "multi" and len(defaults) > 1:
            raise ValueError("single selector cannot have multiple defaults")
        if not contract["selector"]["clear"] and not defaults:
            raise ValueError("required selector needs a default")
        tabs["meta.json"] = "{}"
        tabs["params.js"] = "module.exports = " + json.dumps({name: defaults}, ensure_ascii=False) + ";\n"
        tabs["controls.js"] = renderer + "\nmodule.exports = module.exports(" + json.dumps(normalized, ensure_ascii=False) + ", " + json.dumps(contract, ensure_ascii=False) + ");\n"
        return tabs
    else:
        tabs["prepare.js"] = renderer
        tabs["controls.js"] = "module.exports = {};\n"
    tabs["config.json"] = json.dumps({"visual_contract": contract, "bindings": bindings}, ensure_ascii=False, sort_keys=True)
    return tabs
