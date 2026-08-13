/**
 * Защищённая подготовка модели и рендер. Обычный перенос не требует изменений.
 * Route: editor_advanced. Технические имена параметров и aliases оставлены без перевода.
 */
// Части должны быть неотрицательными и образовывать положительный итог.
// CUSTOMIZE — Необязательная настройка: меняйте значения только внутри этого блока.
const COOKBOOK_CUSTOMIZE = Object.freeze({
  palette: ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'],
  numberFormat: 'decimal1',
  unit: '',
  emptyLabel: "Нет данных",
});

const __DL_TITLE_CONTRACT = Object.freeze({"display_title":"Кольцевая диаграмма","family":"donut","hint":"Состав целого с итогом в центре.","issues":[],"mode":"embedded_title","mutual_exclusion":{"native_and_runtime_hint":"forbidden","native_and_runtime_title":"forbidden"},"native_metadata":{"enableHint":false,"hideTitle":true,"hint":"Состав целого с итогом в центре.","title":"Кольцевая диаграмма"},"ok":true,"route":"editor_advanced","runtime":{"renders_content_label":false,"renders_hint":true,"renders_title":true},"schema_id":"dashboard_title_contract","sha256":"d4e42513fa802b5d05475ab2ac0603eac284d7afbbb33bddd832ad8ba7708b6f"});
function __dlTitleEsc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
}

