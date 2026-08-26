from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.editor.authoring_profiles import (
    CANONICAL_AUTHORING_PROFILE_ID,
    resolve_authoring_profile,
)
from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload
from datalens_dev_mcp.editor.reference_runtime import validate_standard_dashboard_renderer
from datalens_dev_mcp.editor.render_contract import canonical_sha256
from datalens_dev_mcp.editor.title_contract import validate_title_contract
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.dashboard_composition import validate_dashboard_composition
from datalens_dev_mcp.pipeline.semantic_patch import validate_semantic_patch_plan
from datalens_dev_mcp.pipeline.evidence_matrix import CHANGE_CLASS_REQUIREMENTS


FINAL_PAYLOAD_ATTESTATION_SCHEMA_ID = "final_payload_attestation"
ATTESTATION_ARTIFACT = "artifacts/final_payload_attestation.json"
ATTESTED_PROFILE_IDS = frozenset({CANONICAL_AUTHORING_PROFILE_ID})
_DESTINATION_KEYS = frozenset(
    {
        "workbookId",
        "workbook_id",
        "entryId",
        "entry_id",
        "dashboardId",
        "dashboard_id",
        "chartId",
        "chart_id",
        "key",
        "revId",
        "rev_id",
        "revision",
        "mode",
    }
)


