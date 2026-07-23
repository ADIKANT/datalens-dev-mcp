from __future__ import annotations

import ast
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract
from datalens_dev_mcp.pipeline.layout_contract import plan_selector_row_widths


DATE_RANGE_MAINTENANCE_KIND = "date_range_selector_merge"
DATE_RANGE_FAST_PATH_SCHEMA_VERSION = "datalens.selector_date_range_maintenance.v1"


def compile_date_range_selector_merge(
    *,
    project_root: str | Path,
    maintenance_contract: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    selector_path = _resolve_artifact_path(root, maintenance_contract.get("selector_readback_path"))
    dashboard_path = _resolve_artifact_path(root, maintenance_contract.get("dashboard_readback_path"))
    blocked: list[str] = []
    if not selector_path:
        blocked.append("maintenance_contract.selector_readback_path_missing_or_outside_project")
    if not dashboard_path:
        blocked.append("maintenance_contract.dashboard_readback_path_missing_or_outside_project")
    if blocked:
        return _blocked(blocked)

    selector_readback = _read_json(selector_path)
    dashboard_readback = _read_json(dashboard_path)
    if selector_readback is None:
        blocked.append("maintenance_contract.selector_readback_invalid")
    if dashboard_readback is None:
        blocked.append("maintenance_contract.dashboard_readback_invalid")
    if blocked:
        return _blocked(blocked)

    selector_object_id = str(maintenance_contract.get("selector_object_id") or "").strip()
    dashboard_id = str(maintenance_contract.get("dashboard_id") or "").strip()
    if not selector_object_id:
        blocked.append("maintenance_contract.selector_object_id_missing")
    if not dashboard_id:
        blocked.append("maintenance_contract.dashboard_id_missing")

    raw_selector_contract = maintenance_contract.get("selector_contract")
    if not isinstance(raw_selector_contract, dict):
        blocked.append("maintenance_contract.selector_contract_missing")
        normalized_contract: dict[str, Any] = {}
    else:
        normalized_contract = normalize_selector_contract(
            family="date_range_selector",
            title=str(raw_selector_contract.get("label") or ""),
            selector_contract=raw_selector_contract,
        )
        if not normalized_contract.get("ok"):
            blocked.extend(
                "selector_contract." + str(issue.get("code") or "invalid")
                for issue in normalized_contract.get("issues") or []
                if isinstance(issue, dict)
            )
        if normalized_contract.get("param"):
            blocked.append("selector_contract.paired_params_required")
        if not normalized_contract.get("param_from") or not normalized_contract.get("param_to"):
            blocked.append("selector_contract.paired_params_required")
    if blocked:
        return _blocked(blocked, selector_contract=normalized_contract)

    selector_entry_result = _extract_entry(selector_readback, expected_id=selector_object_id)
    dashboard_entry_result = _extract_entry(dashboard_readback, expected_id=dashboard_id)
    if not selector_entry_result["ok"]:
        blocked.append("selector_readback." + selector_entry_result["reason"])
    if not dashboard_entry_result["ok"]:
        blocked.append("dashboard_readback." + dashboard_entry_result["reason"])
    if blocked:
        return _blocked(blocked, selector_contract=normalized_contract)

    selector_entry = selector_entry_result["entry"]
    dashboard_entry = dashboard_entry_result["entry"]
    selector_revision = _revision(selector_entry)
    dashboard_revision = _revision(dashboard_entry)
    if not selector_revision:
        blocked.append("selector_readback.missing_revision")
    if not dashboard_revision:
        blocked.append("dashboard_readback.missing_revision")

    selector_data = selector_entry.get("data")
    dashboard_data = dashboard_entry.get("data")
    if not isinstance(selector_data, dict):
        blocked.append("selector_readback.missing_entry_data")
    if not isinstance(dashboard_data, dict):
        blocked.append("dashboard_readback.missing_entry_data")
    controls_source = selector_data.get("controls") if isinstance(selector_data, dict) else None
    params_source = selector_data.get("params") if isinstance(selector_data, dict) else None
    if not isinstance(controls_source, str):
        blocked.append("selector_readback.controls_source_required")
    if not isinstance(params_source, str):
        blocked.append("selector_readback.params_source_required")
    if blocked:
        return _blocked(blocked, selector_contract=normalized_contract)

    controls_patch = merge_static_date_controls(
        controls_source,
        param_from=str(normalized_contract["param_from"]),
        param_to=str(normalized_contract["param_to"]),
        label=str(normalized_contract["label"]),
    )
    if not controls_patch["ok"]:
        blocked.extend(str(reason) for reason in controls_patch["blocked_reasons"])
    params_patch = patch_params_defaults(
        params_source,
        param_from=str(normalized_contract["param_from"]),
        param_to=str(normalized_contract["param_to"]),
        default_from=str(normalized_contract.get("default_from") or ""),
        default_to=str(normalized_contract.get("default_to") or ""),
    )
    if not params_patch["ok"]:
        blocked.extend(str(reason) for reason in params_patch["blocked_reasons"])

    dashboard_patch = patch_mounted_selector_defaults(
        dashboard_data if isinstance(dashboard_data, dict) else {},
        selector_object_id=selector_object_id,
        mounted_control_id=str(maintenance_contract.get("mounted_control_id") or "").strip(),
        param_from=str(normalized_contract["param_from"]),
        param_to=str(normalized_contract["param_to"]),
        default_from=str(normalized_contract.get("default_from") or ""),
        default_to=str(normalized_contract.get("default_to") or ""),
    )
    if not dashboard_patch["ok"]:
        blocked.extend(str(reason) for reason in dashboard_patch["blocked_reasons"])
    if blocked:
        return _blocked(blocked, selector_contract=normalized_contract)

    selector_overlay = {
        "entry": {
            "data": {
                "controls": controls_patch["source"],
                "params": params_patch["source"],
            }
        }
    }
    dashboard_overlay = {"entry": {"data": dashboard_patch["data"]}}
    changed_sections = []
    if controls_patch["changed"]:
        changed_sections.append("controls")
    if params_patch["changed"]:
        changed_sections.append("params")
    actions = [
        {
            "object_type": "control_node",
            "object_id": selector_object_id,
            "base_revision": selector_revision,
            "readback_path": str(selector_path),
            "desired_overlay": selector_overlay,
            "changed_sections": changed_sections,
        },
        {
            "object_type": "dashboard",
            "object_id": dashboard_id,
            "base_revision": dashboard_revision,
            "readback_path": str(dashboard_path),
            "desired_overlay": dashboard_overlay,
            "changed_sections": ["selector_defaults"],
        },
    ]
    return {
        "ok": True,
        "schema_version": DATE_RANGE_FAST_PATH_SCHEMA_VERSION,
        "kind": DATE_RANGE_MAINTENANCE_KIND,
        "actions": actions,
        "selector_contract": normalized_contract,
        "mounted_control_id": dashboard_patch["mounted_control_id"],
        "workflow_metrics": date_range_fast_path_budget(),
        "runtime_smoke": date_range_runtime_smoke_contract(
            selector_object_id=selector_object_id,
            dashboard_id=dashboard_id,
        ),
        "changed": bool(changed_sections or dashboard_patch["changed"]),
    }


def merge_static_date_controls(
    source: str,
    *,
    param_from: str,
    param_to: str,
    label: str,
) -> dict[str, Any]:
    controls = _controls_array(source)
    if not controls["ok"]:
        return _patch_blocked("selector_controls." + controls["reason"])
    elements = controls["elements"]
    singles: dict[str, list[dict[str, Any]]] = {param_from: [], param_to: []}
    paired: list[dict[str, Any]] = []
    for item in elements:
        properties = _object_properties(source, item["start"], item["end"])
        if properties is None:
            return _patch_blocked("selector_controls.static_control_objects_required")
        if any(
            _property_parts(source, prop["start"], prop["end"]) is None
            and _skip_space_and_comments(source, prop["start"], prop["end"]) < prop["end"]
            for prop in properties
        ):
            return _patch_blocked("selector_controls.dynamic_control_object")
        control_type = _static_string_property(source, properties, "type")
        parameter = _static_string_property(source, properties, "param")
        parameter_from = _static_string_property(source, properties, "paramFrom")
        parameter_to = _static_string_property(source, properties, "paramTo")
        if parameter in singles:
            singles[parameter].append({**item, "type": control_type})
        if parameter_from == param_from and parameter_to == param_to:
            paired.append({**item, "type": control_type})

    single_matches = singles[param_from] + singles[param_to]
    if any(item.get("type") != "datepicker" for item in single_matches):
        return _patch_blocked("selector_controls.static_datepicker_required")
    if len(singles[param_from]) == 1 and len(singles[param_to]) == 1 and not paired:
        selected = sorted([singles[param_from][0], singles[param_to][0]], key=lambda item: item["start"])
        insert_item, remove_item = selected
        indent = _line_indent(source, insert_item["start"])
        replacement = _canonical_range_control(
            param_from=param_from,
            param_to=param_to,
            label=label,
            indent=indent,
        )
        remove_start, remove_end = _element_removal_span(
            source,
            controls_start=controls["array_start"],
            controls_end=controls["array_end"],
            item_start=remove_item["start"],
            item_end=remove_item["end"],
        )
        edits = [
            (insert_item["start"], insert_item["end"], replacement),
            (remove_start, remove_end, ""),
        ]
        patched = _apply_text_edits(source, edits)
        verification = _verify_range_controls(patched, param_from=param_from, param_to=param_to)
        if not verification["ok"]:
            return _patch_blocked("selector_controls.generated_range_invalid")
        return {
            "ok": True,
            "source": patched,
            "changed": patched != source,
            "matched_control_count": 2,
            "blocked_reasons": [],
        }

    if not single_matches and len(paired) == 1 and paired[0].get("type") == "range-datepicker":
        item = paired[0]
        indent = _line_indent(source, item["start"])
        replacement = _canonical_range_control(
            param_from=param_from,
            param_to=param_to,
            label=label,
            indent=indent,
        )
        patched = _apply_text_edits(source, [(item["start"], item["end"], replacement)])
        verification = _verify_range_controls(patched, param_from=param_from, param_to=param_to)
        if not verification["ok"]:
            return _patch_blocked("selector_controls.generated_range_invalid")
        return {
            "ok": True,
            "source": patched,
            "changed": patched != source,
            "matched_control_count": 1,
            "blocked_reasons": [],
        }

    return _patch_blocked("selector_controls.date_control_pair_ambiguous")


def patch_params_defaults(
    source: str,
    *,
    param_from: str,
    param_to: str,
    default_from: str,
    default_to: str,
) -> dict[str, Any]:
    object_result = _module_exports_object(source)
    if not object_result["ok"]:
        return _patch_blocked("selector_params." + object_result["reason"])
    properties = _property_ranges(source, object_result["start"] + 1, object_result["end"] - 1)
    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in properties:
        parsed = _property_parts(source, item["start"], item["end"])
        if not parsed:
            if _skip_space_and_comments(source, item["start"], item["end"]) < item["end"]:
                return _patch_blocked("selector_params.dynamic_property")
            continue
        by_key.setdefault(parsed["key"], []).append(parsed)
    if len(by_key.get(param_from, [])) > 1 or len(by_key.get(param_to, [])) > 1:
        return _patch_blocked("selector_params.duplicate_parameter_key")

    values = {
        param_from: [default_from] if default_from else [],
        param_to: [default_to] if default_to else [],
    }
    edits: list[tuple[int, int, str]] = []
    missing: list[str] = []
    for key, value in values.items():
        matches = by_key.get(key, [])
        if matches:
            item = matches[0]
            edits.append(
                (
                    item["value_start"],
                    item["value_end"],
                    json.dumps(value, ensure_ascii=False),
                )
            )
        else:
            missing.append(key)
    patched = _apply_text_edits(source, edits)
    if missing:
        refreshed = _module_exports_object(patched)
        insertion = _params_property_insertion(
            patched,
            object_start=refreshed["start"],
            object_end=refreshed["end"],
            values={key: values[key] for key in missing},
        )
        patched = patched[: refreshed["end"] - 1] + insertion + patched[refreshed["end"] - 1 :]
    verification = _params_string_arrays(patched, keys=[param_from, param_to])
    if not verification["ok"]:
        return _patch_blocked("selector_params.generated_defaults_invalid")
    return {
        "ok": True,
        "source": patched,
        "changed": patched != source,
        "values": values,
        "blocked_reasons": [],
    }


def patch_mounted_selector_defaults(
    dashboard_data: dict[str, Any],
    *,
    selector_object_id: str,
    mounted_control_id: str,
    param_from: str,
    param_to: str,
    default_from: str,
    default_to: str,
) -> dict[str, Any]:
    data = deepcopy(dashboard_data)
    candidates = _mounted_default_candidates(
        data,
        selector_object_id=selector_object_id,
        mounted_control_id=mounted_control_id,
    )
    if len(candidates) != 1:
        reason = "dashboard_mount.not_found" if not candidates else "dashboard_mount.ambiguous"
        return {"ok": False, "blocked_reasons": [reason]}
    candidate = candidates[0]
    defaults = _value_at_path(data, candidate["defaults_path"])
    if not isinstance(defaults, dict):
        return {"ok": False, "blocked_reasons": ["dashboard_mount.defaults_invalid"]}
    expected = {
        param_from: [default_from] if default_from else [],
        param_to: [default_to] if default_to else [],
    }
    changed = any(defaults.get(key) != value for key, value in expected.items())
    defaults.update(expected)
    return {
        "ok": True,
        "data": data,
        "changed": changed,
        "mounted_control_id": candidate["mount_id"],
        "defaults": expected,
        "blocked_reasons": [],
    }


def date_range_fast_path_budget() -> dict[str, Any]:
    return {
        "mode": "date_range_selector_fast_path",
        "initial_exact_read_count": 2,
        "max_datalens_rpc_count": 14,
        "max_snapshot_calls": 0,
        "max_workbook_inventory_calls": 0,
        "plan_call_count": 1,
        "executor_call_count": 1,
        "target_wall_time_seconds": 300,
    }


def date_range_runtime_smoke_contract(*, selector_object_id: str, dashboard_id: str) -> dict[str, Any]:
    return {
        "required": True,
        "scope_object_ids": [selector_object_id, dashboard_id],
        "scenario_count": 1,
        "max_retries": 1,
        "checks": [
            "one_range_selector_visible_and_old_pair_absent",
            "both_boundaries_can_be_selected_and_applied",
            "selected_range_survives_control_rerender",
            "selected_range_survives_reload",
            "no_console_or_dom_errors",
            "one_machine_readable_capture_saved",
        ],
        "failure_status": "runtime_not_verified",
    }


def date_range_rerender_findings(source: str) -> list[dict[str, str]]:
    controls = _controls_array(source)
    if not controls["ok"]:
        return []
    findings: list[dict[str, str]] = []
    for item in controls["elements"]:
        properties = _object_properties(source, item["start"], item["end"])
        if properties is None:
            continue
        if _static_string_property(source, properties, "type") != "range-datepicker":
            continue
        if not _static_string_property(source, properties, "paramFrom"):
            continue
        if not _static_string_property(source, properties, "paramTo"):
            continue
        value = _static_scalar_property(source, properties, "updateControlsOnChange")
        if value == "true":
            findings.append(
                {
                    "rule": "date_range_controls_rerender_risk",
                    "severity": "warning",
                    "message": (
                        "Paired range-datepicker sets updateControlsOnChange=true; this can rerender the "
                        "control section before both boundaries are committed."
                    ),
                }
            )
    return findings


def _verify_range_controls(source: str, *, param_from: str, param_to: str) -> dict[str, Any]:
    controls = _controls_array(source)
    if not controls["ok"]:
        return {"ok": False}
    paired = 0
    singles = 0
    risky = 0
    for item in controls["elements"]:
        properties = _object_properties(source, item["start"], item["end"])
        if properties is None:
            continue
        parameter = _static_string_property(source, properties, "param")
        if parameter in {param_from, param_to}:
            singles += 1
        if (
            _static_string_property(source, properties, "type") == "range-datepicker"
            and _static_string_property(source, properties, "paramFrom") == param_from
            and _static_string_property(source, properties, "paramTo") == param_to
        ):
            paired += 1
            if _static_scalar_property(source, properties, "updateControlsOnChange") == "true":
                risky += 1
    return {"ok": paired == 1 and singles == 0 and risky == 0}


def _params_string_arrays(source: str, *, keys: list[str]) -> dict[str, Any]:
    exported = _module_exports_object(source)
    if not exported["ok"]:
        return {"ok": False}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in _property_ranges(source, exported["start"] + 1, exported["end"] - 1):
        parsed = _property_parts(source, item["start"], item["end"])
        if parsed:
            by_key.setdefault(parsed["key"], []).append(parsed)
    for key in keys:
        matches = by_key.get(key, [])
        if len(matches) != 1:
            return {"ok": False}
        raw = source[matches[0]["value_start"] : matches[0]["value_end"]]
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False}
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return {"ok": False}
    return {"ok": True}