const __DL_RENDER_CONTRACT = Object.freeze({"adapter_ids":["generic_chart"],"adapters":{"generic_chart":{"allowed_tooltip_owners":["native"],"tokens":{"component":{"direct_labels_preferred":true,"kind":"generic_chart"}}}},"composite_sha256":"f71bce1291cbeaaf26a45a69fd32135841a03d4127882a1a23ebf716a914b667","core":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"placement":"below_selectors","required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"kpi_height_units":{"compact":6,"sparkline":8},"kpi_max_per_row":3,"kpi_width_units":12,"schema_id":"dashboard_composition","selector_height_units":{"one_row":2,"two_rows":3},"selector_row_width_percent":94},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","surface":{"background":"transparent","border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"},"value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"native_height_units":{"comparison_context_maximum":3,"comparison_context_minimum":1,"kpi_compact_default":6,"kpi_creation_default":8,"selector_creation_default":2,"selector_two_row_default":3,"title_creation_default":2},"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"blank_multiselect_semantics":"all","control_max_width_percent":94,"label_placement":"left","period_first_if_present":true,"row_height_px":44,"row_target_width_percent":94,"row_width_tolerance_percent":0,"single_row":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"max_width_px":340,"owner":"native","padding_px":{"horizontal":12,"vertical":10},"period_value_source":"normalized","redundant_row_title":false,"show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true,"surface":{"border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"}},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"legend":{"compact":{"font_size_px":12,"line_height_px":16},"default":{"font_size_px":12,"line_height_px":16},"readable":{"font_size_px":14,"line_height_px":18}},"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"effective_tokens":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"placement":"below_selectors","required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"component":{"direct_labels_preferred":true,"kind":"generic_chart"},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"kpi_height_units":{"compact":6,"sparkline":8},"kpi_max_per_row":3,"kpi_width_units":12,"schema_id":"dashboard_composition","selector_height_units":{"one_row":2,"two_rows":3},"selector_row_width_percent":94},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","surface":{"background":"transparent","border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"},"value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"native_height_units":{"comparison_context_maximum":3,"comparison_context_minimum":1,"kpi_compact_default":6,"kpi_creation_default":8,"selector_creation_default":2,"selector_two_row_default":3,"title_creation_default":2},"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"blank_multiselect_semantics":"all","control_max_width_percent":94,"label_placement":"left","period_first_if_present":true,"row_height_px":44,"row_target_width_percent":94,"row_width_tolerance_percent":0,"single_row":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"max_width_px":340,"owner":"native","padding_px":{"horizontal":12,"vertical":10},"period_value_source":"normalized","redundant_row_title":false,"show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true,"surface":{"border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"}},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"legend":{"active":{"font_size_px":12,"line_height_px":16},"active_token":"legend.default","compact":{"font_size_px":12,"line_height_px":16},"default":{"font_size_px":12,"line_height_px":16},"readable":{"font_size_px":14,"line_height_px":18}},"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"family":"donut","overrides":{},"profile_id":"standard_dashboard","profile_sha256":"70fb8647e0ed8fe5f6f8dbab1f4aceda07b780e73de1a1c9cee55cb07ce41135","registry_sha256":"39cdac0e2e5eedf0dedda2631d127344f3e471cac311851293f48d5c021e1de8","schema_id":"dashboard_render_profiles"});
const __DL_RENDER_CONTEXT = Object.freeze({"tooltip_comparison_mode":"single_period","tooltip_period_source":"normalized"});
function __dlGenerateProfileHtml(options, html) {
  const contract = __DL_RENDER_CONTRACT.effective_tokens || {};
  const typography = contract.typography || {};
  const shell = contract.shell || {};
  const density = contract.density || {};
  const semantic = contract.semantic_colors || {};
  const component = contract.component || {};
  const horizontal = contract.horizontal_rank || {};
  const plotArea = contract.plot_area || {};
  const seriesVisibility = contract.series_visibility || {};
  const componentKind = String(component.kind || 'generic_chart')
    .replace(/[^a-z0-9_-]/gi, '') || 'generic_chart';
  const contractFamily = String(__DL_RENDER_CONTRACT.family || '');
  const tooltipComparisonMode = String(__DL_RENDER_CONTEXT.tooltip_comparison_mode || '');
  const tooltipPeriodSource = String(__DL_RENDER_CONTEXT.tooltip_period_source || '');
  const width = Number(options && options.width);
  const compact = density.mode === 'compact' ||
    (density.mode !== 'comfortable' && Number.isFinite(width) &&
      width < Number(density.compact_below_width_px || 720));
  const padding = (shell.padding_px || {})[compact ? 'compact' : 'normal'] || {};
  const bodyType = typography.body || {};
  const legendType = (typography.legend || {}).active || {};
  const kpi = contract.kpi || {};
  const kpiValue = (kpi.value_typography || {})[compact ? 'compact' : 'normal'] || {};
  const fontFamily = (typography.font_family || ['Inter', 'Arial', 'sans-serif']).join(',');
  const activeSeriesFamilies = ['line_chart', 'multiline_chart', 'area_completion', 'combo_time_series_combo'];
  const coordinatePlotFamilies = activeSeriesFamilies.concat(
    ['vertical_bar_time_bucket', 'histogram', 'box_plot', 'scatter', 'bubble'],
  );
  const seriesPolicyEnabled = activeSeriesFamilies.includes(contractFamily) &&
    seriesVisibility.legend === 'active_series_only' &&
    seriesVisibility.marks === 'active_series_only';
  const plotPolicyEnabled = coordinatePlotFamilies.includes(contractFamily);
  const rightInset = ((plotArea.inset_px || {}).right || {})[compact ? 'compact' : 'normal'];
  const contractAttributes = (
    (seriesPolicyEnabled ? ' data-series-policy="active_series_only"' : '') +
    (plotPolicyEnabled
      ? (
        ' data-plot-area-policy="contract_insets"' +
        ` data-plot-inset-top="${Number((plotArea.inset_px || {}).top || 0)}"` +
        ` data-plot-inset-right="${Number(rightInset || 0)}"` +
        ` data-plot-inset-bottom="${Number((plotArea.inset_px || {}).bottom || 0)}"`
      )
      : '')
  );
  let output = String(html == null ? '' : html);
  let wrapperOverflow = '';
  output = output.replace(/font-family:Inter,Arial,sans-serif/g, `font-family:${fontFamily}`);
  output = output.replace(/font-size:(?:10|11|12)px/g, `font-size:${bodyType.font_size_px || 12}px`);
  output = output.replace(/line-height:1\.25/g, `line-height:${bodyType.line_height_px || 16}px`);
  output = output.replace(
    /(box-sizing:border-box;width:100%;height:100%;)padding:[^;]+;/,
    `$1padding:${Number(padding.vertical || 0)}px ${Number(padding.horizontal || 0)}px;`,
  );
  output = output.replace(
    /font-size:\d+(?:\.\d+)?px;line-height:1\.05;font-weight:850/g,
    (
      `font-size:${Number(kpiValue.font_size_px || 34)}px;` +
      `line-height:${Number(kpiValue.line_height_px || 38)}px;` +
      `font-weight:${Number((kpi.value_typography || {}).font_weight || 750)}`
    ),
  );
  output = output.replace(/var\(--g-color-text-positive,[^)]+\)/g, semantic.success || '#6CBF84');
  output = output.replace(/var\(--g-color-text-danger,[^)]+\)/g, semantic.failure || '#E57373');
  output = output.replace(/#2B75E2/gi, semantic.primary || '#2B75E2');
  if (component.kind === 'horizontal_rank') {
    output = output.replace(
      /grid-template-columns:[^;]+;gap:\d+(?:\.\d+)?px;align-items:center;margin:[^;]+;/g,
      (
        `grid-template-columns:${Number(horizontal.label_width_px || 184)}px ` +
        `minmax(0,${Number(horizontal.preferred_bar_width_px || 234)}px) ` +
        `${Number(horizontal.value_width_px || 106)}px;column-gap:7px;` +
        `align-items:center;min-height:${Number(horizontal.row_min_height_px || 32)}px;` +
        `margin:${Number(horizontal.row_gap_px || 4) / 2}px 0;`
      ),
    );
    if (horizontal.wrap_labels) {
      output = output.replace(
        /white-space:nowrap;overflow:hidden;text-overflow:ellipsis;/g,
        'white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;',
      );
    }
    output = output.replace(
      /height:(10|12|14)px;background:([^;]+);/g,
      `height:$1px;background:$2;border-radius:${Number(horizontal.bar_corner_radius_px || 0)}px;`,
    );
    output = output.replace(
      /(<div[^>]*style="[^"]*display:grid;grid-template-columns:[^"]*"[^>]*>)([\s\S]*?)(<\/div>)/g,
      function(rowMarkup, rowStart, rowBody, rowEnd) {
        const labelMatch = rowBody.match(/<span[^>]*>([^<]*)<\/span>/);
        if (!labelMatch) return rowMarkup;
        const visibleRowLabel = String(labelMatch[1] || '').trim();
        if (!visibleRowLabel) return rowMarkup;
        const sanitizedBody = rowBody.replace(
          /\s+title="([^"]*)"/g,
          function(titleAttribute, titleValue) {
            return String(titleValue || '').trim() === visibleRowLabel
              ? ''
              : titleAttribute;
          },
        );
        return rowStart + sanitizedBody + rowEnd;
      },
    );
    if (horizontal.scroll) {
      output = output.replace(
        /overflow-x:hidden;overflow-y:auto;/,
        'overflow-x:hidden;overflow-y:visible;',
      );
      wrapperOverflow = (
        'overflow-x:hidden;overflow-y:auto;scrollbar-gutter:stable;' +
        `padding-right:${Number(horizontal.scroll_right_padding_px || 4)}px;`
      );
    }
  }
  output = output.replace(
    /font-size:(?:11|12|14)px;line-height:(?:14|16|18)px/g,
    `font-size:${Number(legendType.font_size_px || 12)}px;line-height:${Number(legendType.line_height_px || 16)}px`,
  );
  output = output.replace(
    /<div style="display:flex;([^"]*flex-wrap:wrap;[^"]*)">/g,
    (
      '<div data-role="legend" style="display:flex;$1' +
      `font-size:${Number(legendType.font_size_px || 12)}px;` +
      `line-height:${Number(legendType.line_height_px || 16)}px;">`
    ),
  );
  if (['pie', 'donut', 'treemap'].includes(contractFamily)) {
    output = output.replace(
      '<div style="min-width:0;min-height:0;overflow-y:auto;overflow-x:hidden;">',
      (
        '<div data-role="legend" style="min-width:0;min-height:0;' +
        'overflow-y:auto;overflow-x:hidden;' +
        `font-size:${Number(legendType.font_size_px || 12)}px;` +
        `line-height:${Number(legendType.line_height_px || 16)}px;">`
      ),
    );
  }
  if (component.kind === 'metric_tile') {
    const inset = kpi.padding_px || {};
    output = output.replace(
      /<div (style="font-size:\d+(?:\.\d+)?px;line-height:\d+(?:\.\d+)?px;font-weight:\d+;?")>/,
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
      `<div data-role="kpi" data-component="${componentKind}" ` +
      `data-render-contract="${__DL_RENDER_CONTRACT.composite_sha256}" ` +
      `data-tooltip-comparison-mode="${tooltipComparisonMode}" ` +
      `data-tooltip-period-source="${tooltipPeriodSource}"${contractAttributes} ` +
      'style="box-sizing:border-box;width:100%;height:100%;' +
      `padding:${Number(inset.top || 0)}px ${Number(inset.right || 0)}px ` +
      `${Number(inset.bottom || 0)}px ${Number(inset.left || 0)}px;` +
      'border:0;border-radius:0;outline:none;box-shadow:none;' +
      `background:transparent;overflow:hidden;">${output}</div>`
    );
  } else {
    output = (
      `<div data-component="${componentKind}" ` +
      `data-render-contract="${__DL_RENDER_CONTRACT.composite_sha256}" ` +
      `data-tooltip-comparison-mode="${tooltipComparisonMode}" ` +
      `data-tooltip-period-source="${tooltipPeriodSource}"${contractAttributes} ` +
      'style="box-sizing:border-box;width:100%;height:100%;' +
      'border:0;outline:none;box-shadow:none;background:transparent;' +
      `${wrapperOverflow}">${output}</div>`
    );
  }
  const titleMode = String(__DL_TITLE_CONTRACT.mode || '');
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
}