def build_final_payload_attestation(root: str | Path) -> dict[str, Any]:
    project_root = Path(root)
    issues: list[str] = []
    components: list[dict[str, Any]] = []
    profile_ids: set[str] = set()
    canonical_profile_requested = False

    for bundle_path in sorted(project_root.glob("dashboard/*/bundle.json")):
        bundle = read_json(bundle_path, default={})
        relative = bundle_path.relative_to(project_root).as_posix()
        widget_id = str(bundle.get("widget_id") or bundle_path.parent.name)
        profile = bundle.get("authoring_profile") if isinstance(bundle.get("authoring_profile"), dict) else {}
        profile_id = str(profile.get("id") or "")
        if profile_id:
            profile_ids.add(profile_id)
            resolved_profile = resolve_authoring_profile(
                project_root=project_root,
                requested_profile=profile_id,
            )
            if resolved_profile.get("ok") and resolved_profile.get("id") == CANONICAL_AUTHORING_PROFILE_ID:
                canonical_profile_requested = True
                if profile_id != CANONICAL_AUTHORING_PROFILE_ID:
                    issues.append(
                        f"{relative}: legacy authoring profile {profile_id!r} must be regenerated as "
                        f"{CANONICAL_AUTHORING_PROFILE_ID!r}"
                    )
        route = str(bundle.get("route") or "")
        planned_route = str((bundle.get("chart_decision_record") or {}).get("selected_route") or route)
        if planned_route != route:
            issues.append(f"{relative}: final route {route!r} differs from planned route {planned_route!r}")
        title_contract = bundle.get("title_contract") if isinstance(bundle.get("title_contract"), dict) else {}
        title_issues = validate_title_contract(title_contract) if title_contract else []
        issues.extend(f"{relative}: title_contract: {issue}" for issue in title_issues)
        render_validation: dict[str, Any] = {}
        persisted_tabs = bundle.get("tabs") if isinstance(bundle.get("tabs"), dict) else {}
        for tab_name, expected_text in persisted_tabs.items():
            tab_path = bundle_path.parent / str(tab_name)
            try:
                actual_text = tab_path.read_text(encoding="utf-8")
            except OSError:
                actual_text = None
            if actual_text != expected_text:
                issues.append(f"{relative}: materialized tab {tab_name} differs from bundle.json")
        render_spec = str((profile.get("style_contract") or {}).get("renderer_visual_spec") or "")
        if render_spec.endswith("renderer_visual_spec"):
            render_validation = validate_standard_dashboard_renderer(bundle)
            issues.extend(
                f"{relative}: protected renderer: {issue}"
                for issue in render_validation.get("issues") or []
            )
        try:
            compiled_payload = compile_editor_payload(bundle, workbook_id="__ATTESTED_WORKBOOK__")
        except (KeyError, TypeError, ValueError) as exc:
            compiled_payload = {}
            issues.append(f"{relative}: final Editor payload compile failed: {exc}")
        semantic_patch_plan = bundle.get("semantic_patch_plan")
        if semantic_patch_plan is not None:
            if not isinstance(semantic_patch_plan, dict):
                issues.append(f"{relative}: semantic_patch_plan must be an object")
            else:
                issues.extend(
                    f"{relative}: semantic_patch_plan: {issue}"
                    for issue in validate_semantic_patch_plan(semantic_patch_plan)
                )
        provenance = bundle.get("template_provenance") if isinstance(bundle.get("template_provenance"), dict) else {}
        binding = bundle.get("dashboard_composition_binding") if isinstance(bundle.get("dashboard_composition_binding"), dict) else {}
        components.append(
            {
                "widget_id": widget_id,
                "artifact_path": relative,
                "route": route,
                "planned_route": planned_route,
                "family": str(bundle.get("family") or ""),
                "authoring_profile": profile_id,
                "editor_render_profile": str(profile.get("editor_render_profile") or ""),
                "render_contract_id": str(profile.get("render_contract_id") or render_spec),
                "runtime": {
                    "renderer_kind": str(provenance.get("renderer_kind") or ""),
                    "runtime_sha256": str(provenance.get("canonical_runtime_sha256") or ""),
                    "adapter_sha256": str(provenance.get("canonical_adapter_sha256") or ""),
                    "compiled_tabs_sha256": str(provenance.get("compiled_tabs_sha256") or ""),
                    "protected_prepare_sha256": str(
                        (bundle.get("protected_renderer_identity") or {}).get("protected_prepare_sha256") or ""
                    ),
                },
                "title_mode": str(title_contract.get("mode") or ""),
                "display_title": str(title_contract.get("display_title") or bundle.get("title") or ""),
                "title_contract_sha256": str(title_contract.get("sha256") or ""),
                "selector_contract_sha256": canonical_sha256(bundle.get("selector_contract") or {}),
                "dashboard_composition_sha256": str(binding.get("composition_sha256") or ""),
                "compiled_payload_sha256": canonical_sha256(compiled_payload),
                "binding_neutral_payload_sha256": canonical_sha256(_without_destination_binding(compiled_payload)),
                "tabs_sha256": canonical_sha256(persisted_tabs),
                "render_validation_ok": bool(render_validation.get("ok", True)),
                "semantic_patch_plan_hash": str((semantic_patch_plan or {}).get("plan_hash") or ""),
                "recommended_change_class": _component_change_class(route, str(bundle.get("family") or "")),
            }
        )

    for plan_path in sorted(project_root.glob("artifacts/*.wizard_payload_plan.json")):
        plan = read_json(plan_path, default={})
        relative = plan_path.relative_to(project_root).as_posix()
        widget_id = str(plan.get("widget_id") or plan_path.stem.removesuffix(".wizard_payload_plan"))
        profile = plan.get("authoring_profile") if isinstance(plan.get("authoring_profile"), dict) else {}
        profile_id = str(profile.get("id") or "")
        if profile_id:
            profile_ids.add(profile_id)
            resolved_profile = resolve_authoring_profile(
                project_root=project_root,
                requested_profile=profile_id,
            )
            if resolved_profile.get("ok") and resolved_profile.get("id") == CANONICAL_AUTHORING_PROFILE_ID:
                canonical_profile_requested = True
                if profile_id != CANONICAL_AUTHORING_PROFILE_ID:
                    issues.append(
                        f"{relative}: legacy authoring profile {profile_id!r} must be regenerated as "
                        f"{CANONICAL_AUTHORING_PROFILE_ID!r}"
                    )
        route = str(plan.get("route") or "wizard_native")
        planned_route = str((plan.get("chart_decision_record") or {}).get("selected_route") or route)
        if route != "wizard_native" or planned_route != "wizard_native":
            issues.append(f"{relative}: Wizard-first route was replaced after planning")
        title_contract = plan.get("title_contract") if isinstance(plan.get("title_contract"), dict) else {}
        if title_contract:
            issues.extend(
                f"{relative}: title_contract: {issue}"
                for issue in validate_title_contract(title_contract)
            )
        compiled_payload = deepcopy(plan.get("compiled_payload") or {})
        binding = plan.get("dashboard_composition_binding") if isinstance(plan.get("dashboard_composition_binding"), dict) else {}
        components.append(
            {
                "widget_id": widget_id,
                "artifact_path": relative,
                "route": route,
                "planned_route": planned_route,
                "family": str(plan.get("semantic_family") or plan.get("visualization_id") or ""),
                "authoring_profile": profile_id,
                "editor_render_profile": str(profile.get("editor_render_profile") or ""),
                "render_contract_id": str(profile.get("render_contract_id") or ""),
                "runtime": {},
                "title_mode": str(title_contract.get("mode") or "native_title"),
                "display_title": str(title_contract.get("display_title") or (plan.get("options") or {}).get("title") or ""),
                "title_contract_sha256": str(title_contract.get("sha256") or ""),
                "selector_contract_sha256": canonical_sha256({}),
                "dashboard_composition_sha256": str(binding.get("composition_sha256") or ""),
                "compiled_payload_sha256": canonical_sha256(compiled_payload),
                "binding_neutral_payload_sha256": canonical_sha256(_without_destination_binding(compiled_payload)),
                "tabs_sha256": "",
                "render_validation_ok": True,
                "recommended_change_class": _component_change_class(
                    route,
                    str(plan.get("semantic_family") or plan.get("visualization_id") or ""),
                ),
            }
        )

    requires_attestation = canonical_profile_requested or bool(profile_ids & ATTESTED_PROFILE_IDS) or any(
        str(item.get("render_contract_id") or "").endswith("renderer_visual_spec")
        for item in components
    )
    composition_path = project_root / "artifacts" / "dashboard_composition.json"
    dashboard_payload_path = project_root / "artifacts" / "dashboard_payloads" / "generated.dashboard.payload.json"
    composition = read_json(composition_path, default={}) if composition_path.is_file() else {}
    dashboard_payload = read_json(dashboard_payload_path, default={}) if dashboard_payload_path.is_file() else {}
    if requires_attestation and not composition:
        issues.append("artifacts/dashboard_composition.json is required by the dashboard authoring profile")
    if composition:
        composition_issues = validate_dashboard_composition(composition)
        issues.extend(f"dashboard_composition: {issue}" for issue in composition_issues)
        if dashboard_payload != composition.get("payload_skeleton"):
            issues.append("final dashboard payload differs from the validated composition skeleton")
        composition_hash = str(composition.get("sha256") or "")
        for component in components:
            if component.get("dashboard_composition_sha256") != composition_hash:
                issues.append(
                    f"{component['artifact_path']}: dashboard composition binding is missing or stale"
                )

    ordered_components = sorted(components, key=lambda item: item["widget_id"])
    attestation: dict[str, Any] = {
        "schema_id": FINAL_PAYLOAD_ATTESTATION_SCHEMA_ID,
        "ok": not issues,
        "status": "attested" if not issues else "blocked",
        "applicability": "required" if requires_attestation else "legacy_optional",
        "issues": issues,
        "authoring_profiles": sorted(profile_ids),
        "routes": [
            {
                "widget_id": item["widget_id"],
                "planned": item["planned_route"],
                "actual": item["route"],
            }
            for item in ordered_components
        ],
        "components": ordered_components,
        "intent_aware_qa": {
            "change_classes": sorted(
                {str(item.get("recommended_change_class") or "") for item in ordered_components if item}
            ),
            "requirements": {
                key: list(value)
                for key, value in CHANGE_CLASS_REQUIREMENTS.items()
            },
        },
        "dashboard_composition": {
            "path": composition_path.relative_to(project_root).as_posix(),
            "sha256": str(composition.get("sha256") or ""),
            "layout_hash": canonical_sha256(composition.get("tabs") or []),
            "selector_hash": canonical_sha256(
                [
                    item
                    for tab in composition.get("tabs") or []
                    for row in tab.get("rows") or []
                    for item in row.get("items") or []
                    if item.get("role") == "selector"
                ]
            ),
            "tab_hashes": [
                {"tab_id": str(tab.get("id") or ""), "sha256": canonical_sha256(tab)}
                for tab in composition.get("tabs") or []
            ],
        },
        "dashboard_payload": {
            "path": dashboard_payload_path.relative_to(project_root).as_posix(),
            "sha256": canonical_sha256(dashboard_payload),
            "binding_neutral_sha256": canonical_sha256(
                _dashboard_binding_neutral_payload(dashboard_payload)
            ),
            "mount_bindings_sha256": canonical_sha256(
                _dashboard_mount_bindings(dashboard_payload)
            ),
        },
        "payload_set_sha256": canonical_sha256(
            {
                "components": [
                    {
                        "widget_id": item["widget_id"],
                        "payload": item["compiled_payload_sha256"],
                        "tabs": item["tabs_sha256"],
                    }
                    for item in ordered_components
                ],
                "dashboard": canonical_sha256(dashboard_payload),
            }
        ),
        "qa_requirement": {
            "required_for_publish": requires_attestation,
            "dashboard_revision_bound": True,
            "payload_hash_bound": True,
            "required_viewport_widths": [720, 1200, 1440],
        },
    }
    attestation["attestation_sha256"] = canonical_sha256(
        {key: value for key, value in attestation.items() if key != "attestation_sha256"}
    )
    return attestation


