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
    if bindings.get("direct_source") and "source" not in bindings:
        from datalens_dev_mcp.authoring.dataset_source import compile_direct_source

        bindings = {**bindings, "source": compile_direct_source(bindings["direct_source"])}
    if recipe_id == "comparison_matrix" and bindings.get("dataset_id") and "source" not in bindings:
        from datalens_dev_mcp.authoring.dataset_source import matrix_dataset_source

        bindings = {**bindings, "source": matrix_dataset_source(bindings)}
    if recipe_id == "kpi_sparkline" and bindings.get("dataset_id") and "source" not in bindings:
        from datalens_dev_mcp.authoring.dataset_source import kpi_dataset_source

        bindings = {**bindings, "source": kpi_dataset_source(bindings)}
    if (
        recipe_id == "weekly_totals_table"
        and bindings.get("dataset_id")
        and "source" not in bindings
        and "prepared_data" not in bindings
    ):
        from datalens_dev_mcp.authoring.dataset_source import weekly_dataset_source

        bindings = {**bindings, "source": weekly_dataset_source(bindings)}
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
    if recipe_id == "kpi_sparkline":
        contract = _kpi_semantics(contract, bindings, values)
    technology = str(recipe["technology"] if defaults["technology_source"] == "generic" else values.get("technology"))
    technology = {
        "advanced-chart_node": "advanced_chart",
        "control_node": "selector",
        "table_node": "table",
        "d3_node": "gravity",
        "markdown_node": "markdown",
    }.get(technology, technology)
    if technology != recipe["technology"]:
        raise ValueError(
            f"recipe {recipe_id} does not support technology {technology}; choose a matching recipe or author an explicit custom draft"
        )
    _validate_prepared_data(recipe_id, bindings)
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
        renderer_text = (
            files("datalens_dev_mcp.assets.recipes").joinpath(str(renderer_name)).read_text(encoding="utf-8")
        )
        variant = draft["object_type"]
        draft["variant"] = variant
        renderer_contract = contract
        if recipe_id == "kpi_sparkline":
            renderer_contract = deepcopy(contract)
            renderer_contract["hint"]["enabled"] = (
                bool(contract["hint"].get("enabled")) and contract["hint"].get("owner") == "body"
            )
        draft["tabs"] = _editor_tabs(str(variant), renderer_text, renderer_contract, bindings, recipe_id=recipe_id)
        draft["name"] = contract["object_name"]["value"] or str(
            (bindings.get("parameter") or {}).get("name") or recipe_id
        )
        draft["client_ref"] = str(bindings.get("client_ref") or recipe_id)
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
        "name": name,
        "client_ref": str(bindings.get("client_ref") or "time_comparison"),
        "wizard": {
            "visualization": "line",
            "dataset_id": dataset_id,
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
        if any(
            not isinstance(v, Mapping) or not isinstance(v.get("field_guid"), str) or not v["field_guid"]
            for v in values
        ):
            raise ValueError(f"{source} require field_guid from Dataset readback")
        roles[role] = [v["field_guid"] for v in values]
    title, table = contract["visible_title"], contract["table"]
    if table.get("total_position") not in {"bottom_and_right", "none"}:
        raise ValueError("cross_tab_totals supports bottom_and_right or none")
    return {
        "name": name,
        "client_ref": str(bindings.get("client_ref") or "cross_tab_totals"),
        "wizard": {
            "visualization": "pivot_table",
            "dataset_id": dataset_id,
            "roles": roles,
            "title": str(title.get("text") or name),
            "title_mode": "show" if title.get("visible") and title.get("owner") == "chart" else "hide",
            "subtotals": [roles["rows"][0], roles["columns"][0]] if table.get("total_position") != "none" else [],
            "table": {
                "pagination": table.get("pagination", True),
                "page_size": table.get("page_size", 100),
                "size": table.get("size", "m"),
            },
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
        "name": name,
        "client_ref": str(bindings.get("client_ref") or "categorical_bar"),
        "wizard": {
            "visualization": "bar",
            "dataset_id": dataset_id,
            "roles": roles,
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
            "visualization": "flat_table",
            "dataset_id": dataset_id,
            "roles": {"columns": guids},
            "column_titles": titles,
            "title": str(title.get("text") or name),
            "title_mode": "show" if title.get("visible") and title.get("owner") == "chart" else "hide",
            "table": {
                "pagination": table.get("pagination", True),
                "page_size": table.get("page_size", 100),
                "totals": table.get("total_position") == "bottom",
                "size": table.get("size", "m"),
            },
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


def _kpi_semantics(contract: Mapping[str, Any], bindings: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    """Metric semantics seed defaults; accepted profiles/reference/explicit values win."""
    result = deepcopy(dict(contract))
    metric = bindings.get("metric") if isinstance(bindings.get("metric"), Mapping) else {}
    configured = values.get("kpi") if isinstance(values.get("kpi"), Mapping) else {}
    allowed = {
        "direction": {"higher_is_better", "lower_is_better", "neutral"},
        "delta_kind": {"relative", "absolute", "percentage_points"},
        "value_scale": {"fraction", "percent", None},
    }
    for key, choices in allowed.items():
        value = configured.get(key, metric.get(key, result["kpi"].get(key)))
        if not isinstance(value, (str, type(None))) or value not in choices:
            raise ValueError(f"kpi {key} must be one of {sorted(str(item) for item in choices)}")
        result["kpi"][key] = value
    if result["kpi"]["delta_kind"] == "percentage_points" and not result["kpi"]["value_scale"]:
        raise ValueError("kpi percentage_points requires value_scale fraction or percent")
    if result["kpi"]["value_scale"]:
        result["labels"]["unit"] = "%"
        result["tooltip"]["unit"] = "%"
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
    if isinstance(metric.get("precision"), int):
        result["labels"]["precision"] = max(0, min(10, metric["precision"]))
    semantics = str(metric.get("aggregation") or metric.get("role") or "sum").lower()
    result["table"]["totals_additive"] = semantics not in {
        "ratio", "average", "avg", "count_distinct", "unique", "uniq", "uniqexact"
    }
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
    *,
    recipe_id: str | None = None,
) -> dict[str, str]:
    tabs = {
        "meta.json": json.dumps({"variant": variant}, sort_keys=True),
        "params.js": "module.exports = {};\n",
    }
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
                raise TypeError("selector option must be a scalar or title/value object")
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
        tabs["controls.js"] = (
            renderer
            + "\nmodule.exports = module.exports("
            + json.dumps(normalized, ensure_ascii=False)
            + ", "
            + json.dumps(contract, ensure_ascii=False)
            + ");\n"
        )
        return tabs
    else:
        source = bindings.get("source")
        if isinstance(source, Mapping):
            if (
                not isinstance(source.get("meta"), Mapping)
                or not isinstance(source.get("sources_js"), str)
                or not isinstance(source.get("prepare_js"), str)
            ):
                raise TypeError("source requires meta object, sources_js and prepare_js strings")
            tabs["meta.json"] = json.dumps(source["meta"], ensure_ascii=False)
            source_params = source.get("params") or {}
            if not isinstance(source_params, Mapping):
                raise TypeError("source params must be an object")
            tabs["params.js"] = "module.exports = " + json.dumps(dict(source_params), ensure_ascii=False) + ";\n"
            tabs["sources.js"] = source["sources_js"]
            prepared = (
                "(() => { const module = {exports: {}};\n" + source["prepare_js"] + "\nreturn module.exports; })()"
            )
        elif "prepared_data" in bindings and isinstance(bindings["prepared_data"], Mapping):
            tabs["meta.json"] = "{}"
            tabs["sources.js"] = "module.exports = {};\n"
            prepared = json.dumps(bindings["prepared_data"], ensure_ascii=False)
        else:
            raise ValueError(
                "Advanced recipe requires explicit source or prepared_data; no placeholder source is generated"
            )
        if recipe_id in {"kpi_sparkline", "period_series"}:
            temporal = files("datalens_dev_mcp.assets.recipes").joinpath("temporal_prepare.js").read_text(encoding="utf-8")
            date = dict(bindings.get("date") or {})
            if (bindings.get("comparison") or {}).get("alignment") == "ordinal":
                date.setdefault("mode", "ordinal")
            prepared = (
                "(() => { const module = {exports: {}};\n" + temporal
                + "\nreturn module.exports(" + prepared + ", " + json.dumps(date)
                + ", " + json.dumps(recipe_id) + "); })()"
            )
        tabs["prepare.js"] = (
            renderer
            + "\nmodule.exports = module.exports("
            + prepared
            + ", "
            + json.dumps(contract, ensure_ascii=False)
            + ");\n"
        )
        tabs["controls.js"] = "module.exports = {controls: []};\n"
    return tabs


def _validate_prepared_data(recipe_id: str, bindings: Mapping[str, Any]) -> None:
    prepared = bindings.get("prepared_data")
    if not isinstance(prepared, Mapping) or not prepared:
        return
    if recipe_id == "weekly_totals_table":
        metric = bindings.get("metric") or {}
        semantics = str(metric.get("aggregation") or metric.get("role") or "sum").lower()
        if semantics in {"ratio", "average", "avg", "count_distinct", "unique", "uniq", "uniqexact"} and (
            "total_values" not in prepared or "grand_total" not in prepared or any(
                "total" not in row for row in prepared.get("rows", [])
            )
        ):
            raise ValueError("non-additive weekly measures require source-computed totals")
        return
    if recipe_id == "period_series":
        categories, series = prepared.get("categories"), prepared.get("series")
        if not isinstance(categories, list) or not isinstance(series, list):
            raise ValueError("period_series requires aligned categories and series")
        for item in series:
            if not isinstance(item, Mapping) or item.get("type") not in {"line", "bar"}:
                raise ValueError("period_series requires line/bar series")
            for key in ("values", "comparisonValues"):
                if (key == "values" or key in item) and (
                    not isinstance(item.get(key), list) or len(item[key]) != len(categories)
                ):
                    raise ValueError("period_series values must be aligned with categories")
        for key in ("comparisonCategories", "currentRanges", "comparisonRanges"):
            if key in prepared and (not isinstance(prepared[key], list) or len(prepared[key]) != len(categories)):
                raise ValueError("period_series periods must be aligned with categories")
        return
    if recipe_id == "kpi_sparkline":
        required = {"value", "previous", "points"}
        if not required.issubset(prepared):
            raise ValueError("kpi_sparkline prepared_data requires value, previous and points")
        points = prepared["points"]
        if not isinstance(points, list) or any(
            not isinstance(point, Mapping) or "date" not in point or "value" not in point for point in points
        ):
            raise ValueError("kpi_sparkline prepared_data points must contain date/value objects")
        return
    if recipe_id != "comparison_matrix":
        return
    rows = prepared.get("rows")
    if not isinstance(rows, list):
        raise TypeError("comparison_matrix prepared_data rows must be a list")
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("comparison_matrix prepared_data rows must contain objects")
    columns = prepared.get("columns") or []
    if not isinstance(columns, list) or any(not isinstance(column, Mapping) for column in columns):
        raise ValueError("comparison_matrix prepared_data columns must contain objects")
    for column in columns:
        if not isinstance(column.get("key"), str) or not column["key"] or not isinstance(column.get("headers"), list):
            raise ValueError("comparison_matrix prepared_data columns require key and headers")
    for row in rows:
        if "cells" in row:
            cells = row["cells"]
            if not isinstance(cells, list) or any(
                not isinstance(cell, Mapping) or "value" not in cell for cell in cells
            ):
                raise ValueError("comparison_matrix prepared_data cells must contain value objects")
        elif not {"current", "previous"}.issubset(row):
            raise ValueError("comparison_matrix prepared_data rows require cells or current/previous values")