const STYLE_GUIDE = {
  light: {
    colors: {
      surface: 'var(--g-color-base-background, #FFFFFF)',
      surfaceMuted: 'var(--g-color-base-neutral-light, #F8FAFC)',
      border: 'var(--g-color-line-generic, #E5E7EB)',
      gridLine: 'var(--g-color-line-generic, #E5E7EB)',
      text: 'var(--g-color-text-primary, #111827)',
      textMuted: 'var(--g-color-text-secondary, #667085)',
      textSubtle: 'var(--g-color-text-hint, #98A2B3)',
      tooltipBackground: 'var(--g-color-base-float, #FFFFFF)',
      tooltipText: 'var(--g-color-text-primary, #111827)',
      primary: '#2B75E2',
      accent: '#2B75E2',
      ok: 'var(--g-color-text-positive, #237A57)',
      warning: 'var(--g-color-text-warning, #B7791F)',
      critical: 'var(--g-color-text-danger, #B42318)',
      category: ['#2B75E2', '#6A8FCA', '#8BB7A2', '#A8B0BD', '#D4A95F', '#B58CCF'],
      sequential: ['#D7E3F6', '#AFC7ED', '#7AA7F0', '#2B75E2'],
      tableHeader: 'var(--g-color-base-neutral-light, transparent)',
      tableRow: 'var(--g-color-base-background, transparent)',
      selectorLabel: 'var(--g-color-text-secondary, #667085)',
    },
    chart_categorical_palette: ['#2B75E2', '#6A8FCA', '#8BB7A2', '#A8B0BD', '#D4A95F', '#B58CCF'],
    table_header_background: 'var(--g-color-base-neutral-light, transparent)',
  },
  dark: {
    colors: {
      surface: 'var(--g-color-base-background, #111827)',
      surfaceMuted: 'var(--g-color-base-neutral-light, #1F2937)',
      border: 'var(--g-color-line-generic, #374151)',
      gridLine: 'var(--g-color-line-generic, #374151)',
      text: 'var(--g-color-text-primary, #F9FAFB)',
      textMuted: 'var(--g-color-text-secondary, #D1D5DB)',
      textSubtle: 'var(--g-color-text-hint, #9CA3AF)',
      tooltipBackground: 'var(--g-color-base-float, #1F2937)',
      tooltipText: 'var(--g-color-text-primary, #F9FAFB)',
      primary: '#79A8F7',
      accent: '#79A8F7',
      ok: 'var(--g-color-text-positive, #5BD18B)',
      warning: 'var(--g-color-text-warning, #F2B84B)',
      critical: 'var(--g-color-text-danger, #F87171)',
      category: ['#79A8F7', '#9FB9E5', '#A8CDB9', '#B7BEC8', '#E0C47C', '#C9A6DF'],
      sequential: ['#1F2937', '#385A8D', '#5D85C9', '#79A8F7'],
      tableHeader: 'var(--g-color-base-neutral-light, transparent)',
      tableRow: 'var(--g-color-base-background, transparent)',
      selectorLabel: 'var(--g-color-text-secondary, #D1D5DB)',
    },
    chart_categorical_palette: ['#79A8F7', '#9FB9E5', '#A8CDB9', '#B7BEC8', '#E0C47C', '#C9A6DF'],
    table_header_background: 'var(--g-color-base-neutral-light, transparent)',
  },
};