def _controls_array(source: str) -> dict[str, Any]:
    exported = _module_exports_object(source)
    if not exported["ok"]:
        return exported
    properties = _property_ranges(source, exported["start"] + 1, exported["end"] - 1)
    matches: list[dict[str, Any]] = []
    for item in properties:
        parsed = _property_parts(source, item["start"], item["end"])
        if parsed and parsed["key"] == "controls":
            matches.append(parsed)
    if len(matches) != 1:
        return {"ok": False, "reason": "controls_property_missing_or_ambiguous"}
    value_start = _skip_space_and_comments(source, matches[0]["value_start"], matches[0]["value_end"])
    if value_start >= matches[0]["value_end"] or source[value_start] != "[":
        return {"ok": False, "reason": "static_controls_array_required"}
    array_end = _balanced_end(source, value_start)
    if array_end is None or array_end > matches[0]["value_end"]:
        return {"ok": False, "reason": "static_controls_array_required"}
    tail = _skip_space_and_comments(source, array_end, matches[0]["value_end"])
    if tail != matches[0]["value_end"]:
        return {"ok": False, "reason": "static_controls_array_required"}
    return {
        "ok": True,
        "array_start": value_start,
        "array_end": array_end,
        "elements": _element_ranges(source, value_start + 1, array_end - 1),
    }


