from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from datalens_dev_mcp.knowledge.formulas import FormulaSyntaxError, tokenize_formula
from datalens_dev_mcp.pipeline.wizard_role_types import binding_role_type_error


@dataclass(frozen=True)
class WizardContractFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WizardContractResult:
    ok: bool
    findings: list[WizardContractFinding] = field(default_factory=list)
    schema_version: str = "datalens.wizard-visual-dataset-contract.delta-v6"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


def validate_wizard_field_binding_against_dataset_readback(
    chart_payload: dict[str, Any],
    dataset_readbacks: list[dict[str, Any]] | None = None,
    *,
    source: str = "",
    strict: bool = True,
    enforce_role_types: bool = False,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    readbacks = [item for item in dataset_readbacks or [] if isinstance(item, dict)]
    dataset_ids = [_dataset_id(item) for item in readbacks]
    chart_dataset_ids = _chart_dataset_ids(chart_payload)
    dataset_field_ids = set()
    dataset_field_types: dict[str, str] = {}
    for readback in readbacks:
        if chart_dataset_ids and _dataset_id(readback) not in chart_dataset_ids:
            continue
        dataset_field_ids.update(_dataset_field_ids(readback))
        dataset_field_types.update(_dataset_field_type_map(readback))
    if strict and not readbacks:
        findings.append(_finding_dict("error", "dataset_readback_required", "$.dataset_readbacks", "dataset readback is required"))
    bound_dataset_ids = {item for item in dataset_ids if item}
    if strict:
        for index, dataset_id in enumerate(dataset_ids):
            if not dataset_id:
                findings.append(
                    _finding_dict(
                        "error",
                        "dataset_readback_identity_required",
                        f"$.dataset_readbacks[{index}]",
                        "dataset readback must expose datasetId/id",
                    )
                )
        missing_dataset_ids = sorted(chart_dataset_ids - bound_dataset_ids)
        if missing_dataset_ids:
            findings.append(
                _finding_dict(
                    "error",
                    "wizard_dataset_readback_mismatch",
                    "$.dataset_readbacks",
                    "dataset readback does not cover chart dataset ids: " + ", ".join(missing_dataset_ids),
                )
            )

    partial_fields = _partial_fields(chart_payload)
    partial_ids = {field_id for field_id, _path, _field in partial_fields}
    chart_local_ids = {field_id for field_id, _path, field in partial_fields if _is_chart_local_formula(field)}
    for field_id, path, field in partial_fields:
        if field_id in chart_local_ids:
            continue
        if readbacks and field_id not in dataset_field_ids:
            findings.append(
                _finding_dict(
                    "error",
                    "wizard_partial_field_missing_from_dataset_readback",
                    path,
                    f"datasetsPartialFields field `{field_id}` is absent from dataset readback",
                )
            )
        if _is_chart_local_formula(field):
            findings.append(
                _finding_dict(
                    "error",
                    "chart_local_formula_in_datasets_partial_fields",
                    path,
                    f"chart-local formula field `{field_id}` must stay in chart-local structures",
                )
            )

    resolvable = dataset_field_ids | partial_ids | chart_local_ids
    for ref, path in _field_refs(chart_payload):
        if ref and (resolvable or readbacks) and ref not in resolvable:
            findings.append(
                _finding_dict(
                    "error",
                    "wizard_field_ref_unresolved_against_dataset_readback",
                    path,
                    f"field reference `{ref}` is unresolved",
                )
            )
    for ref, path in _formula_refs(chart_payload):
        if ref and (resolvable or readbacks) and ref not in resolvable:
            findings.append(
                _finding_dict(
                    "error",
                    "wizard_formula_ref_unresolved_against_dataset_readback",
                    path,
                    f"formula reference `{ref}` is unresolved",
                )
            )
    visualization_id = _wizard_visualization_token(chart_payload) or str(
        chart_payload.get("chart_type")
        or chart_payload.get("type")
        or chart_payload.get("family")
        or ""
    )
    for role, ref, path in _role_field_refs(chart_payload):
        field_type = dataset_field_types.get(ref, "")
        type_error = binding_role_type_error(
            visualization_id=visualization_id,
            role=role,
            field_type=field_type,
        )
        if type_error:
            findings.append(
                _finding_dict(
                    "error" if enforce_role_types else "warning",
                    "wizard_field_role_type_mismatch",
                    path,
                    f"field `{ref}` in role `{role}` {type_error}",
                )
            )
    if _uses_select_star(chart_payload):
        findings.append(
            _finding_dict(
                "error",
                "wizard_sql_select_star_forbidden",
                "$.sql",
                "Wizard source SQL must expose explicit aliases instead of SELECT *",
            )
        )
    if _raw_schema_empty_for_subselect(chart_payload):
        findings.append(
            _finding_dict(
                "error",
                "wizard_ch_subselect_raw_schema_required",
                "$.raw_schema",
                "CH_SUBSELECT Wizard datasets require raw_schema aliases from SQL output",
            )
        )
    if _stale_template_ref(chart_payload):
        findings.append(_finding_dict("error", "wizard_stale_template_ref", "$", "stale *_mend/template GUIDs must be removed"))
    if _is_grouped_side_by_side_request(chart_payload) and _uses_multiple_measure_grouping(chart_payload):
        findings.append(
            _finding_dict(
                "error",
                "grouped_bar_requires_tidy_category_model",
                "$.measures",
                "side-by-side grouped bars require period/category dimensions, one numeric measure, and category color",
            )
        )
    if strict and _missing_required_labels(chart_payload):
        findings.append(
            _finding_dict(
                "error",
                "wizard_labels_required_by_default",
                "$.labels",
                "bar/column Wizard charts require labels; line charts need labels or readable axes with value tooltips",
            )
        )
    if _gridlines_enabled(chart_payload):
        findings.append(
            _finding_dict("warning", "wizard_gridlines_default_off", "$.gridlines", "gridlines should be off unless justified")
        )
    if _measure_axis_title_enabled(chart_payload):
        findings.append(
            _finding_dict(
                "warning",
                "wizard_measure_axis_title_default_off",
                "$.axes.measure_axis_title",
                "measure-axis title should be off unless justified",
            )
        )
    findings.extend(_flat_table_hint_findings(chart_payload, as_dict=True))
    return {
        "schema_version": "datalens.delta_v7.wizard_field_binding_report.v1",
        "ok": not any(item["severity"] == "error" for item in findings),
        "chart_id": str(chart_payload.get("entryId") or chart_payload.get("chartId") or chart_payload.get("id") or ""),
        "dataset_ids": [item for item in dataset_ids if item],
        "source": source,
        "findings": findings,
    }


def compact_wizard_dataset_readbacks(
    chart_payload: dict[str, Any],
    dataset_readbacks: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Keep only identity plus referenced field id/type evidence for a Wizard plan."""

    referenced_ids = {
        ref
        for ref, _path in _field_refs(chart_payload)
        if ref
    }
    referenced_ids.update(
        field_id
        for field_id, _path, _field in _partial_fields(chart_payload)
        if field_id
    )
    referenced_ids.update(
        ref
        for _role, ref, _path in _role_field_refs(chart_payload)
        if ref
    )
    chart_dataset_ids = _chart_dataset_ids(chart_payload)
    compact: list[dict[str, Any]] = []
    for readback in dataset_readbacks or []:
        if not isinstance(readback, dict):
            continue
        readback_dataset_id = _dataset_id(readback)
        if chart_dataset_ids and readback_dataset_id not in chart_dataset_ids:
            continue
        available_ids = _dataset_field_ids(readback)
        field_types = _dataset_field_type_map(readback)
        fields: list[dict[str, str]] = []
        for field_id in sorted(referenced_ids & available_ids):
            field: dict[str, str] = {"guid": field_id}
            if field_types.get(field_id):
                field["data_type"] = field_types[field_id]
            fields.append(field)
        compact.append(
            {
                "datasetId": readback_dataset_id,
                "result_schema": fields,
            }
        )
    return compact


def validate_wizard_visual_dataset_contract(payload: dict[str, Any]) -> WizardContractResult:
    findings: list[WizardContractFinding] = []
    partial_fields = _partial_fields(payload)
    partial_ids = {field_id for field_id, _path, _field in partial_fields}
    refs = _field_refs(payload)
    for ref, path in refs:
        if ref and partial_ids and ref not in partial_ids:
            findings.append(
                _finding(
                    "wizard_field_ref_missing_from_datasets_partial_fields",
                    path,
                    f"field reference `{ref}` is not present in datasetsPartialFields",
                )
            )
    for field_id, path, field in partial_fields:
        if _is_chart_local_formula(field):
            findings.append(
                _finding(
                    "chart_local_formula_in_datasets_partial_fields",
                    path,
                    f"chart-local formula field `{field_id}` must not be treated as a dataset field",
                )
            )
    if _uses_select_star(payload):
        findings.append(
            _finding(
                "wizard_sql_select_star_forbidden",
                "$.sql",
                "Wizard source SQL must expose explicit aliases instead of SELECT *",
            )
        )
    if _stale_template_ref(payload):
        findings.append(
            _finding(
                "wizard_stale_template_ref",
                "$",
                "stale template references such as *_mend must be removed before save/publish",
            )
        )
    if _is_grouped_side_by_side_request(payload) and _uses_multiple_measure_grouping(payload):
        findings.append(
            _finding(
                "grouped_bar_requires_tidy_category_model",
                "$.measures",
                "side-by-side grouped bars require x dimension, category dimension, one numeric measure, and category color/segment",
            )
        )
    if _missing_required_labels(payload):
        findings.append(
            _finding(
                "wizard_labels_required_by_default",
                "$.labels",
                "bar/column Wizard charts require labels; line charts need labels or readable axes with value tooltips",
            )
        )
    if _gridlines_enabled(payload):
        findings.append(
            _finding(
                "wizard_gridlines_default_off",
                "$.gridlines",
                "gridlines should be off unless justified",
                severity="warning",
            )
        )
    if _measure_axis_title_enabled(payload):
        findings.append(
            _finding(
                "wizard_measure_axis_title_default_off",
                "$.axes.measure_axis_title",
                "measure-axis title should be off unless justified",
                severity="warning",
            )
        )
    findings.extend(_flat_table_hint_findings(payload, as_dict=False))
    return WizardContractResult(ok=not any(item.severity == "error" for item in findings), findings=findings)


def _partial_fields(value: Any, path: str = "$") -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "datasetsPartialFields":
                rows.extend(_fields_from_partial_container(item, child_path))
            else:
                rows.extend(_partial_fields(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_partial_fields(item, f"{path}[{index}]"))
    return rows


def _fields_from_partial_container(value: Any, path: str) -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_fields_from_partial_container(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict):
                field_id = _field_id(item)
                if field_id:
                    rows.append((field_id, f"{path}[{index}]", item))
            else:
                text = str(item).strip()
                if text:
                    rows.append((text, f"{path}[{index}]", {}))
    return rows


def _field_refs(value: Any, path: str = "$", *, in_ref_slot: bool = False) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            child_in_ref = in_ref_slot or lowered in {
                "placeholder",
                "placeholders",
                "labels",
                "label",
                "colors",
                "color",
                "tooltip",
                "tooltips",
                "sort",
                "sorting",
                "filters",
                "filter",
                "dimensions",
                "dimension",
                "measures",
                "measure",
                "segments",
                "segment",
                "shapes",
                "shape",
                "geopoints",
                "geopoint",
            }
            child_path = f"{path}.{key}"
            if (
                child_in_ref
                and lowered in {"guid", "fieldguid", "field_guid", "fieldid", "field_id", "ref", "field"}
                and not isinstance(item, (dict, list))
            ):
                text = str(item).strip()
                if text:
                    refs.append((text, child_path))
            refs.extend(_field_refs(item, child_path, in_ref_slot=child_in_ref))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            refs.extend(_field_refs(item, f"{path}[{index}]", in_ref_slot=in_ref_slot))
    return refs


def _field_id(field: dict[str, Any]) -> str:
    return str(
        field.get("guid")
        or field.get("fieldGuid")
        or field.get("field_guid")
        or field.get("id")
        or field.get("fieldId")
        or ""
    ).strip()


def _is_chart_local_formula(field: dict[str, Any]) -> bool:
    scope = str(field.get("formula_scope") or field.get("scope") or "").strip().lower()
    return bool(field.get("local_formula") or field.get("chart_local_formula") or scope in {"chart", "local", "chart_local"})


def _uses_select_star(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_uses_select_star(item) for item in value.values())
    if isinstance(value, list):
        return any(_uses_select_star(item) for item in value)
    if isinstance(value, str):
        lowered = " ".join(value.lower().split())
        return "select *" in lowered
    return False


def _stale_template_ref(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_stale_template_ref(item) for item in value.values())
    if isinstance(value, list):
        return any(_stale_template_ref(item) for item in value)
    return isinstance(value, str) and "_mend" in value


def _is_grouped_side_by_side_request(payload: dict[str, Any]) -> bool:
    text = " ".join(
        str(payload.get(key) or "")
        for key in ("chart_intent", "intent", "requirement", "grouping_requirement", "description")
    ).lower()
    chart_type = str(payload.get("chart_type") or payload.get("type") or "").lower()
    return (
        "side-by-side" in text
        or "side by side" in text
        or "grouped" in text
        or ("group" in chart_type and ("bar" in chart_type or "column" in chart_type))
    )


def _uses_multiple_measure_grouping(payload: dict[str, Any]) -> bool:
    measures = payload.get("measures")
    if not isinstance(measures, list) or len(measures) <= 1:
        return False
    category = payload.get("category_dimension") or payload.get("color_dimension") or payload.get("segment_dimension")
    return not bool(category and len(measures) == 1)


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> WizardContractFinding:
    return WizardContractFinding(rule=rule, severity=severity, path=path, message=message)


def _finding_dict(severity: str, rule: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "rule": rule, "path": path, "message": message}


def _dataset_id(value: dict[str, Any]) -> str:
    for key in ("datasetId", "dataset_id", "id"):
        item = value.get(key)
        if item not in (None, ""):
            return str(item)
    dataset = value.get("dataset") if isinstance(value.get("dataset"), dict) else {}
    for key in ("datasetId", "dataset_id", "id"):
        item = dataset.get(key)
        if item not in (None, ""):
            return str(item)
    return ""


def _chart_dataset_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("_", "").lower()
            if normalized == "datasetsids" and isinstance(item, list):
                ids.update(str(dataset_id).strip() for dataset_id in item if str(dataset_id).strip())
            elif normalized == "datasetid" and item not in (None, "") and not isinstance(item, (dict, list)):
                ids.add(str(item).strip())
            elif isinstance(item, (dict, list)):
                ids.update(_chart_dataset_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.update(_chart_dataset_ids(item))
    return ids


def _dataset_field_ids(value: Any, *, in_field_container: bool = False) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        is_field = in_field_container and _looks_like_dataset_field(value)
        if is_field:
            for key in ("guid", "fieldGuid", "field_guid", "fieldId", "field_id", "id", "name", "title"):
                item = value.get(key)
                if item not in (None, "") and not isinstance(item, (dict, list)):
                    ids.add(str(item).strip())
        for key, item in value.items():
            lowered = str(key).lower()
            child_is_field_container = in_field_container or lowered in {
                "fields",
                "datasetfields",
                "dataset_fields",
                "fielddefinitions",
                "field_definitions",
                "resultschema",
                "result_schema",
            }
            ids.update(_dataset_field_ids(item, in_field_container=child_is_field_container))
    elif isinstance(value, list):
        for item in value:
            ids.update(_dataset_field_ids(item, in_field_container=in_field_container))
    return ids


def _dataset_field_type_map(value: Any, *, in_field_container: bool = False) -> dict[str, str]:
    field_types: dict[str, str] = {}
    if isinstance(value, dict):
        is_field = in_field_container and _looks_like_dataset_field(value)
        if is_field:
            field_type = str(
                value.get("data_type")
                or value.get("dataType")
                or value.get("field_type")
                or value.get("fieldType")
                or value.get("type")
                or ""
            ).strip()
            if field_type:
                for key in ("guid", "fieldGuid", "field_guid", "fieldId", "field_id", "id", "name", "title"):
                    item = value.get(key)
                    if item not in (None, "") and not isinstance(item, (dict, list)):
                        field_types[str(item).strip()] = field_type
        for key, item in value.items():
            lowered = str(key).lower()
            child_is_field_container = in_field_container or lowered in {
                "fields",
                "datasetfields",
                "dataset_fields",
                "fielddefinitions",
                "field_definitions",
                "resultschema",
                "result_schema",
            }
            field_types.update(_dataset_field_type_map(item, in_field_container=child_is_field_container))
    elif isinstance(value, list):
        for item in value:
            field_types.update(_dataset_field_type_map(item, in_field_container=in_field_container))
    return field_types


def _role_field_refs(value: Any, path: str = "$") -> list[tuple[str, str, str]]:
    refs: list[tuple[str, str, str]] = []
    if isinstance(value, dict):
        field_bindings = value.get("field_bindings")
        if isinstance(field_bindings, dict):
            for role, raw_items in field_bindings.items():
                items = raw_items if isinstance(raw_items, list) else [raw_items]
                for index, item in enumerate(items):
                    ref = _field_id(item) if isinstance(item, dict) else str(item or "").strip()
                    if ref:
                        refs.append((str(role), ref, f"{path}.field_bindings.{role}[{index}]"))
        placeholders = value.get("placeholders")
        if isinstance(placeholders, list):
            for index, placeholder in enumerate(placeholders):
                if not isinstance(placeholder, dict):
                    continue
                role = str(placeholder.get("id") or placeholder.get("name") or "").strip()
                items = placeholder.get("items") if isinstance(placeholder.get("items"), list) else []
                for item_index, item in enumerate(items):
                    ref = _field_id(item) if isinstance(item, dict) else str(item or "").strip()
                    if role and ref:
                        refs.append(
                            (
                                role,
                                ref,
                                f"{path}.placeholders[{index}].items[{item_index}]",
                            )
                        )
        for key, item in value.items():
            if key not in {"field_bindings", "placeholders"}:
                refs.extend(_role_field_refs(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            refs.extend(_role_field_refs(item, f"{path}[{index}]"))
    return refs


def _wizard_visualization_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("visualization_id", "visualizationId"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        visualization = value.get("visualization")
        if isinstance(visualization, dict):
            token = str(visualization.get("id") or visualization.get("type") or "").strip()
            if token:
                return token
        for child in value.values():
            token = _wizard_visualization_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _wizard_visualization_token(child)
            if token:
                return token
    return ""


def _looks_like_dataset_field(value: dict[str, Any]) -> bool:
    if any(value.get(key) not in (None, "") for key in ("guid", "fieldGuid", "field_guid", "fieldId", "field_id")):
        return True
    return bool(
        value.get("name")
        and any(key in value for key in ("type", "data_type", "aggregation", "formula", "cast", "role"))
    )


def _formula_refs(value: Any, path: str = "$") -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            lowered = str(key).lower()
            if lowered in {"formula", "guid_formula", "guidformula"} and isinstance(item, str):
                refs.extend((ref, child_path) for ref in _refs_from_formula(item))
            else:
                refs.extend(_formula_refs(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            refs.extend(_formula_refs(item, f"{path}[{index}]"))
    return refs


def _refs_from_formula(value: str) -> list[str]:
    try:
        return [token.value for token in tokenize_formula(value) if token.kind == "field"]
    except FormulaSyntaxError:
        # Syntax validation belongs to the formula validator. Keep a bounded
        # fallback here so a malformed formula cannot hide otherwise obvious
        # bracketed field references from the Wizard binding report.
        return [item.strip() for item in re.findall(r"\[([^\[\]]+)\]", value) if item.strip()]


def _flat_table_hint_findings(payload: dict[str, Any], *, as_dict: bool) -> list[Any]:
    if not _flat_table_family(payload):
        return []
    findings: list[Any] = []

    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            description = str(value.get("description") or "").strip()
            if _looks_like_wizard_field_item(value):
                settings = value.get("hintSettings") if isinstance(value.get("hintSettings"), dict) else {}
                visible_required = _visible_flat_table_hint_required(payload, value)
                missing = []
                if not description:
                    missing.append("description")
                if settings.get("enabled") is not True:
                    missing.append("hintSettings.enabled=true")
                if not str(settings.get("text") or "").strip():
                    missing.append("hintSettings.text")
                settings_missing = bool(
                    settings.get("enabled") is not True or not str(settings.get("text") or "").strip()
                )
                if (visible_required and missing) or (description and settings_missing):
                    message = (
                        "Visible flat-table field hints require nonempty description, "
                        "hintSettings.enabled=true, and nonempty hintSettings.text; missing: "
                        + ", ".join(missing)
                    )
                    severity = "error" if visible_required else "warning"
                    if as_dict:
                        findings.append(_finding_dict(severity, "wizard_flat_table_hint_not_enabled", path, message))
                    else:
                        findings.append(
                            _finding("wizard_flat_table_hint_not_enabled", path, message, severity=severity)
                        )
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload)
    return findings


def _visible_flat_table_hint_required(payload: dict[str, Any], field: dict[str, Any]) -> bool:
    def values(value: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(value, dict):
            found.append(value)
            for item in value.values():
                found.extend(values(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(values(item))
        return found

    for value in [field, *values(payload)]:
        if any(
            value.get(key) is True
            for key in (
                "require_visible_hint",
                "visible_hint_required",
                "visible_hints_required",
                "require_visible_hints",
            )
        ):
            return True
        intent = str(
            value.get("hint_intent")
            or value.get("visible_hint_intent")
            or value.get("description_intent")
            or ""
        ).strip().lower()
        if intent in {"visible", "header_hint", "visible_header_hint", "required"}:
            return True
    return False


def _flat_table_family(payload: dict[str, Any]) -> bool:
    values: list[str] = []

    def walk(value: Any, *, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, item in value.items():
                if str(child_key).lower() in {"id", "type", "chart_type", "visualizationid", "visualization_id"}:
                    values.append(str(item))
                walk(item, key=str(child_key))
        elif isinstance(value, list):
            for item in value:
                walk(item, key=key)

    walk(payload)
    normalized = " ".join(values).lower().replace("_", "")
    return "flattable" in normalized


def _looks_like_wizard_field_item(value: dict[str, Any]) -> bool:
    return any(value.get(key) not in (None, "") for key in ("guid", "fieldGuid", "field_guid", "fieldId", "field_id"))


def _raw_schema_empty_for_subselect(payload: dict[str, Any]) -> bool:
    dataset_type = str(payload.get("dataset_type") or payload.get("source_type") or payload.get("connection_type") or "").upper()
    if dataset_type != "CH_SUBSELECT":
        return False
    raw = payload.get("raw_schema")
    return raw in (None, "", [], {})


def _line_bar_column_family(payload: dict[str, Any]) -> bool:
    text = " ".join(str(payload.get(key) or "") for key in ("chart_type", "type", "family", "visualization")).lower()
    return any(term in text for term in ("line", "bar", "column"))


def _line_family(payload: dict[str, Any]) -> bool:
    text = " ".join(str(payload.get(key) or "") for key in ("chart_type", "type", "family", "visualization")).lower()
    return any(term in text for term in ("line", "timeseries", "time_series"))


def _missing_required_labels(payload: dict[str, Any]) -> bool:
    if not _line_bar_column_family(payload) or _has_labels(payload):
        return False
    if _line_family(payload):
        return not _line_label_alternative(payload)
    return True


def _line_label_alternative(payload: dict[str, Any]) -> bool:
    alternatives = payload.get("alternatives") if isinstance(payload.get("alternatives"), dict) else {}
    runtime = payload.get("runtime_constraints") if isinstance(payload.get("runtime_constraints"), dict) else {}
    explicit = bool(
        payload.get("explicit_label_axis_alternative")
        or alternatives.get("labels_or_axes")
        or alternatives.get("label_axis_alternative")
        or runtime.get("explicit_label_axis_alternative")
    )
    if explicit:
        return True

    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    axes = payload.get("axes") if isinstance(payload.get("axes"), dict) else {}
    settings_axes = settings.get("axes") if isinstance(settings.get("axes"), dict) else {}
    readable_axes = any(
        bool(container.get(key))
        for container in (axes, settings_axes)
        for key in ("show", "visible", "x_axis_label", "y_axis_label", "date_axis_ascending", "unit_label_required")
    )

    tooltip = payload.get("tooltip")
    tooltips = payload.get("tooltips")
    settings_tooltip = settings.get("tooltip")
    value_tooltips = _tooltip_has_values(tooltip) or _tooltip_has_values(tooltips) or _tooltip_has_values(settings_tooltip)
    return readable_axes and value_tooltips


def _tooltip_has_values(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    if not isinstance(value, dict):
        return bool(value)
    return bool(
        value.get("enabled")
        or value.get("show")
        or value.get("include_values")
        or value.get("include_metric_definition")
        or value.get("fields")
        or value.get("items")
    )


def _has_labels(payload: dict[str, Any]) -> bool:
    if payload.get("labels") or payload.get("label"):
        return True
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    labels = settings.get("labels") if isinstance(settings.get("labels"), dict) else {}
    return bool(labels.get("enabled") or labels.get("show"))


def _gridlines_enabled(payload: dict[str, Any]) -> bool:
    gridlines = payload.get("gridlines") if isinstance(payload.get("gridlines"), dict) else {}
    return bool(payload.get("show_gridlines") or gridlines.get("show") or gridlines.get("enabled"))


def _measure_axis_title_enabled(payload: dict[str, Any]) -> bool:
    axes = payload.get("axes") if isinstance(payload.get("axes"), dict) else {}
    return bool(payload.get("measure_axis_title") or axes.get("measure_axis_title"))
