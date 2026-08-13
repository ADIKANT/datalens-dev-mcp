from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from datalens_dev_mcp.editor.render_compiler import (
    RENDER_COMPILER_ID,
    compile_bundle_render_contract,
    validate_compiled_render_contract,
)
from datalens_dev_mcp.editor.render_contract import canonical_sha256
from datalens_dev_mcp.editor.title_contract import validate_title_contract
from datalens_dev_mcp.runtime_resources import resource_text


STANDARD_DASHBOARD_RUNTIME_RESOURCE = (
    "templates/datalens/authoring_profiles/standard_dashboard/advanced_editor_runtime.js"
)
STANDARD_DASHBOARD_ADAPTER_RESOURCE = (
    "templates/datalens/authoring_profiles/standard_dashboard/prepare_adapter.js"
)
STANDARD_DASHBOARD_RUNTIME_SHA256 = (
    "c3e69739a22f825f80654afd0a70a9602e7cb1f63c5cfcda1f3dc7040ea96e13"
)
STANDARD_DASHBOARD_RUNTIME_BYTES = 96_888
STANDARD_DASHBOARD_ADAPTER_SHA256 = (
    "facfa61fb1a75e8c0abc1fc520b1b80b6f13f65f1135c3c531f544a5cfded407"
)
STANDARD_DASHBOARD_RENDER_COMPILER_ID = "resolved_render_contract"

REFERENCE_RUNTIME_FAMILY_ADAPTERS = {
    "kpi_value_only": "metric_tile",
    "kpi_value_delta": "metric_tile",
    "kpi_value_sparkline": "metric_tile",
    "kpi_value_delta_sparkline": "metric_tile",
    "line_chart": "combo_line",
    "multiline_chart": "combo_line",
    "area_completion": "combo_area",
    "vertical_bar_time_bucket": "combo_bar",
    "combo_time_series_combo": "combo_mixed",
    "horizontal_bar": "horizontal",
    "grouped_bar": "horizontal_grouped",
}


class StandardDashboardRuntimeError(ValueError):
    pass


def compile_standard_dashboard_renderer(
    bundle: dict[str, Any],
    *,
    render_contract: dict[str, Any],
    title_contract: dict[str, Any],
) -> dict[str, Any]:
    """Compile canonical chrome and use the exact registered runtime where supported."""

    title_issues = validate_title_contract(title_contract)
    if title_issues:
        raise StandardDashboardRuntimeError("invalid title contract: " + "; ".join(title_issues))
    route = str(bundle.get("route") or "")
    family = str(bundle.get("family") or "")
    if route == "editor_advanced" and family in REFERENCE_RUNTIME_FAMILY_ADAPTERS:
        compiled = _compile_exact_reference_runtime(
            bundle,
            render_contract=render_contract,
            title_contract=title_contract,
        )
    else:
        compiled = compile_bundle_render_contract(bundle, render_contract=render_contract)
        compiled["title_contract"] = deepcopy(title_contract)
        compiled = _apply_title_chrome(compiled, title_contract=title_contract)
        provenance = deepcopy(compiled.get("template_provenance") or {})
        provenance.update(
            {
                "dashboard_render_compiler_id": STANDARD_DASHBOARD_RENDER_COMPILER_ID,
                "base_render_compiler_id": RENDER_COMPILER_ID,
                "renderer_kind": "registered_template",
                "title_contract_sha256": title_contract["sha256"],
            }
        )
        compiled["template_provenance"] = provenance
    validation = validate_standard_dashboard_renderer(compiled)
    if not validation["ok"]:
        raise StandardDashboardRuntimeError(
            "compiled standard dashboard renderer failed: " + "; ".join(validation["issues"])
        )
    compiled["standard_dashboard_renderer_validation"] = validation
    return compiled