def _module_exports_object(source: str) -> dict[str, Any]:
    match = re.search(r"\bmodule\s*\.\s*exports\s*=", source)
    if not match:
        return {"ok": False, "reason": "module_exports_assignment_required"}
    start = _skip_space_and_comments(source, match.end(), len(source))
    if start >= len(source) or source[start] != "{":
        return {"ok": False, "reason": "static_module_exports_object_required"}
    end = _balanced_end(source, start)
    if end is None:
        return {"ok": False, "reason": "unbalanced_module_exports_object"}
    return {"ok": True, "start": start, "end": end}


def _object_properties(source: str, start: int, end: int) -> list[dict[str, Any]] | None:
    item_start = _skip_space_and_comments(source, start, end)
    if item_start >= end or source[item_start] != "{":
        return None
    item_end = _balanced_end(source, item_start)
    if item_end is None or item_end > end:
        return None
    return _property_ranges(source, item_start + 1, item_end - 1)


def _property_ranges(source: str, start: int, end: int) -> list[dict[str, Any]]:
    return _top_level_ranges(source, start, end)


def _element_ranges(source: str, start: int, end: int) -> list[dict[str, Any]]:
    return _top_level_ranges(source, start, end)


def _top_level_ranges(source: str, start: int, end: int) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    segment_start = start
    index = start
    stack: list[str] = []
    state = "normal"
    quote = ""
    while index < end:
        char = source[index]
        nxt = source[index + 1] if index + 1 < end else ""
        if state == "string":
            if char == "\\":
                index += 2
                continue
            if char == quote:
                state = "normal"
            index += 1
            continue
        if state == "line_comment":
            if char in "\r\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                state = "normal"
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"', "`"}:
            state = "string"
            quote = char
            index += 1
            continue
        if char == "/" and nxt == "/":
            state = "line_comment"
            index += 2
            continue
        if char == "/" and nxt == "*":
            state = "block_comment"
            index += 2
            continue
        if char in "{[(":
            stack.append(char)
        elif char in "}])":
            if stack:
                stack.pop()
        elif char == "," and not stack:
            item_start, item_end = _trim_range(source, segment_start, index)
            if item_start < item_end:
                ranges.append({"start": item_start, "end": item_end})
            segment_start = index + 1
        index += 1
    item_start, item_end = _trim_range(source, segment_start, end)
    if item_start < item_end:
        ranges.append({"start": item_start, "end": item_end})
    return ranges


def _property_parts(source: str, start: int, end: int) -> dict[str, Any] | None:
    content_start = _skip_space_and_comments(source, start, end)
    colon = _top_level_colon(source, content_start, end)
    if colon is None:
        return None
    key_text = source[content_start:colon].strip()
    key = _parse_property_key(key_text)
    if not key:
        return None
    value_start, value_end = _trim_range(source, colon + 1, end)
    return {
        "key": key,
        "start": start,
        "end": end,
        "value_start": value_start,
        "value_end": value_end,
    }


def _top_level_colon(source: str, start: int, end: int) -> int | None:
    index = start
    stack: list[str] = []
    state = "normal"
    quote = ""
    while index < end:
        char = source[index]
        nxt = source[index + 1] if index + 1 < end else ""
        if state == "string":
            if char == "\\":
                index += 2
                continue
            if char == quote:
                state = "normal"
            index += 1
            continue
        if state == "line_comment":
            if char in "\r\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                state = "normal"
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"', "`"}:
            state = "string"
            quote = char
        elif char == "/" and nxt == "/":
            state = "line_comment"
            index += 1
        elif char == "/" and nxt == "*":
            state = "block_comment"
            index += 1
        elif char in "{[(":
            stack.append(char)
        elif char in "}])":
            if stack:
                stack.pop()
        elif char == ":" and not stack:
            return index
        index += 1
    return None