const HOUSE_STYLE = {
  colors: STYLE_GUIDE.light.colors,
  themes: STYLE_GUIDE,
  radius: 6,
  spacing: 12,
};

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatCompact(value) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return 'Нет данных';
  const number = Number(value);
  const abs = Math.abs(number);
  if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
  if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
  return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
}

function formatDateLabel(value) {
  const text = String(value == null ? '' : value).trim();
  const daily = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$/);
  if (daily) return `${daily[3]}.${daily[2]}.${daily[1].slice(2)}`;
  const monthly = text.match(/^(\d{4})-(\d{2})$/);
  if (monthly) return `${monthly[2]}.${monthly[1].slice(2)}`;
  return text || 'Нет данных';
}

function niceAxis(maxValue, tickCount) {
  const maximum = Number(maxValue);
  const count = Math.max(2, Math.round(Number(tickCount) || 4));
  if (!Number.isFinite(maximum) || maximum <= 0) return {max: 1, step: 1, ticks: [0, 1]};
  const rough = maximum / count;
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const fraction = rough / power;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  const step = niceFraction * power;
  const niceMax = Math.ceil(maximum / step) * step;
  const ticks = [];
  for (let value = 0; value <= niceMax + step / 2; value += step) ticks.push(Number(value.toPrecision(12)));
  return {max: niceMax, step, ticks};
}