def _component_change_class(route: str, family: str) -> str:
    lowered = f"{route} {family}".lower()
    if "selector" in lowered or "control" in lowered:
        return "selector_behavior"
    if route == "editor_advanced":
        return "renderer_logic"
    return "source_labels_only"


def write_final_payload_attestation(root: str | Path) -> dict[str, Any]:
    project_root = Path(root)
    attestation = build_final_payload_attestation(project_root)
    write_json(project_root / ATTESTATION_ARTIFACT, attestation)
    return attestation


def verify_final_payload_attestation(
    root: str | Path,
    expected: dict[str, Any] | None = None,
) -> list[str]:
    project_root = Path(root)
    stored = expected
    if stored is None:
        path = project_root / ATTESTATION_ARTIFACT
        stored = read_json(path, default={}) if path.is_file() else {}
    if not isinstance(stored, dict) or not stored:
        return ["final_payload_attestation is required"]
    rebuilt = build_final_payload_attestation(project_root)
    issues: list[str] = []
    if stored.get("ok") is not True or stored.get("status") != "attested":
        issues.append("stored final_payload_attestation is not successful")
    if rebuilt.get("ok") is not True:
        issues.extend(f"rebuilt attestation: {issue}" for issue in rebuilt.get("issues") or [])
    if stored.get("attestation_sha256") != rebuilt.get("attestation_sha256"):
        issues.append("final payload changed after validation; regenerate the attestation")
    return issues