def _static_string_property(
    source: str,
    properties: list[dict[str, Any]],
    key: str,
) -> str:
    values = []
    for item in properties:
        parsed = _property_parts(source, item["start"], item["end"])
        if parsed and parsed["key"] == key:
            values.append(_parse_js_string(source[parsed["value_start"] : parsed["value_end"]]))
    return values[0] if len(values) == 1 and values[0] is not None else ""


def _static_scalar_property(
    source: str,
    properties: list[dict[str, Any]],
    key: str,
) -> str:
    values = []
    for item in properties:
        parsed = _property_parts(source, item["start"], item["end"])
        if parsed and parsed["key"] == key:
            values.append(source[parsed["value_start"] : parsed["value_end"]].strip())
    return values[0] if len(values) == 1 else ""


def _parse_property_key(value: str) -> str:
    stripped = value.strip()
    parsed = _parse_js_string(stripped)
    if parsed is not None:
        return parsed
    return stripped if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$-]*", stripped) else ""


def _parse_js_string(value: str) -> str | None:
    stripped = value.strip()
    if len(stripped) < 2 or stripped[0] not in {"'", '"'} or stripped[-1] != stripped[0]:
        return None
    try:
        parsed = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return None
    return parsed if isinstance(parsed, str) else None


def _canonical_range_control(*, param_from: str, param_to: str, label: str, indent: str) -> str:
    inner = indent + "  "
    width = plan_selector_row_widths(["selector"])["selector"]
    return (
        "{\n"
        f"{inner}type: 'range-datepicker',\n"
        f"{inner}paramFrom: {json.dumps(param_from, ensure_ascii=False)},\n"
        f"{inner}paramTo: {json.dumps(param_to, ensure_ascii=False)},\n"
        f"{inner}label: {json.dumps(label, ensure_ascii=False)},\n"
        f"{inner}labelPlacement: 'left',\n"
        f"{inner}width: '{width}',\n"
        f"{inner}updateOnChange: true,\n"
        f"{indent}}}"
    )