function safeUri(value, options) {
  const policy = options || {};
  const allowHttp = policy.allowHttp === true;
  const allowRelative = policy.allowRelative !== false;
  const text = String(value == null ? '' : value)
    .replace(/&#(x[0-9a-f]+|\d+);?/gi, (_match, code) => {
      const point = code[0].toLowerCase() === 'x' ? parseInt(code.slice(1), 16) : parseInt(code, 10);
      return Number.isInteger(point) && point >= 0 && point <= 0x10FFFF ? String.fromCodePoint(point) : '\uFFFD';
    })
    .replace(/&colon;/gi, ':')
    .replace(/&tab;/gi, '\t')
    .replace(/&newline;/gi, '\n')
    .replace(/&amp;/gi, '&')
    .trim();
  if (!text || /[\u0000-\u001F\u007F\s]/.test(text) || text.indexOf(String.fromCharCode(92)) !== -1 || text.startsWith('//')) return '';
  if (/^https?:/i.test(text)) {
    try {
      const parsed = new URL(text);
      if (!parsed.hostname || parsed.username || parsed.password) return '';
      if (parsed.protocol === 'https:') return text;
      if (parsed.protocol === 'http:') return allowHttp ? text : '';
      return '';
    } catch (_error) {
      return '';
    }
  }
  if (text.includes('://')) return '';
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(text)) return '';
  return allowRelative ? text : '';
}

function normalizeRows(sourceName) {
  const loaded = Editor.getLoadedData() || {};
  const source = loaded[sourceName] || loaded.rows || [];
  if (!Array.isArray(source)) return [];
  const metadata = source.find((item) => item && item.event === 'metadata');
  const names = metadata?.data?.names || [];
  const eventRows = source.filter((item) => item && item.event === 'row' && Array.isArray(item.data));
  if (names.length && eventRows.length) {
    return eventRows.map((item) => Object.fromEntries(item.data.map((value, index) => [names[index] || `column_${index + 1}`, value])));
  }
  return source;
}

function themeName() {
  const params = Editor.getParams ? Editor.getParams() : {};
  const requested = String(params.theme?.[0] || 'light').toLowerCase();
  return requested === 'dark' ? 'dark' : 'light';
}

const TEMPLATE_VARIANT = 'donut';

