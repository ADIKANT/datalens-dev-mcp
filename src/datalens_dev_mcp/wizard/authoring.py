from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from datalens_sdk import DataLensClientYC, Dataset, WizardLocalField, Workbook
from datalens_sdk.converter.wizard import WizardChartConverter

from datalens_dev_mcp.api.sdk_adapter import SDK_VERSION, WIZARD_VARIANTS
from datalens_dev_mcp.authoring.profiles import get_authoring_defaults
from datalens_dev_mcp.dataset.contracts import (
    TECHNICAL_MEASURES,
    validate_dataset_fields,
    validate_visualization_fields,
    wire_fields,
)


def wizard_builder(client: Any, dataset: Dataset, specification: Mapping[str, Any], *, name: str, location: Any) -> Any:
    """Configure the official builder using GUIDs resolved from Dataset readback.

    Returning a builder is local work; only its caller may invoke build().
    Role names are deliberately not arbitrary SDK method names.
    """
    specification, profile = resolve_wizard_presentation(specification)
    visualization = str(specification.get("visualization") or "")
    if visualization not in WIZARD_VARIANTS:
        raise ValueError(f"unsupported Wizard visualization: {visualization}")
    allowed = {
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
        "family", "project_root", "presentation", "grid_reason", "measure_colors",
    }
    if set(specification) - allowed:
        raise ValueError(f"unsupported Wizard settings: {sorted(set(specification) - allowed)}")
    roles = specification.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("wizard.roles must contain explicit field GUID assignments")
    used_guids = [guid for guids in roles.values() if isinstance(guids, list) for guid in guids]
    used_guids.extend(order["field_guid"] for order in specification.get("sort", []))
    report = validate_visualization_fields(list(dataset.result_schema), used_guids)
    if not report["ok"]:
        raise ValueError(report["issues"][0]["message"])
    builder = getattr(client.create.wizard_chart, visualization)(name=name, location=location).dataset(dataset)
    for role, guids in roles.items():
        if role not in {"x", "y", "y2", "columns", "rows", "measures", "colors", "labels", "size", "shapes"}:
            raise ValueError(f"unsupported Wizard field role: {role}")
        method = getattr(builder, role, None)
        if not callable(method) or not isinstance(guids, list) or not guids:
            raise ValueError(f"{visualization} requires a supported nonempty field role: {role}")
        resolved = []
        for guid in guids:
            if not isinstance(guid, str) or guid.lower() in TECHNICAL_MEASURES:
                raise ValueError("Wizard field roles require Dataset GUIDs, not technical measures")
            resolved.append(dataset.fields.by_guid(guid))
        method(resolved)
    if specification.get("title") or "title_mode" in specification:
        mode = specification.get("title_mode", "show")
        if mode not in {"show", "hide"}:
            raise ValueError("title_mode must be show or hide")
        _setter(builder, "chart_title")(text=str(specification.get("title") or ""), mode=mode)
    for order in specification.get("sort", []):
        if order.get("direction") not in {"asc", "desc"}:
            raise ValueError("sort direction must be asc or desc")
        builder.add_sort(dataset.fields.by_guid(order["field_guid"]), direction=order["direction"])
    table = specification.get("table")
    if table is not None:
        if visualization not in {"flat_table", "pivot_table"} or not isinstance(table, dict):
            raise ValueError("table settings require flat_table or pivot_table")
        if set(table) - {"pagination", "page_size", "totals", "size", "freeze_columns"}:
            raise ValueError("unsupported native table setting")
        page_size = table.get("page_size", 100)
        if type(page_size) is not int or page_size < 1:
            raise ValueError("page_size must be a positive integer")
        builder.pagination(enabled=bool(table.get("pagination", True)), limit=page_size)
        if visualization == "flat_table":
            builder.totals(enabled=bool(table.get("totals", False)))
        elif "totals" in table:
            raise ValueError("pivot totals are per-dimension subtotals, not flat table totals")
        size = table.get("size", "m")
        if size not in {"s", "m", "l"}:
            raise ValueError("table size must be s, m or l")
        builder.table_size(size=size)
        if "freeze_columns" in table:
            count = table["freeze_columns"]
            if type(count) is not int or count < 0:
                raise ValueError("freeze_columns must be a nonnegative integer")
            builder.freeze_columns(count=count)
    for guid in specification.get("subtotals", []):
        if visualization != "pivot_table" or guid not in roles.get("rows", []) + roles.get("columns", []):
            raise ValueError("subtotals require a pivot row or column field")
        builder.subtotals(dataset.fields.by_guid(guid), enabled=True)
    for guid, title in specification.get("column_titles", {}).items():
        if visualization != "flat_table":
            raise ValueError("column_titles require flat_table")
        builder.column_title(dataset.fields.by_guid(guid), title=str(title))
    for axis, enabled in specification.get("grid", {}).items():
        if axis not in {"x", "y", "y2"} or type(enabled) is not bool or not callable(getattr(builder, "grid", None)):
            raise ValueError("grid requires a supported x/y/y2 axis and boolean value")
        builder.grid(axis, enabled=enabled)
    if "legend" in specification:
        if specification["legend"] not in {"show", "hide"}:
            raise ValueError("legend must be show or hide")
        _setter(builder, "legend")(mode=specification["legend"])
    if "labels_position" in specification:
        if specification["labels_position"] not in {"inside", "outside", "auto"}:
            raise ValueError("labels_position must be inside, outside or auto")
        _setter(builder, "labels_position")(mode=specification["labels_position"])
    labels = profile["values"]["labels"]
    for field in dataset.result_schema:
        if str(field.get("type", "")).upper() != "MEASURE" or field.get("guid") not in used_guids:
            continue
        formatting = {}
        if isinstance(labels.get("precision"), int):
            formatting["precision"] = labels["precision"]
        if labels.get("unit") not in {None, "", "from_field", "count"}:
            formatting["postfix"] = " " + str(labels["unit"])
        if formatting:
            _setter(builder, "measure_format")(dataset.fields.by_guid(field["guid"]), **formatting)
    colors = specification.get("measure_colors")
    if colors is not None:
        if not isinstance(colors, Mapping) or not colors:
            raise ValueError("wizard/measure_colors must map measure GUIDs to stable colors")
        measures = set(roles.get("y", []) + roles.get("y2", []))
        if set(colors) != measures:
            raise ValueError("wizard/measure_colors must assign every y/y2 measure GUID exactly once")
        _setter(builder, "color_by_measure_name")(colors_map={dataset.fields.by_guid(k): v for k, v in colors.items()})
    return builder