def _element_removal_span(
    source: str,
    *,
    controls_start: int,
    controls_end: int,
    item_start: int,
    item_end: int,
) -> tuple[int, int]:
    index = item_start - 1
    while index > controls_start and source[index].isspace():
        index -= 1
    if source[index] == ",":
        return index, item_end
    index = item_end
    while index < controls_end and source[index].isspace():
        index += 1
    if index < controls_end and source[index] == ",":
        return item_start, index + 1
    return item_start, item_end


def _params_property_insertion(
    source: str,
    *,
    object_start: int,
    object_end: int,
    values: dict[str, list[str]],
) -> str:
    existing = _property_ranges(source, object_start + 1, object_end - 1)
    indent = "  "
    if existing:
        indent = _line_indent(source, existing[0]["start"]) or "  "
    rendered = ",\n".join(
        f"{indent}{json.dumps(key, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in values.items()
    )
    if not existing:
        return "\n" + rendered + "\n"
    return ",\n" + rendered + "\n"


def _mounted_default_candidates(
    data: dict[str, Any],
    *,
    selector_object_id: str,
    mounted_control_id: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def walk(value: Any, path: tuple[Any, ...]) -> None:
        if isinstance(value, dict):
            default_paths: list[tuple[Any, ...]] = []
            if isinstance(value.get("defaults"), dict):
                default_paths.append(path + ("defaults",))
            nested_data = value.get("data")
            if isinstance(nested_data, dict) and isinstance(nested_data.get("defaults"), dict):
                default_paths.append(path + ("data", "defaults"))
            for defaults_path in default_paths:
                defaults = _value_at_path(data, defaults_path)
                mount_id = _mount_identity(value)
                source_ids = _source_ids(value)
                mount_matches = bool(mounted_control_id and mount_id == mounted_control_id)
                source_matches = selector_object_id in source_ids
                if (mounted_control_id and mount_matches and source_matches) or (
                    not mounted_control_id and source_matches
                ):
                    candidates.append(
                        {
                            "defaults_path": defaults_path,
                            "mount_id": mount_id or mounted_control_id,
                        }
                    )
            for key, item in value.items():
                walk(item, path + (key,))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + (index,))

    walk(data, ())
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in candidates:
        existing = unique.get(candidate["defaults_path"])
        if existing is None or (not existing.get("mount_id") and candidate.get("mount_id")):
            unique[candidate["defaults_path"]] = candidate
    return list(unique.values())