const sourceRows = normalizeRows('rows');
const parsedRows = sourceRows.map((row) => ({
  label: String(row.label || ''),
  value: row.value == null || row.value === '' ? NaN : Number(row.value),
})).slice(0, 8);
const invalidReason = sourceRows.length > 8
  ? 'слишком_много_категорий'
  : parsedRows.some((row) => !row.label || !Number.isFinite(row.value) || row.value < 0)
    ? 'некорректная_или_отрицательная_часть'
    : !(parsedRows.reduce((sum, row) => sum + row.value, 0) > 0)
      ? 'нужен_положительный_итог'
      : '';
const rows = parsedRows.map((row) => ({...row, value: Number.isFinite(row.value) ? row.value : 0}));
const total = rows.reduce((sum, row) => sum + row.value, 0);
const model = {variant: TEMPLATE_VARIANT, rows, total, invalidReason, hint: 'Небольшой состав целого; для рейтинга используйте столбцы.', theme: themeName(), style: HOUSE_STYLE};

module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      function esc(value) {
        return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function fmt(value) {
        const number = Number(value || 0);
        const abs = Math.abs(number);
        if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
        if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
        return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
      }
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = width < 530 || height < 260;
      if (data.invalidReason) {
        return __dlGenerateProfileHtml(options, `<div style="box-sizing:border-box;width:100%;height:100%;padding:12px;background:${style.colors.surface};color:${style.colors.textMuted};font-family:Inter,Arial,sans-serif;">N/A · ${esc(data.invalidReason)}</div>`);
      }
      function renderPieLike(isDonut) {
        let offset = 0;
        const strokeWidth = isDonut ? 30 : 74;
        const inner = isDonut ? `<circle cx="110" cy="110" r="52" fill="${style.colors.surface}"/><text x="110" y="112" text-anchor="middle" font-size="24" font-weight="850" fill="${style.colors.text}">${fmt(data.total)}</text>` : '';
        const slices = data.rows.map((row, index) => {
          const share = data.total ? row.value / data.total * 100 : 0;
          const color = style.colors.category[index % style.colors.category.length];
          const segment = `<circle r="72" cx="110" cy="110" pathLength="100" fill="transparent" stroke="${color}" stroke-width="${strokeWidth}" stroke-dasharray="${share} ${100 - share}" stroke-dashoffset="${-offset}"></circle>`;
          offset += share;
          return segment;
        }).join('');
        return `<svg viewBox="0 0 220 220" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">${slices}${inner}</svg>`;
      }
      function renderTreemap() {
        let xOffset = 0;
        return `<svg viewBox="0 0 320 180" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">${data.rows.map((row, index) => {
          const width = data.total ? row.value / data.total * 320 : 0;
          const color = style.colors.category[index % style.colors.category.length];
          const label = width >= 36 ? `<text x="${xOffset + 6}" y="${24 + index % 4 * 18}" font-size="12" font-weight="800" fill="${style.colors.surface}">${esc(row.label)} ${Math.round(row.value / data.total * 100)}%</text>` : '';
          const rect = `<rect x="${xOffset}" y="0" width="${width}" height="180" fill="${color}"/>${label}`;
          xOffset += width;
          return rect;
        }).join('')}</svg>`;
      }
      const chart = data.variant === 'treemap' ? renderTreemap() : renderPieLike(data.variant === 'donut');
      const legend = data.rows.map((row, index) => `<span style="display:flex;align-items:center;gap:6px;margin:5px 0;font-size:12px;color:${style.colors.textMuted};"><i style="width:10px;height:10px;background:${style.colors.category[index % style.colors.category.length]};display:inline-block;"></i>${esc(row.label)} ${data.total ? Math.round(row.value / data.total * 100) : 0}%</span>`).join('');
      const layout = compact
        ? 'grid-template-columns:1fr;grid-template-rows:minmax(0,2fr) minmax(0,1fr);'
        : 'grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-rows:1fr;';
      return __dlGenerateProfileHtml(options, `<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 8 : 12}px ${compact ? 8 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;"><div style="display:grid;${layout}width:100%;height:100%;align-items:stretch;gap:${compact ? 6 : 16}px;"><div style="min-width:0;min-height:0;">${chart}</div><div style="min-width:0;min-height:0;overflow-y:auto;overflow-x:hidden;">${legend}</div></div></div>`);
    },
  }),
};