def resolve_wizard_presentation(specification: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the same effective contract to recipes and direct new Wizard objects."""
    result = deepcopy(dict(specification))
    visualization = result.get("visualization")
    family = result.get("family") or {"bar": "categorical_bar", "line": "time_comparison",
                                     "flat_table": "native_detail_table", "pivot_table": "cross_tab_totals"}.get(visualization)
    profile = get_authoring_defaults(project_root=result.get("project_root"), family=family,
                                     explicit=result.get("presentation"))
    values = profile["values"]
    title = values["visible_title"]
    result.setdefault("title", title.get("text", ""))
    result.setdefault("title_mode", "show" if title.get("visible") and title.get("owner") == "chart" else "hide")
    if values.get("legend") and visualization not in {"flat_table", "pivot_table", "indicator"}:
        result.setdefault("legend", "hide" if values["legend"].get("mode") == "hidden" else "show")
    if visualization in {"flat_table", "pivot_table"} and values.get("table"):
        table = values["table"]
        settings = {key: table[key] for key in ("pagination", "page_size", "size", "freeze_columns") if key in table}
        if visualization == "flat_table":
            settings["totals"] = table.get("total_position") == "bottom"
        elif table.get("total_position") == "bottom_and_right":
            roles = result.get("roles") or {}
            result.setdefault("subtotals", roles.get("rows", [])[:1] + roles.get("columns", [])[:1])
        result["table"] = {**settings, **result.get("table", {})}
        if isinstance(table.get("widths"), Mapping):
            raise ValueError("wizard/presentation/table/widths: explicit column widths require a supported Editor table family")
    if visualization in {"line", "column", "bar", "column_100p", "bar_100p", "area", "area_100p"}:
        roles = result.get("roles")
        if isinstance(roles, dict):
            if any(not isinstance(guids, list) or any(not isinstance(guid, str) or not guid for guid in guids)
                   for guids in roles.values()):
                raise ValueError("wizard/roles: fields must be nonempty GUID strings in arrays")
            measures = roles.get("x" if visualization in {"bar", "bar_100p"} else "y", []) + roles.get("y2", [])
            if len(measures) > 1 and visualization in {"line", "column"} and "measure_colors" not in result:
                palette = ("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7")
                colors = {guid: palette[int(hashlib.sha256(guid.encode()).hexdigest(), 16) % len(palette)] for guid in measures}
                if len(set(colors.values())) != len(colors):
                    raise ValueError("wizard/measure_colors: finite palette collision; supply explicit stable GUID-to-color assignments")
                result["measure_colors"] = colors
            if values["labels"].get("visible") and "labels" not in roles:
                roles["labels"] = deepcopy(measures)
            if not values["labels"].get("visible"):
                roles.pop("labels", None)
            if roles.get("labels") and visualization in {"bar", "column"}:
                result.setdefault("labels_position", values["labels"].get("position", "outside"))
        grid = values["axes_gridlines"]
        result["grid"] = {"x": grid["x_grid"], "y": grid["y_grid"], **result.get("grid", {})}
        if visualization == "line":
            result["grid"].setdefault("y2", False)
        categorical = "y" if visualization in {"bar", "bar_100p"} else "x"
        if result["grid"].get(categorical):
            raise ValueError(f"wizard/grid/{categorical}: categorical grid must be disabled")
        if any(result["grid"].values()):
            reason = result.get("grid_reason") or grid.get("reason")
            if visualization not in {"line", "column"} or not isinstance(reason, str) or not reason.strip():
                raise ValueError("wizard/grid: numeric grid requires line/column and a concrete grid_reason")
    return result, profile


def compile_wizard_create(
    *,
    visualization: str,
    name: str,
    workbook_id: str,
    dataset_id: str,
    fields: list[dict[str, Any]],
    roles: dict[str, list[str]],
    title: str = "",
    local_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = validate_dataset_fields(fields)
    issues = list(report["issues"])
    selected = [guid for guids in roles.values() for guid in guids]
    issues.extend(validate_visualization_fields(fields + (local_fields or []), selected)["issues"])
    if visualization not in WIZARD_VARIANTS:
        issues.append(
            {
                "code": "wizard_visualization_unsupported",
                "path": "visualization",
                "message": f"unsupported SDK visualization: {visualization}",
            }
        )
    field_rows = wire_fields(fields)
    known = {str(item["guid"]): item for item in field_rows}
    for role, guids in roles.items():
        for guid in guids:
            if guid.lower() in TECHNICAL_MEASURES:
                issues.append(
                    {
                        "code": "technical_measure_role_requires_sdk_operation",
                        "path": f"roles.{role}",
                        "message": "technical measures must use a documented SDK chart operation",
                    }
                )
            elif guid not in known:
                issues.append(
                    {
                        "code": "wizard_field_guid_unknown",
                        "path": f"roles.{role}",
                        "message": f"field GUID is absent from Dataset readback: {guid}",
                    }
                )
    if issues:
        return {"ok": False, "issues": issues, "sdk_version": SDK_VERSION, "dataset_fields": field_rows}

    dataset = Dataset(id=dataset_id, result_schema=tuple(field_rows))
    client = DataLensClientYC(auth=None)
    try:
        builder = wizard_builder(client, dataset, {
            "dataset_id": dataset_id, "visualization": visualization, "roles": roles, "title": title,
        }, name=name, location=Workbook.workbook(workbook_id))
        for item in local_fields or []:
            builder.add_local_field(WizardLocalField(
                title=str(item["title"]),
                formula=str(item["formula"]),
                guid=str(item["guid"]),
                cast=str(item.get("cast") or "float"),
                type="MEASURE" if item.get("measure") else "DIMENSION",
                autoaggregated=False,
                aggregation=str(item.get("aggregation") or "none"),
            ))
        payload = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()
    except (ValueError, TypeError) as exc:
        return {"ok": False, "issues": [{"code": "wizard_compilation_invalid", "path": "wizard", "message": str(exc)}],
                "sdk_version": SDK_VERSION, "dataset_fields": field_rows}
    finally:
        client.close()
    return {
        "ok": True,
        "issues": [],
        "sdk_version": SDK_VERSION,
        "sdk_factory": f"wizard_chart.{visualization}",
        "dataset_fields": field_rows,
        "payload": payload,
        "partial_fields_shape": inspect_wizard_shape(payload["data"])["partial_fields_shape"],
    }


def inspect_wizard_shape(data: Mapping[str, Any]) -> dict[str, Any]:
    partial = data.get("datasetsPartialFields")
    if not isinstance(partial, list):
        shape = "missing"
    elif not partial:
        shape = "empty"
    elif all(isinstance(item, list) for item in partial):
        shape = "nested"
    elif all(isinstance(item, Mapping) for item in partial):
        shape = "flat"
    else:
        shape = "mixed"
    current = isinstance(data.get("sources"), Mapping) and isinstance(data["sources"].get("datasetsIds"), list)
    return {
        "sdk_version": SDK_VERSION,
        "document_schema": "V1" if current else "legacy_or_unknown",
        "partial_fields_shape": shape,
        "update_safe": current and shape == "missing",
        "policy": "preserve_v1_guid_handles_and_slot_order; re-export_legacy_via_api_v3",
    }


def _setter(builder: Any, name: str) -> Any:
    method = getattr(builder, name, None)
    if not callable(method):
        raise ValueError(f"SDK 3.0.0 does not support {name} for this Wizard visualization")  # noqa: TRY004
    return method