def validate_payload_against_attestation(
    payload: dict[str, Any],
    attestation: dict[str, Any],
    *,
    widget_id: str = "",
    is_dashboard: bool = False,
) -> list[str]:
    if not isinstance(attestation, dict) or attestation.get("ok") is not True:
        return ["a successful final_payload_attestation is required"]
    if is_dashboard:
        actual_neutral = canonical_sha256(
            _dashboard_binding_neutral_payload(payload)
        )
        expected = str((attestation.get("dashboard_payload") or {}).get("binding_neutral_sha256") or "")
        expected_mounts = str(
            (attestation.get("dashboard_payload") or {}).get("mount_bindings_sha256")
            or ""
        )
        actual_mounts = canonical_sha256(_dashboard_mount_bindings(payload))
        issues: list[str] = []
        if not expected or actual_neutral != expected:
            issues.append("dashboard payload is absent from or differs from final_payload_attestation")
        if not expected_mounts or actual_mounts != expected_mounts:
            issues.append("dashboard mount to chart bindings differ from final_payload_attestation")
        return issues
    actual_neutral = canonical_sha256(_without_destination_binding(payload))
    candidates = [
        item
        for item in attestation.get("components") or []
        if isinstance(item, dict) and (not widget_id or item.get("widget_id") == widget_id)
    ]
    if not candidates:
        return [f"payload widget {widget_id or '<unknown>'} is absent from final_payload_attestation"]
    if any(item.get("binding_neutral_payload_sha256") == actual_neutral for item in candidates):
        return []
    return [f"payload for widget {widget_id or '<unknown>'} differs from final_payload_attestation"]


def _without_destination_binding(
    value: Any,
    *,
    preserve_chart_ids: bool = False,
) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_destination_binding(
                item,
                preserve_chart_ids=preserve_chart_ids,
            )
            for key, item in value.items()
            if key not in _DESTINATION_KEYS or (preserve_chart_ids and key in {"chartId", "chart_id"})
        }
    if isinstance(value, list):
        return [
            _without_destination_binding(
                item,
                preserve_chart_ids=preserve_chart_ids,
            )
            for item in value
        ]
    return value


def _dashboard_mount_bindings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = payload.get("entry") if isinstance(payload.get("entry"), dict) else payload
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    bindings: list[dict[str, Any]] = []
    for dashboard_tab in data.get("tabs") or []:
        if not isinstance(dashboard_tab, dict):
            continue
        dashboard_tab_id = str(dashboard_tab.get("id") or "")
        for item in dashboard_tab.get("items") or []:
            if not isinstance(item, dict) or str(item.get("type") or "") != "widget":
                continue
            widget_id = str(item.get("id") or "")
            item_data = item.get("data") if isinstance(item.get("data"), dict) else item
            for inner_tab in item_data.get("tabs") or []:
                if not isinstance(inner_tab, dict):
                    continue
                bindings.append(
                    {
                        "dashboard_tab_id": dashboard_tab_id,
                        "widget_id": widget_id,
                        "widget_tab_id": str(inner_tab.get("id") or ""),
                        "chart_id": str(inner_tab.get("chartId") or inner_tab.get("chart_id") or ""),
                    }
                )
    return sorted(
        bindings,
        key=lambda item: (
            item["dashboard_tab_id"],
            item["widget_id"],
            item["widget_tab_id"],
            item["chart_id"],
        ),
    )


def _dashboard_binding_neutral_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project create/update/publish envelopes onto the exact dashboard body."""

    body = payload.get("entry") if isinstance(payload.get("entry"), dict) else payload
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return {
        "display_title": str(meta.get("title") or body.get("display_title") or ""),
        "data": _without_destination_binding(
            data,
            preserve_chart_ids=True,
        )
    }
