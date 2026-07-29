from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from datalens_dev_mcp.editor.render_contract import render_contract_to_dict


RENDER_COMPILER_VERSION = "2026-07-29.resolved_render_contract.v3"
_HTML_ROUTES = {"editor_advanced"}
_NATIVE_TABLE_ROUTES = {"editor_table"}
_MARKER_ROUTES = {"editor_markdown"}
_CONTROL_ROUTES = {"editor_js_control"}
_SUPPORTED_ROUTES = _HTML_ROUTES | _NATIVE_TABLE_ROUTES | _MARKER_ROUTES | _CONTROL_ROUTES
_ACTIVE_SERIES_FAMILIES = {
    "line_chart",
    "multiline_chart",
    "area_completion",
    "combo_time_series_combo",
}
_COORDINATE_PLOT_FAMILIES = _ACTIVE_SERIES_FAMILIES | {
    "vertical_bar_time_bucket",
    "histogram",
    "box_plot",
    "scatter",
    "bubble",
}


class RenderContractCompileError(ValueError):
    pass


def compile_bundle_render_contract(
    bundle: dict[str, Any],
    *,
    render_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile an exact render contract into generated tabs.

    The legacy template assets stay unchanged. A strict profile receives a
    deterministic runtime adapter whose output is hash-bound to the resolved
    core tokens, family adapter, bounded overrides, and compiled tabs.
    """

    compiled = deepcopy(bundle)
    tabs = compiled.get("tabs") if isinstance(compiled.get("tabs"), dict) else {}
    route = str(compiled.get("route") or "")
    family = str(compiled.get("family") or "")
    contract = render_contract_to_dict(render_contract)
    if contract.get("family") != family:
        raise RenderContractCompileError(
            f"render contract family {contract.get('family')!r} does not match bundle family {family!r}"
        )
    if route not in _SUPPORTED_ROUTES:
        raise RenderContractCompileError(
            f"render contract compiler does not support route {route!r}"
        )

    base_tabs_sha256 = _tabs_sha256(tabs)
    transformed_tabs = dict(tabs)
    transformed_call_count = 0
    if route in _HTML_ROUTES:
        prepare = _required_tab(transformed_tabs, "prepare.js", route=route)
        call_count = prepare.count("Editor.generateHtml(")
        if call_count < 1:
            raise RenderContractCompileError(
                "HTML render profile requires at least one Editor.generateHtml call"
            )
        tooltip_context = _strict_tooltip_context(compiled)
        helper = _runtime_contract_helper(
            contract,
            tooltip_context=tooltip_context,
        )
        transformed = prepare.replace(
            "Editor.generateHtml(",
            "__dlGenerateProfileHtml(options, ",
        )
        transformed_call_count = call_count
        transformed_tabs["prepare.js"] = helper + "\n" + transformed
    elif route in _NATIVE_TABLE_ROUTES:
        prepare = _required_tab(transformed_tabs, "prepare.js", route=route)
        config = _required_tab(transformed_tabs, "config.js", route=route)
        marker = _contract_marker(contract)
        transformed_tabs["prepare.js"] = marker + "\n" + prepare
        transformed_tabs["config.js"] = _native_contract_preamble(contract) + "\n" + config
    elif route in _MARKER_ROUTES:
        prepare = _required_tab(transformed_tabs, "prepare.js", route=route)
        marker = _contract_marker(contract)
        transformed_tabs["prepare.js"] = marker + "\n" + prepare
    else:
        controls = _required_tab(transformed_tabs, "controls.js", route=route)
        selector_contract = (
            compiled.get("selector_contract")
            if isinstance(compiled.get("selector_contract"), dict)
            else {}
        )
        selector_complete = selector_contract.get("ok") is True
        if selector_complete:
            required_fragments = (
                "labelPlacement: 'left'",
                "width: '94%'",
                "updateOnChange: true",
            )
            if any(fragment not in controls for fragment in required_fragments):
                raise RenderContractCompileError(
                    "strict selector profile requires left labels, 94% width, and immediate updates"
                )
        elif compiled.get("generation_status") != "blocked_missing_input":
            raise RenderContractCompileError(
                "incomplete selector contract must remain blocked_missing_input"
            )
        transformed_tabs["controls.js"] = _native_contract_preamble(contract) + "\n" + controls

    compiled["tabs"] = transformed_tabs
    compiled["render_contract"] = contract
    compiled["renderer_visual_spec"] = deepcopy(
        compiled.get("renderer_visual_spec") or {}
    )
    provenance = (
        deepcopy(compiled.get("template_provenance"))
        if isinstance(compiled.get("template_provenance"), dict)
        else {}
    )
    compiled_tabs_sha256 = _tabs_sha256(transformed_tabs)
    provenance.update(
        {
            "base_compiled_tabs_sha256": base_tabs_sha256,
            "compiled_tabs_sha256": compiled_tabs_sha256,
            "render_compiler_version": RENDER_COMPILER_VERSION,
            "render_contract_profile_sha256": contract.get("profile_sha256"),
            "render_contract_composite_sha256": contract.get("composite_sha256"),
            "render_adapter_ids": list(contract.get("adapter_ids") or []),
            "render_transformed_call_count": transformed_call_count,
            "postcompile_invariants": {
                "kpi_surface": "transparent_no_border_radius_outline_shadow",
                "kpi_content": "visible_marked_value_unclipped_equal_set_height",
                "legend_typography": "single_profile_token",
                "legend_series": "filtered_result_rows_active_series_only",
                "selector": "period_first_single_row_target_95_left_immediate_max_94",
                "semantic_heights": "new_h_selector_2_comparison_min_3_kpi_6_update_preserves_saved",
                "comparison_context": "exactly_one_when_enabled_minimum_70px",
                "plot_area": "top_22_right_10_or_16_bottom_34",
                "kpi_sparkline": "all_or_none_within_dashboard_kpi_set",
                "tooltip": "normalized_period_comparison_adaptive_native_owner",
            },
        }
    )
    compiled["template_provenance"] = provenance
    validation = validate_compiled_render_contract(compiled)
    if not validation["ok"]:
        raise RenderContractCompileError(
            "compiled render contract failed: " + "; ".join(validation["issues"])
        )
    compiled["render_contract_validation"] = validation
    return compiled


def validate_compiled_render_contract(bundle: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    contract = (
        bundle.get("render_contract")
        if isinstance(bundle.get("render_contract"), dict)
        else {}
    )
    tabs = bundle.get("tabs") if isinstance(bundle.get("tabs"), dict) else {}
    prepare = str(tabs.get("prepare.js") or "")
    provenance = (
        bundle.get("template_provenance")
        if isinstance(bundle.get("template_provenance"), dict)
        else {}
    )
    composite = str(contract.get("composite_sha256") or "")
    marker = f"resolved-render-contract:{composite}"
    if provenance.get("compiled_tabs_sha256") != _tabs_sha256(tabs):
        issues.append("compiled_tabs_sha256_mismatch")
    if provenance.get("render_contract_composite_sha256") != composite:
        issues.append("render_contract_provenance_mismatch")
    if provenance.get("render_compiler_version") != RENDER_COMPILER_VERSION:
        issues.append("render_compiler_version_mismatch")
    route = str(bundle.get("route") or "")
    if route in _HTML_ROUTES:
        if not composite or marker not in prepare:
            issues.append("resolved_render_contract_marker_missing")
        if "__dlGenerateProfileHtml(options, " not in prepare:
            issues.append("render_contract_not_consumed_by_html_calls")
        if prepare.count("Editor.generateHtml(") != 1:
            issues.append("unwrapped_editor_generate_html_call")
        if 'data-component="${componentKind}"' not in prepare:
            issues.append("runtime_component_marker_missing")
        if 'data-tooltip-comparison-mode="${tooltipComparisonMode}"' not in prepare:
            issues.append("runtime_tooltip_comparison_mode_marker_missing")
        if 'data-tooltip-period-source="${tooltipPeriodSource}"' not in prepare:
            issues.append("runtime_tooltip_period_source_marker_missing")
        family = str(bundle.get("family") or "")
        if family in _ACTIVE_SERIES_FAMILIES:
            for marker_fragment in (
                'data-series-policy="active_series_only"',
                'data-series-role="mark"',
                'data-series-role="legend"',
            ):
                if marker_fragment not in prepare:
                    issues.append(f"active_series_runtime_marker_missing:{marker_fragment}")
        if family in _COORDINATE_PLOT_FAMILIES:
            for marker_fragment in (
                'data-plot-area-policy="contract_insets"',
                'data-role="plot-area"',
                "data-inset-top",
                "data-inset-right",
                "data-inset-bottom",
            ):
                if marker_fragment not in prepare:
                    issues.append(f"plot_area_runtime_marker_missing:{marker_fragment}")
        effective_tokens = (
            contract.get("effective_tokens")
            if isinstance(contract.get("effective_tokens"), dict)
            else {}
        )
        horizontal = (
            effective_tokens.get("horizontal_rank")
            if isinstance(effective_tokens.get("horizontal_rank"), dict)
            else {}
        )
        if horizontal.get("scroll") is True and "scrollbar-gutter:stable" not in prepare:
            issues.append("horizontal_scroll_gutter_runtime_missing")
    elif route in _NATIVE_TABLE_ROUTES:
        config = str(tabs.get("config.js") or "")
        if (
            not composite
            or marker not in prepare
            or marker not in config
            or "const __DL_RENDER_CONTRACT = Object.freeze(" not in config
        ):
            issues.append("native_table_render_contract_marker_missing")
        if "__dlGenerateProfileHtml" in prepare or "__dlGenerateProfileHtml" in config:
            issues.append("native_table_html_wrapper_forbidden")
    elif route in _MARKER_ROUTES:
        if not composite or marker not in prepare:
            issues.append("resolved_render_contract_marker_missing")
    elif route in _CONTROL_ROUTES:
        controls = str(tabs.get("controls.js") or "")
        if (
            not composite
            or marker not in controls
            or "const __DL_RENDER_CONTRACT = Object.freeze(" not in controls
        ):
            issues.append("control_render_contract_marker_missing")
        selector_contract = (
            bundle.get("selector_contract")
            if isinstance(bundle.get("selector_contract"), dict)
            else {}
        )
        if selector_contract.get("ok") is True:
            for fragment in (
                "labelPlacement: 'left'",
                "width: '94%'",
                "updateOnChange: true",
            ):
                if fragment not in controls:
                    issues.append(f"strict_selector_runtime_invariant_missing:{fragment}")
        elif bundle.get("generation_status") != "blocked_missing_input":
            issues.append("incomplete_selector_status_must_be_blocked_missing_input")
    else:
        issues.append("unsupported_render_contract_route")
    if str(bundle.get("family") or "").startswith("kpi_"):
        for token in (
            'data-role="kpi"',
            'data-role="kpi-value"',
            "border:0",
            "border-radius:0",
            "outline:none",
            "box-shadow:none",
            "background:transparent",
        ):
            if token not in prepare:
                issues.append(f"kpi_runtime_invariant_missing:{token}")
    return {
        "ok": not issues,
        "schema_version": "2026-07-29.compiled_render_contract_validation.v2",
        "issues": issues,
        "compiled_tabs_sha256": _tabs_sha256(tabs),
        "render_contract_composite_sha256": composite,
    }


def _runtime_contract_helper(
    contract: dict[str, Any],
    *,
    tooltip_context: dict[str, str],
) -> str:
    encoded = json.dumps(
        contract,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    marker = _contract_marker(contract)
    encoded_context = json.dumps(
        tooltip_context,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"""{marker}
const __DL_RENDER_CONTRACT = Object.freeze({encoded});
const __DL_RENDER_CONTEXT = Object.freeze({encoded_context});
function __dlGenerateProfileHtml(options, html) {{
  const contract = __DL_RENDER_CONTRACT.effective_tokens || {{}};
  const typography = contract.typography || {{}};
  const shell = contract.shell || {{}};
  const density = contract.density || {{}};
  const semantic = contract.semantic_colors || {{}};
  const component = contract.component || {{}};
  const horizontal = contract.horizontal_rank || {{}};
  const plotArea = contract.plot_area || {{}};
  const seriesVisibility = contract.series_visibility || {{}};
  const componentKind = String(component.kind || 'generic_chart')
    .replace(/[^a-z0-9_-]/gi, '') || 'generic_chart';
  const contractFamily = String(__DL_RENDER_CONTRACT.family || '');
  const tooltipComparisonMode = String(__DL_RENDER_CONTEXT.tooltip_comparison_mode || '');
  const tooltipPeriodSource = String(__DL_RENDER_CONTEXT.tooltip_period_source || '');
  const width = Number(options && options.width);
  const compact = density.mode === 'compact' ||
    (density.mode !== 'comfortable' && Number.isFinite(width) &&
      width < Number(density.compact_below_width_px || 720));
  const padding = (shell.padding_px || {{}})[compact ? 'compact' : 'normal'] || {{}};
  const bodyType = typography.body || {{}};
  const legendType = (typography.legend || {{}}).active || {{}};
  const kpi = contract.kpi || {{}};
  const kpiValue = (kpi.value_typography || {{}})[compact ? 'compact' : 'normal'] || {{}};
  const fontFamily = (typography.font_family || ['Inter', 'Arial', 'sans-serif']).join(',');
  const activeSeriesFamilies = ['line_chart', 'multiline_chart', 'area_completion', 'combo_time_series_combo'];
  const coordinatePlotFamilies = activeSeriesFamilies.concat(
    ['vertical_bar_time_bucket', 'histogram', 'box_plot', 'scatter', 'bubble'],
  );
  const seriesPolicyEnabled = activeSeriesFamilies.includes(contractFamily) &&
    seriesVisibility.legend === 'active_series_only' &&
    seriesVisibility.marks === 'active_series_only';
  const plotPolicyEnabled = coordinatePlotFamilies.includes(contractFamily);
  const rightInset = ((plotArea.inset_px || {{}}).right || {{}})[compact ? 'compact' : 'normal'];
  const contractAttributes = (
    (seriesPolicyEnabled ? ' data-series-policy="active_series_only"' : '') +
    (plotPolicyEnabled
      ? (
        ' data-plot-area-policy="contract_insets"' +
        ` data-plot-inset-top="${{Number((plotArea.inset_px || {{}}).top || 0)}}"` +
        ` data-plot-inset-right="${{Number(rightInset || 0)}}"` +
        ` data-plot-inset-bottom="${{Number((plotArea.inset_px || {{}}).bottom || 0)}}"`
      )
      : '')
  );
  let output = String(html == null ? '' : html);
  let wrapperOverflow = '';
  output = output.replace(/font-family:Inter,Arial,sans-serif/g, `font-family:${{fontFamily}}`);
  output = output.replace(/font-size:(?:10|11|12)px/g, `font-size:${{bodyType.font_size_px || 12}}px`);
  output = output.replace(/line-height:1\\.25/g, `line-height:${{bodyType.line_height_px || 16}}px`);
  output = output.replace(
    /(box-sizing:border-box;width:100%;height:100%;)padding:[^;]+;/,
    `$1padding:${{Number(padding.vertical || 0)}}px ${{Number(padding.horizontal || 0)}}px;`,
  );
  output = output.replace(
    /font-size:\\d+(?:\\.\\d+)?px;line-height:1\\.05;font-weight:850/g,
    (
      `font-size:${{Number(kpiValue.font_size_px || 34)}}px;` +
      `line-height:${{Number(kpiValue.line_height_px || 38)}}px;` +
      `font-weight:${{Number((kpi.value_typography || {{}}).font_weight || 750)}}`
    ),
  );
  output = output.replace(/var\\(--g-color-text-positive,[^)]+\\)/g, semantic.success || '#6CBF84');
  output = output.replace(/var\\(--g-color-text-danger,[^)]+\\)/g, semantic.failure || '#E57373');
  output = output.replace(/#2B75E2/gi, semantic.primary || '#2B75E2');
  if (component.kind === 'horizontal_rank') {{
    output = output.replace(
      /grid-template-columns:[^;]+;gap:\\d+(?:\\.\\d+)?px;align-items:center;margin:[^;]+;/g,
      (
        `grid-template-columns:${{Number(horizontal.label_width_px || 184)}}px ` +
        `minmax(0,${{Number(horizontal.preferred_bar_width_px || 234)}}px) ` +
        `${{Number(horizontal.value_width_px || 106)}}px;column-gap:7px;` +
        `align-items:center;min-height:${{Number(horizontal.row_min_height_px || 32)}}px;` +
        `margin:${{Number(horizontal.row_gap_px || 4) / 2}}px 0;`
      ),
    );
    if (horizontal.wrap_labels) {{
      output = output.replace(
        /white-space:nowrap;overflow:hidden;text-overflow:ellipsis;/g,
        'white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;',
      );
    }}
    output = output.replace(
      /height:(10|12|14)px;background:([^;]+);/g,
      `height:$1px;background:$2;border-radius:${{Number(horizontal.bar_corner_radius_px || 0)}}px;`,
    );
    output = output.replace(
      /(<div[^>]*style="[^"]*display:grid;grid-template-columns:[^"]*"[^>]*>)([\\s\\S]*?)(<\\/div>)/g,
      function(rowMarkup, rowStart, rowBody, rowEnd) {{
        const labelMatch = rowBody.match(/<span[^>]*>([^<]*)<\\/span>/);
        if (!labelMatch) return rowMarkup;
        const visibleRowLabel = String(labelMatch[1] || '').trim();
        if (!visibleRowLabel) return rowMarkup;
        const sanitizedBody = rowBody.replace(
          /\\s+title="([^"]*)"/g,
          function(titleAttribute, titleValue) {{
            return String(titleValue || '').trim() === visibleRowLabel
              ? ''
              : titleAttribute;
          }},
        );
        return rowStart + sanitizedBody + rowEnd;
      }},
    );
    if (horizontal.scroll) {{
      output = output.replace(
        /overflow-x:hidden;overflow-y:auto;/,
        'overflow-x:hidden;overflow-y:visible;',
      );
      wrapperOverflow = (
        'overflow-x:hidden;overflow-y:auto;scrollbar-gutter:stable;' +
        `padding-right:${{Number(horizontal.scroll_right_padding_px || 4)}}px;`
      );
    }}
  }}
  output = output.replace(
    /font-size:(?:11|12|14)px;line-height:(?:14|16|18)px/g,
    `font-size:${{Number(legendType.font_size_px || 12)}}px;line-height:${{Number(legendType.line_height_px || 16)}}px`,
  );
  output = output.replace(
    /<div style="display:flex;([^"]*flex-wrap:wrap;[^"]*)">/g,
    (
      '<div data-role="legend" style="display:flex;$1' +
      `font-size:${{Number(legendType.font_size_px || 12)}}px;` +
      `line-height:${{Number(legendType.line_height_px || 16)}}px;">`
    ),
  );
  if (['pie', 'donut', 'treemap'].includes(contractFamily)) {{
    output = output.replace(
      '<div style="min-width:0;min-height:0;overflow-y:auto;overflow-x:hidden;">',
      (
        '<div data-role="legend" style="min-width:0;min-height:0;' +
        'overflow-y:auto;overflow-x:hidden;' +
        `font-size:${{Number(legendType.font_size_px || 12)}}px;` +
        `line-height:${{Number(legendType.line_height_px || 16)}}px;">`
      ),
    );
  }}
  if (component.kind === 'metric_tile') {{
    const inset = kpi.padding_px || {{}};
    output = output.replace(
      /<div (style="font-size:\\d+(?:\\.\\d+)?px;line-height:\\d+(?:\\.\\d+)?px;font-weight:\\d+;?")>/,
      '<div data-role="kpi-value" $1>',
    );
    output = output.replace(
      /box-sizing:border-box;width:100%;height:100%;padding:[^;]+;background:[^;]+;/,
      (
        'box-sizing:border-box;width:100%;height:100%;padding:0;' +
        'border:0;border-radius:0;outline:none;box-shadow:none;' +
        'background:transparent;'
      ),
    );
    output = (
      `<div data-role="kpi" data-component="${{componentKind}}" ` +
      `data-render-contract="${{__DL_RENDER_CONTRACT.composite_sha256}}" ` +
      `data-tooltip-comparison-mode="${{tooltipComparisonMode}}" ` +
      `data-tooltip-period-source="${{tooltipPeriodSource}}"${{contractAttributes}} ` +
      'style="box-sizing:border-box;width:100%;height:100%;' +
      `padding:${{Number(inset.top || 0)}}px ${{Number(inset.right || 0)}}px ` +
      `${{Number(inset.bottom || 0)}}px ${{Number(inset.left || 0)}}px;` +
      'border:0;border-radius:0;outline:none;box-shadow:none;' +
      `background:transparent;overflow:hidden;">${{output}}</div>`
    );
  }} else {{
    output = (
      `<div data-component="${{componentKind}}" ` +
      `data-render-contract="${{__DL_RENDER_CONTRACT.composite_sha256}}" ` +
      `data-tooltip-comparison-mode="${{tooltipComparisonMode}}" ` +
      `data-tooltip-period-source="${{tooltipPeriodSource}}"${{contractAttributes}} ` +
      'style="box-sizing:border-box;width:100%;height:100%;' +
      'border:0;outline:none;box-shadow:none;background:transparent;' +
      `${{wrapperOverflow}}">${{output}}</div>`
    );
  }}
  return Editor.generateHtml(output);
}}"""


def _strict_tooltip_context(bundle: dict[str, Any]) -> dict[str, str]:
    visual_spec = (
        bundle.get("renderer_visual_spec")
        if isinstance(bundle.get("renderer_visual_spec"), dict)
        else {}
    )
    tooltip = (
        visual_spec.get("tooltip")
        if isinstance(visual_spec.get("tooltip"), dict)
        else {}
    )
    mode = str(tooltip.get("comparison_mode") or "")
    period_source = str(tooltip.get("period_value_source") or "")
    if mode not in {"single_period", "comparison"}:
        raise RenderContractCompileError(
            "strict tooltip contract requires comparison_mode=single_period or comparison"
        )
    if period_source != "normalized":
        raise RenderContractCompileError(
            "strict tooltip contract requires period_value_source=normalized"
        )
    return {
        "tooltip_comparison_mode": mode,
        "tooltip_period_source": period_source,
    }


def _native_contract_preamble(contract: dict[str, Any]) -> str:
    encoded = json.dumps(
        contract,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _contract_marker(contract) + f"\nconst __DL_RENDER_CONTRACT = Object.freeze({encoded});"


def _contract_marker(contract: dict[str, Any]) -> str:
    return (
        "/* resolved-render-contract:"
        + str(contract.get("composite_sha256") or "")
        + f"; compiler:{RENDER_COMPILER_VERSION} */"
    )


def _required_tab(tabs: dict[str, Any], name: str, *, route: str) -> str:
    value = tabs.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RenderContractCompileError(
            f"render-profile route {route!r} requires a non-empty {name}"
        )
    return value


def _tabs_sha256(tabs: dict[str, Any]) -> str:
    canonical = json.dumps(
        tabs,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