def _apply_title_chrome(
    bundle: dict[str, Any],
    *,
    title_contract: dict[str, Any],
) -> dict[str, Any]:
    if str(bundle.get("route") or "") != "editor_advanced":
        return bundle
    compiled = deepcopy(bundle)
    tabs = deepcopy(compiled.get("tabs") or {})
    prepare = str(tabs.get("prepare.js") or "")
    needle = "  return Editor.generateHtml(output);\n}"
    if needle not in prepare:
        raise StandardDashboardRuntimeError("registered title chrome insertion point is missing")
    encoded = json.dumps(
        title_contract,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    declaration = (
        f"const __DL_TITLE_CONTRACT = Object.freeze({encoded});\n"
        "function __dlTitleEsc(value) {\n"
        "  return String(value == null ? '' : value)\n"
        "    .replace(/&/g, '&amp;').replace(/</g, '&lt;')\n"
        "    .replace(/>/g, '&gt;').replace(/\\\"/g, '&quot;');\n"
        "}\n"
    )
    insertion = """  const titleMode = String(__DL_TITLE_CONTRACT.mode || '');
  const titleText = __dlTitleEsc(__DL_TITLE_CONTRACT.display_title || '');
  const hintText = __dlTitleEsc(__DL_TITLE_CONTRACT.hint || '');
  if (titleMode === 'embedded_title') {
    const hint = hintText
      ? `<span data-role="embedded-hint" title="${hintText}" `
        + `style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;`
        + `border-radius:50%;background:var(--g-color-base-generic,#F2F3F5);`
        + `color:var(--g-color-text-secondary,#667085);font-size:12px;font-weight:800;flex:0 0 auto;">?</span>`
      : '';
    const chrome = `<div data-role="embedded-title" `
      + `style="display:flex;align-items:center;gap:7px;min-width:0;margin-bottom:8px;">`
      + `<div style="font-size:17px;line-height:21px;font-weight:800;white-space:nowrap;`
      + `overflow:hidden;text-overflow:ellipsis;">${titleText}</div>${hint}</div>`;
    output = `<div data-role="title-owned-widget" `
      + `style="display:flex;flex-direction:column;width:100%;height:100%;min-height:0;">`
      + `${chrome}<div style="min-height:0;flex:1;">${output}</div></div>`;
  } else if (titleMode === 'content_label') {
    const hint = hintText
      ? `<span data-role="content-hint" title="${hintText}" `
        + `style="margin-left:6px;color:var(--g-color-text-secondary,#667085);">?</span>`
      : '';
    output = `<div data-role="content-label" `
      + `style="font-size:12px;line-height:15px;color:var(--g-color-text-secondary,#667085);margin-bottom:4px;">`
      + `${titleText}${hint}</div>${output}`;
  }
  return Editor.generateHtml(output);
}"""
    tabs["prepare.js"] = declaration + prepare.replace(needle, insertion, 1)
    compiled["tabs"] = tabs
    provenance = deepcopy(compiled.get("template_provenance") or {})
    provenance["compiled_tabs_sha256"] = canonical_sha256(tabs)
    compiled["template_provenance"] = provenance
    return compiled


def validate_standard_dashboard_renderer(bundle: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    provenance = bundle.get("template_provenance") if isinstance(bundle.get("template_provenance"), dict) else {}
    title_contract = bundle.get("title_contract") if isinstance(bundle.get("title_contract"), dict) else {}
    issues.extend(validate_title_contract(title_contract))
    if provenance.get("dashboard_render_compiler_id") != STANDARD_DASHBOARD_RENDER_COMPILER_ID:
        issues.append("dashboard_render_compiler_id_mismatch")
    if provenance.get("title_contract_sha256") != title_contract.get("sha256"):
        issues.append("title_contract_provenance_mismatch")
    tabs = bundle.get("tabs") if isinstance(bundle.get("tabs"), dict) else {}
    if provenance.get("compiled_tabs_sha256") != canonical_sha256(tabs):
        issues.append("compiled_tabs_sha256_mismatch")

    renderer_kind = str(provenance.get("renderer_kind") or "")
    if renderer_kind == "exact_standard_dashboard_runtime":
        prepare = str(tabs.get("prepare.js") or "")
        runtime = _verified_resource(
            STANDARD_DASHBOARD_RUNTIME_RESOURCE,
            expected_sha256=STANDARD_DASHBOARD_RUNTIME_SHA256,
            expected_bytes=STANDARD_DASHBOARD_RUNTIME_BYTES,
        )
        if prepare.count(runtime) != 1:
            issues.append("canonical_runtime_not_embedded_exactly_once")
        if provenance.get("canonical_runtime_sha256") != STANDARD_DASHBOARD_RUNTIME_SHA256:
            issues.append("canonical_runtime_provenance_mismatch")
        if provenance.get("canonical_runtime_embedded_verbatim") is not True:
            issues.append("canonical_runtime_verbatim_marker_missing")
        marker = (
            f"standard-dashboard-runtime:{STANDARD_DASHBOARD_RUNTIME_SHA256};"
            f" adapter:{STANDARD_DASHBOARD_ADAPTER_SHA256};"
        )
        if marker not in prepare:
            issues.append("protected_runtime_marker_missing")
        encoded_spec = json.dumps(
            _runtime_spec(bundle, title_contract=title_contract),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if f"const DASHBOARD_RENDER_SPEC = {encoded_spec};" not in prepare:
            issues.append("runtime_title_or_family_spec_mismatch")
    elif renderer_kind == "registered_template":
        base_validation = validate_compiled_render_contract(bundle)
        issues.extend(f"base:{issue}" for issue in base_validation["issues"])
    else:
        issues.append("unregistered_renderer_kind")
    return {
        "ok": not issues,
        "schema_id": "standard_dashboard_renderer_validation",
        "issues": issues,
        "renderer_kind": renderer_kind,
        "compiled_tabs_sha256": canonical_sha256(tabs),
        "title_contract_sha256": str(title_contract.get("sha256") or ""),
    }


def protected_renderer_identity(bundle: dict[str, Any]) -> dict[str, str]:
    provenance = bundle.get("template_provenance") if isinstance(bundle.get("template_provenance"), dict) else {}
    tabs = bundle.get("tabs") if isinstance(bundle.get("tabs"), dict) else {}
    return {
        "renderer_kind": str(provenance.get("renderer_kind") or ""),
        "runtime_sha256": str(provenance.get("canonical_runtime_sha256") or ""),
        "adapter_sha256": str(provenance.get("canonical_adapter_sha256") or ""),
        "protected_prepare_sha256": hashlib.sha256(str(tabs.get("prepare.js") or "").encode("utf-8")).hexdigest(),
        "compiled_tabs_sha256": canonical_sha256(tabs),
    }


def _compile_exact_reference_runtime(
    bundle: dict[str, Any],
    *,
    render_contract: dict[str, Any],
    title_contract: dict[str, Any],
) -> dict[str, Any]:
    runtime = _verified_resource(
        STANDARD_DASHBOARD_RUNTIME_RESOURCE,
        expected_sha256=STANDARD_DASHBOARD_RUNTIME_SHA256,
        expected_bytes=STANDARD_DASHBOARD_RUNTIME_BYTES,
    )
    adapter = _verified_resource(
        STANDARD_DASHBOARD_ADAPTER_RESOURCE,
        expected_sha256=STANDARD_DASHBOARD_ADAPTER_SHA256,
    )
    if "__DATALENS_DASHBOARD_RENDER_SPEC__" not in adapter or "/* __DATALENS_STANDARD_DASHBOARD_RUNTIME__ */" not in adapter:
        raise StandardDashboardRuntimeError("registered adapter placeholders are missing")
    compiled = deepcopy(bundle)
    tabs = deepcopy(compiled.get("tabs") or {})
    base_tabs_sha256 = canonical_sha256(tabs)
    spec = _runtime_spec(compiled, title_contract=title_contract)
    encoded_spec = json.dumps(spec, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    marker = (
        f"/* standard-dashboard-runtime:{STANDARD_DASHBOARD_RUNTIME_SHA256};"
        f" adapter:{STANDARD_DASHBOARD_ADAPTER_SHA256};"
        f" contract:{render_contract.get('composite_sha256') or ''};"
        f" compiler:{STANDARD_DASHBOARD_RENDER_COMPILER_ID} */"
    )
    prepare = adapter.replace("__DATALENS_DASHBOARD_RENDER_SPEC__", encoded_spec).replace(
        "/* __DATALENS_STANDARD_DASHBOARD_RUNTIME__ */",
        runtime,
    )
    tabs["prepare.js"] = marker + "\n" + prepare
    compiled["tabs"] = tabs
    compiled["render_contract"] = deepcopy(render_contract)
    compiled["title_contract"] = deepcopy(title_contract)
    provenance = deepcopy(compiled.get("template_provenance") or {})
    provenance.update(
        {
            "base_compiled_tabs_sha256": base_tabs_sha256,
            "compiled_tabs_sha256": canonical_sha256(tabs),
            "dashboard_render_compiler_id": STANDARD_DASHBOARD_RENDER_COMPILER_ID,
            "renderer_kind": "exact_standard_dashboard_runtime",
            "canonical_runtime_resource": STANDARD_DASHBOARD_RUNTIME_RESOURCE,
            "canonical_runtime_bytes": len(runtime.encode("utf-8")),
            "canonical_runtime_sha256": STANDARD_DASHBOARD_RUNTIME_SHA256,
            "canonical_runtime_embedded_verbatim": True,
            "canonical_adapter_resource": STANDARD_DASHBOARD_ADAPTER_RESOURCE,
            "canonical_adapter_sha256": STANDARD_DASHBOARD_ADAPTER_SHA256,
            "render_contract_profile_sha256": render_contract.get("profile_sha256"),
            "render_contract_composite_sha256": render_contract.get("composite_sha256"),
            "title_contract_sha256": title_contract["sha256"],
        }
    )
    compiled["template_provenance"] = provenance
    return compiled


def _runtime_spec(bundle: dict[str, Any], *, title_contract: dict[str, Any]) -> dict[str, Any]:
    family = str(bundle.get("family") or "")
    return {
        "schema_id": "standard_dashboard_runtime_spec",
        "family": family,
        "adapter": REFERENCE_RUNTIME_FAMILY_ADAPTERS.get(family, ""),
        "title": str(title_contract.get("display_title") or ""),
        "hint": str(title_contract.get("hint") or ""),
        "title_mode": str(title_contract.get("mode") or ""),
        "title_contract_sha256": str(title_contract.get("sha256") or ""),
    }


def _verified_resource(path: str, *, expected_sha256: str, expected_bytes: int | None = None) -> str:
    value = resource_text(path)
    raw = value.encode("utf-8")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise StandardDashboardRuntimeError(f"registered resource hash mismatch: {path}")
    if expected_bytes is not None and len(raw) != expected_bytes:
        raise StandardDashboardRuntimeError(f"registered resource byte length mismatch: {path}")
    return value
