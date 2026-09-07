from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datalens_sdk import DataLensClientYC, Dataset, Workbook
from datalens_sdk.converter.wizard import WizardChartConverter

from datalens_dev_mcp.api.sdk_adapter import SDK_VERSION, WIZARD_VARIANTS
from datalens_dev_mcp.dataset.contracts import TECHNICAL_MEASURES, validate_dataset_fields, wire_fields


def wizard_builder(client: Any, dataset: Dataset, specification: Mapping[str, Any], *, name: str, location: Any) -> Any:
    """Configure the official builder using GUIDs resolved from Dataset readback.

    Returning a builder is local work; only its caller may invoke build().
    Role names are deliberately not arbitrary SDK method names.
    """
    visualization = str(specification.get("visualization") or "")
    if visualization not in WIZARD_VARIANTS:
        raise ValueError(f"unsupported Wizard visualization: {visualization}")
    allowed = {"dataset_id", "visualization", "roles", "title", "title_mode", "table", "sort", "column_titles",
               "grid", "legend", "labels_position"}
    if set(specification) - allowed:
        raise ValueError(f"unsupported Wizard settings: {sorted(set(specification) - allowed)}")
    roles = specification.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("wizard.roles must contain explicit field GUID assignments")
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
        builder.chart_title(text=str(specification.get("title") or ""), mode=mode)
    for order in specification.get("sort", []):
        if order.get("direction") not in {"asc", "desc"}:
            raise ValueError("sort direction must be asc or desc")
        builder.add_sort(dataset.fields.by_guid(order["field_guid"]), direction=order["direction"])
    table = specification.get("table")
    if table is not None:
        if visualization != "flat_table" or not isinstance(table, dict):
            raise ValueError("table settings currently require flat_table")
        if set(table) - {"pagination", "page_size", "totals", "size", "freeze_columns"}:
            raise ValueError("unsupported native table setting")
        page_size = table.get("page_size", 100)
        if type(page_size) is not int or page_size < 1:
            raise ValueError("page_size must be a positive integer")
        builder.pagination(enabled=bool(table.get("pagination", True)), limit=page_size)
        builder.totals(enabled=bool(table.get("totals", False)))
        size = table.get("size", "m")
        if size not in {"s", "m", "l"}:
            raise ValueError("table size must be s, m or l")
        builder.table_size(size=size)
        if "freeze_columns" in table:
            count = table["freeze_columns"]
            if type(count) is not int or count < 0:
                raise ValueError("freeze_columns must be a nonnegative integer")
            builder.freeze_columns(count=count)
    for guid, title in specification.get("column_titles", {}).items():
        if visualization != "flat_table":
            raise ValueError("column_titles require flat_table")
        builder.column_title(dataset.fields.by_guid(guid), title=str(title))
    for axis, enabled in specification.get("grid", {}).items():
        if axis not in {"x", "y"} or type(enabled) is not bool or not callable(getattr(builder, "grid", None)):
            raise ValueError("grid requires a supported x/y axis and boolean value")
        builder.grid(axis, enabled=enabled)
    if "legend" in specification:
        if specification["legend"] not in {"show", "hide"}:
            raise ValueError("legend must be show or hide")
        builder.legend(mode=specification["legend"])
    if "labels_position" in specification:
        if specification["labels_position"] not in {"inside", "outside", "auto"}:
            raise ValueError("labels_position must be inside, outside or auto")
        builder.labels_position(mode=specification["labels_position"])
    return builder


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
    if visualization not in WIZARD_VARIANTS:
        issues.append({"code": "wizard_visualization_unsupported", "path": "visualization", "message": f"unsupported SDK visualization: {visualization}"})
    field_rows = wire_fields(fields)
    known = {str(item["guid"]): item for item in field_rows}
    for role, guids in roles.items():
        for guid in guids:
            if guid.lower() in TECHNICAL_MEASURES:
                issues.append({"code": "technical_measure_role_requires_sdk_operation", "path": f"roles.{role}", "message": "technical measures must use a documented SDK chart operation"})
            elif guid not in known:
                issues.append({"code": "wizard_field_guid_unknown", "path": f"roles.{role}", "message": f"field GUID is absent from Dataset readback: {guid}"})
    if issues:
        return {"ok": False, "issues": issues, "sdk_version": SDK_VERSION, "dataset_fields": field_rows}

    dataset = Dataset(id=dataset_id, result_schema=tuple(field_rows))
    client = DataLensClientYC(auth=None)
    try:
        factory = getattr(client.create.wizard_chart, visualization)
        builder = factory(name=name, location=Workbook.workbook(workbook_id)).dataset(dataset)
        for role, guids in roles.items():
            method = getattr(builder, role, None)
            if method is None or not callable(method):
                return {
                    "ok": False,
                    "issues": [{"code": "wizard_role_unsupported", "path": f"roles.{role}", "message": f"{visualization} does not support role {role}"}],
                    "sdk_version": SDK_VERSION,
                    "dataset_fields": field_rows,
                }
            method([dataset.fields.by_guid(guid) for guid in guids])
        for item in local_fields or []:
            builder.add_local_field(
                title=str(item["title"]),
                formula=str(item["formula"]),
                guid=str(item["guid"]),
                cast=str(item.get("cast") or "float"),
                measure=bool(item.get("measure")),
                aggregation=str(item["aggregation"]) if item.get("aggregation") else None,
            )
        if title and hasattr(builder, "chart_title"):
            builder.chart_title(text=title, mode="show")
        payload = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()
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
    return {
        "sdk_version": SDK_VERSION,
        "partial_fields_shape": shape,
        "update_safe": shape in {"nested", "flat", "empty"},
        "policy": "preserve_existing_shape_on_update",
    }
