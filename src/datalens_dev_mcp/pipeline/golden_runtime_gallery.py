from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from datalens_dev_mcp.editor.bundle import generate_editor_bundle
from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT
from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan, load_wizard_template_registry
from datalens_dev_mcp.pipeline.route_registry import visualization_for_family
from datalens_dev_mcp.runtime_resources import resource_json
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.route_validator import validate_route_payload


INVENTORY_RESOURCE = "config/golden_runtime_gallery_inventory.json"
CONTRACTS_RESOURCE = "config/golden_runtime_gallery_contracts.json"
SCHEMA_VERSION = "2026-07-01.golden_runtime_gallery_contracts.v1"
STATIC_WORKBOOK_PLACEHOLDER = "<GOLDEN_TEST_WORKBOOK_ID>"
DEFAULT_BROWSER_UNAVAILABLE_REASON = (
    "No rendered DataLens URL, browser authentication, or browser capture artifact is configured for this static run."
)


def load_golden_inventory() -> dict[str, Any]:
    return resource_json(INVENTORY_RESOURCE)


def load_golden_contracts() -> dict[str, Any]:
    return resource_json(CONTRACTS_RESOURCE)


def build_golden_contracts(
    *,
    inventory: dict[str, Any] | None = None,
    static_workbook_id: str = STATIC_WORKBOOK_PLACEHOLDER,
    browser_unavailable_reason: str = DEFAULT_BROWSER_UNAVAILABLE_REASON,
) -> dict[str, Any]:
    active_inventory = deepcopy(inventory or load_golden_inventory())
    _validate_inventory(active_inventory)
    contracts = [
        _build_family_contract(active_inventory, family, static_workbook_id, browser_unavailable_reason)
        for family in active_inventory["supported_family_inventory"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "inventory_schema_version": active_inventory["schema_version"],
        "inventory_digest": _sha256_json(
            {
                "route_inventory": active_inventory["route_inventory"],
                "supported_family_inventory": active_inventory["supported_family_inventory"],
            }
        ),
        "static_workbook_placeholder": static_workbook_id,
        "write_policy": active_inventory["write_policy"],
        "route_inventory": active_inventory["route_inventory"],
        "contracts": contracts,
        "summary": _summary(active_inventory, contracts),
    }


def compare_generated_to_golden(
    *,
    inventory: dict[str, Any] | None = None,
    golden: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = build_golden_contracts(inventory=inventory)
    expected = golden or load_golden_contracts()
    mismatches: list[dict[str, str]] = []
    if _canonical_json(generated) != _canonical_json(expected):
        generated_by_family = _contracts_by_family(generated)
        expected_by_family = _contracts_by_family(expected)
        for family_id in sorted(set(generated_by_family) | set(expected_by_family)):
            left = generated_by_family.get(family_id)
            right = expected_by_family.get(family_id)
            if left is None:
                mismatches.append({"family_id": family_id, "field": "<family>", "message": "missing from generated"})
                continue
            if right is None:
                mismatches.append({"family_id": family_id, "field": "<family>", "message": "missing from golden"})
                continue
            for field in (
                "source_data_contract",
                "params_contract",
                "template_contract",
                "generated_payload",
                "validators",
                "saved_readback",
                "published_readback",
                "browser_proof",
                "known_limits",
                "do_not_change_runtime_contract",
            ):
                if _canonical_json(left.get(field)) != _canonical_json(right.get(field)):
                    mismatches.append({"family_id": family_id, "field": field, "message": "field drift"})
        if not mismatches:
            mismatches.append({"family_id": "<root>", "field": "<document>", "message": "root metadata drift"})
    return {
        "ok": not mismatches,
        "schema_version": "2026-07-01.golden_runtime_gallery_compare.v1",
        "generated_family_count": len(generated.get("contracts") or []),
        "golden_family_count": len(expected.get("contracts") or []),
        "mismatches": mismatches,
    }


def _build_family_contract(
    inventory: dict[str, Any],
    family: dict[str, Any],
    static_workbook_id: str,
    browser_unavailable_reason: str,
) -> dict[str, Any]:
    route = str(family["route"])
    spec = ROUTE_CONTRACT.spec(route)
    source_contract = deepcopy(inventory["source_data_contracts"][family["source_contract_ref"]])
    params_contract = deepcopy(inventory["params_contracts"][family["params_contract_ref"]])
    route_contract = _route_inventory_item(inventory, route)
    family_id = str(family["family_id"])
    title = str(family.get("title") or f"Golden {family_id.replace('_', ' ').title()}")
    widget_id = str(family.get("widget_id") or f"golden_{family_id}")
    if route == "wizard_native":
        generated = _build_wizard_contract(family_id, source_contract, params_contract)
    elif route == "ql_explicit":
        generated = _build_ql_contract(family_id, source_contract, params_contract)
    else:
        generated = _build_editor_contract(
            family_id=family_id,
            route=route,
            title=title,
            widget_id=widget_id,
            source_contract=source_contract,
            static_workbook_id=static_workbook_id,
        )
    known_limits = list(route_contract.get("known_limits") or []) + list(family.get("known_limits") or [])
    do_not_change = list(route_contract.get("do_not_change_runtime_contract") or []) + list(
        family.get("do_not_change_runtime_contract") or []
    )
    return {
        "family_id": family_id,
        "route": route,
        "support_status": "supported",
        "entry_type": spec.entry_type,
        "widget_kind": spec.widget_kind,
        "representative_object": {
            "widget_id": widget_id,
            "title": title,
            "template_family": family.get("template_family", family_id),
            "generator": route_contract["generator"],
            "create_method": spec.create_method,
            "read_method": spec.read_method,
            "update_method": spec.update_method,
        },
        "source_data_contract": source_contract,
        "params_contract": params_contract,
        "template_contract": generated["template_contract"],
        "generated_payload": generated["generated_payload"],
        "validators": generated["validators"],
        "saved_readback": _unavailable_readback(
            stage="saved_readback",
            route=route,
            reason="No disposable workbook or live execution target was configured for this static fixture.",
        ),
        "published_readback": _unavailable_readback(
            stage="published_readback",
            route=route,
            reason="Published proof requires a successful saved readback and publish-enabled runtime.",
        ),
        "browser_proof": {
            "browser_rendered": "unavailable",
            "proof_level": "not_run",
            "screenshot_path": None,
            "rendered_url": None,
            "reason": browser_unavailable_reason,
            "must_not_claim_passed": True,
        },
        "known_limits": known_limits,
        "do_not_change_runtime_contract": do_not_change,
    }


def _build_editor_contract(
    *,
    family_id: str,
    route: str,
    title: str,
    widget_id: str,
    source_contract: dict[str, Any],
    static_workbook_id: str,
) -> dict[str, Any]:
    columns = [field["name"] for field in source_contract.get("fields", []) if isinstance(field, dict)]
    bundle = generate_editor_bundle(
        widget_id=widget_id,
        route=route,
        title=title,
        family=family_id,
        dataset_alias=source_contract.get("dataset_alias", "golden_dataset"),
        columns=columns,
        param=(source_contract.get("default_param") or "segment"),
        options=source_contract.get("default_param_values") or ["all"],
        source_mode="golden_fixture",
    )
    route_validation = validate_route_payload(bundle)
    compiled_payload = compile_editor_payload(bundle, workbook_id=static_workbook_id, allow_fixture_source=True)
    runtime_validation = validate_editor_runtime_contract(
        compiled_payload,
        source=f"golden_runtime_gallery:{family_id}",
        allow_unknown_warnings=True,
    )
    spec = ROUTE_CONTRACT.spec(route)
    return {
        "template_contract": {
            "route": route,
            "required_tabs": list(spec.required_tabs),
            "observed_tabs": sorted(bundle["tabs"]),
            "tab_hashes": {name: _sha256_text(bundle["tabs"][name]) for name in sorted(bundle["tabs"])},
            "source_template": bundle.get("source_template", bundle.get("source_gallery", "")),
            "schema_version": bundle.get("schema_version", ""),
        },
        "generated_payload": {
            "kind": "compiled_editor_save_payload",
            "method": spec.update_method,
            "mode": "save",
            "workbook_id": static_workbook_id,
            "hash_algorithm": "sha256(canonical_json)",
            "sha256": _sha256_json(compiled_payload),
        },
        "validators": {
            "route_payload": {"ok": route_validation.ok, "issues": route_validation.issues},
            "editor_runtime_contract": {
                "ok": runtime_validation["ok"],
                "rule_version": runtime_validation["rule_version"],
                "summary": runtime_validation["summary"],
            },
        },
    }


def _build_wizard_contract(
    family_id: str,
    source_contract: dict[str, Any],
    params_contract: dict[str, Any],
) -> dict[str, Any]:
    visualization_id = visualization_for_family(family_id) or ("geolayer" if family_id == "native_map_geo_widget" else "flatTable")
    template_spec = (load_wizard_template_registry().get("templates") or {})[visualization_id]
    fields = [field for field in source_contract.get("fields") or [] if isinstance(field, dict)]
    if not fields:
        fields = [{"name": "dimension", "type": "string"}, {"name": "value", "type": "number"}]
    bindings: dict[str, Any] = {}
    for index, role in enumerate(template_spec.get("required_roles") or []):
        field = fields[min(index, len(fields) - 1)]
        bindings[str(role)] = {"guid": str(field.get("name") or f"field_{index}"), "title": str(field.get("name") or "Field")}
    if family_id == "bubble":
        field = fields[-1]
        bindings["size"] = {"guid": str(field.get("name") or "size"), "title": str(field.get("name") or "Size")}
    config = {
        "route": "wizard_native",
        "visualization_id": visualization_id,
        "semantic_family": family_id,
        "dataset": source_contract.get("dataset_ref", "<GOLDEN_DATASET_ID>"),
        "location": {"workbookId": STATIC_WORKBOOK_PLACEHOLDER, "name": f"Golden {family_id}"},
        "field_bindings": bindings,
        "geo": {"evidence_kind": "validated_map_payload"} if visualization_id == "geolayer" else {},
    }
    plan = build_wizard_payload_plan(config)
    route_validation = validate_route_payload(plan)
    return {
        "template_contract": {
            "route": "wizard_native",
            "required_tabs": [],
            "observed_tabs": [],
            "template_name": plan.get("template_name", "native_map"),
            "payload_shape_status": plan.get("payload_shape_status", ""),
            "geo_evidence_kind": (plan.get("geo_evidence") or {}).get("kind", ""),
            "schema_version": plan.get("schema_version", ""),
        },
        "generated_payload": {
            "kind": "wizard_payload_plan",
            "method": "createWizardChart",
            "mode": "plan_only",
            "workbook_id": STATIC_WORKBOOK_PLACEHOLDER,
            "hash_algorithm": "sha256(canonical_json)",
            "sha256": _sha256_json({"family_id": family_id, "params_contract": params_contract, "plan": plan}),
        },
        "validators": {
            "route_payload": {"ok": route_validation.ok, "issues": route_validation.issues},
            "wizard_template_config": plan.get("validation", {}),
        },
    }


def _build_ql_contract(
    family_id: str,
    source_contract: dict[str, Any],
    params_contract: dict[str, Any],
) -> dict[str, Any]:
    del source_contract
    payload = {
        "route": "ql_explicit",
        "entry_type": "ql_chart",
        "approval_provenance": {
            "selection_origin": "explicit_user_request",
            "request_digest": "golden_explicit_ql_fixture",
        },
        "method": "createQLChart",
        "compiled_payload": {
            "workbookId": STATIC_WORKBOOK_PLACEHOLDER,
            "name": "Golden explicit QL fixture",
            "template": "ql",
            "data": {"query": "SELECT 1 AS value"},
        },
    }
    route_validation = validate_route_payload(payload)
    return {
        "template_contract": {
            "route": "ql_explicit",
            "required_tabs": [],
            "observed_tabs": [],
            "payload_policy": "explicit_payload_or_fresh_saved_seed",
            "schema_version": "2026-07-13.ql_explicit_fixture.v1",
        },
        "generated_payload": {
            "kind": "explicit_ql_payload_fixture",
            "method": "createQLChart",
            "mode": "plan_only",
            "workbook_id": STATIC_WORKBOOK_PLACEHOLDER,
            "hash_algorithm": "sha256(canonical_json)",
            "sha256": _sha256_json({"family_id": family_id, "params_contract": params_contract, "payload": payload}),
        },
        "validators": {
            "route_payload": {"ok": route_validation.ok, "issues": route_validation.issues},
            "ql_explicit_provenance": {"ok": True, "selection_origin": "explicit_user_request"},
        },
    }


def _unavailable_readback(*, stage: str, route: str, reason: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "route": route,
        "status": "unavailable",
        "proof_level": "not_run",
        "artifact_path": None,
        "object_id": None,
        "revision_id": None,
        "reason": reason,
        "required_configuration": [
            "disposable test workbook id",
            "implementation request for the disposable target",
            "fresh saved-object readback",
        ],
        "must_not_claim_passed": True,
    }


def _summary(inventory: dict[str, Any], contracts: list[dict[str, Any]]) -> dict[str, Any]:
    by_route: dict[str, int] = {}
    validator_failures: list[str] = []
    for contract in contracts:
        route = str(contract["route"])
        by_route[route] = by_route.get(route, 0) + 1
        validators = contract.get("validators") or {}
        for name, result in validators.items():
            if isinstance(result, dict) and result.get("ok") is False:
                validator_failures.append(f"{contract['family_id']}:{name}")
    return {
        "supported_route_count": len(inventory["route_inventory"]["supported"]),
        "supported_family_count": len(contracts),
        "families_by_route": dict(sorted(by_route.items())),
        "validator_failure_count": len(validator_failures),
        "validator_failures": validator_failures,
        "saved_readback_available_count": 0,
        "published_readback_available_count": 0,
        "browser_rendered_available_count": 0,
        "browser_rendered_unavailable_count": len(contracts),
    }


def _route_inventory_item(inventory: dict[str, Any], route: str) -> dict[str, Any]:
    for item in inventory["route_inventory"]["supported"]:
        if item["route"] == route:
            return item
    raise KeyError(route)


def _validate_inventory(inventory: dict[str, Any]) -> None:
    supported_routes = {item["route"] for item in inventory["route_inventory"]["supported"]}
    if supported_routes != set(ROUTE_CONTRACT.routes):
        raise ValueError(f"inventory route set drift: {sorted(supported_routes)}")
    source_contracts = inventory.get("source_data_contracts") or {}
    params_contracts = inventory.get("params_contracts") or {}
    for family in inventory.get("supported_family_inventory") or []:
        route = family.get("route")
        if route not in supported_routes:
            raise ValueError(f"unsupported route in family inventory: {route}")
        if family.get("source_contract_ref") not in source_contracts:
            raise ValueError(f"unknown source contract ref for {family.get('family_id')}")
        if family.get("params_contract_ref") not in params_contracts:
            raise ValueError(f"unknown params contract ref for {family.get('family_id')}")


def _contracts_by_family(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["family_id"]): item for item in payload.get("contracts") or []}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