def _mount_identity(value: dict[str, Any]) -> str:
    for container in (value, value.get("data") if isinstance(value.get("data"), dict) else {}):
        for key in ("id", "itemId", "item_id", "widgetId", "widget_id", "controlId", "control_id"):
            if str(container.get(key) or "").strip():
                return str(container[key]).strip()
    return ""


def _source_ids(value: dict[str, Any]) -> set[str]:
    ids: set[str] = set()

    def walk(item: Any, parent_key: str = "") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = str(key).replace("_", "").lower()
                if normalized in {"chartid", "entryid", "sourceid", "selectorid"} and str(child).strip():
                    ids.add(str(child).strip())
                elif normalized == "id" and parent_key in {"source", "chart", "selector"} and str(child).strip():
                    ids.add(str(child).strip())
                if key != "defaults":
                    walk(child, str(key).lower())
        elif isinstance(item, list):
            for child in item:
                walk(child, parent_key)

    walk(value)
    return ids


def _extract_entry(readback: dict[str, Any], *, expected_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            object_id = _entry_id(value)
            if object_id == expected_id and isinstance(value.get("data"), dict):
                matches.append(value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(readback)
    unique: dict[str, dict[str, Any]] = {}
    for item in matches:
        identity = json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        unique[identity] = item
    if not unique:
        return {"ok": False, "reason": "target_entry_missing"}
    if len(unique) > 1:
        return {"ok": False, "reason": "target_entry_ambiguous"}
    return {"ok": True, "entry": deepcopy(next(iter(unique.values())))}


def _entry_id(entry: dict[str, Any]) -> str:
    return str(
        entry.get("entryId")
        or entry.get("entry_id")
        or entry.get("dashboardId")
        or entry.get("chartId")
        or entry.get("id")
        or ""
    ).strip()


def _revision(entry: dict[str, Any]) -> str:
    return str(entry.get("revId") or entry.get("rev_id") or entry.get("revision") or "").strip()


def _resolve_artifact_path(root: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _value_at_path(value: Any, path: tuple[Any, ...]) -> Any:
    current = value
    for part in path:
        if isinstance(part, int) and isinstance(current, list) and 0 <= part < len(current):
            current = current[part]
        elif isinstance(part, str) and isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _balanced_end(source: str, start: int) -> int | None:
    pairs = {"{": "}", "[": "]", "(": ")"}
    if start >= len(source) or source[start] not in pairs:
        return None
    stack = [source[start]]
    index = start + 1
    state = "normal"
    quote = ""
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "string":
            if char == "\\":
                index += 2
                continue
            if char == quote:
                state = "normal"
            index += 1
            continue
        if state == "line_comment":
            if char in "\r\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                state = "normal"
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"', "`"}:
            state = "string"
            quote = char
        elif char == "/" and nxt == "/":
            state = "line_comment"
            index += 1
        elif char == "/" and nxt == "*":
            state = "block_comment"
            index += 1
        elif char in pairs:
            stack.append(char)
        elif char in pairs.values():
            if not stack or pairs[stack[-1]] != char:
                return None
            stack.pop()
            if not stack:
                return index + 1
        index += 1
    return None


def _skip_space_and_comments(source: str, start: int, end: int) -> int:
    index = start
    while index < end:
        if source[index].isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2, end)
            return end if newline < 0 else _skip_space_and_comments(source, newline + 1, end)
        if source.startswith("/*", index):
            close = source.find("*/", index + 2, end)
            return end if close < 0 else _skip_space_and_comments(source, close + 2, end)
        return index
    return index


def _trim_range(source: str, start: int, end: int) -> tuple[int, int]:
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    return start, end


def _line_indent(source: str, index: int) -> str:
    line_start = source.rfind("\n", 0, index) + 1
    prefix = source[line_start:index]
    if prefix.strip():
        return re.match(r"[ \t]*", prefix).group(0)
    return prefix


def _apply_text_edits(source: str, edits: list[tuple[int, int, str]]) -> str:
    result = source
    for start, end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def _patch_blocked(reason: str) -> dict[str, Any]:
    return {"ok": False, "blocked_reasons": [reason]}


def _blocked(
    reasons: list[str],
    *,
    selector_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": DATE_RANGE_FAST_PATH_SCHEMA_VERSION,
        "kind": DATE_RANGE_MAINTENANCE_KIND,
        "blocked_reasons": list(dict.fromkeys(str(reason) for reason in reasons if str(reason))),
        "selector_contract": selector_contract or {},
        "actions": [],
        "workflow_metrics": date_range_fast_path_budget(),
    }
