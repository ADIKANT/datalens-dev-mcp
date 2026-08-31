/**
 * Защищённая подготовка модели и рендер. Обычный перенос не требует изменений.
 * Route: editor_advanced. Технические имена параметров и aliases оставлены без перевода.
 */
// Числовые поля проверяются до построения распределения или связи.
// CUSTOMIZE — Необязательная настройка: меняйте значения только внутри этого блока.
const COOKBOOK_CUSTOMIZE = Object.freeze({
  palette: ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'],
  numberFormat: 'decimal1',
  unit: '',
  emptyLabel: "Нет данных",
});

const __DL_TITLE_CONTRACT = Object.freeze({"display_title":"Точечная диаграмма","family":"scatter","hint":"Связь двух числовых показателей.","issues":[],"mode":"embedded_title","mutual_exclusion":{"native_and_runtime_hint":"forbidden","native_and_runtime_title":"forbidden"},"native_metadata":{"enableHint":false,"hideTitle":true,"hint":"Связь двух числовых показателей.","title":"Точечная диаграмма"},"ok":true,"route":"editor_advanced","runtime":{"renders_content_label":false,"renders_hint":true,"renders_title":true},"schema_id":"dashboard_title_contract","sha256":"f10767d53e5b984ac01c1c59d0b1946aa370ed0ecfbfb6bf9a3782abb813b84d"});
function __dlTitleEsc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
}

const __DL_RENDER_CONTRACT = Object.freeze({"adapter_ids":["generic_chart"],"adapters":{"generic_chart":{"allowed_tooltip_owners":["native"],"tokens":{"component":{"direct_labels_preferred":true,"kind":"generic_chart"}}}},"composite_sha256":"3e38cac7aefb53158b46bd58b0e78cd3c596759d42348562f68d27a9e5b18309","core":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"schema_id":"dashboard_composition"},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"owner":"native","period_value_source":"normalized","show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"effective_tokens":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"component":{"direct_labels_preferred":true,"kind":"generic_chart"},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"schema_id":"dashboard_composition"},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"owner":"native","period_value_source":"normalized","show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"family":"scatter","overlay_ids":[],"overrides":{},"profile_id":"standard_dashboard","profile_sha256":"d02f86a0ea31b1d03d87fc734f58d166327ae7bdc0af8e33a29dbc921cf6a35d","registry_sha256":"c068d515bb5cbaa031fc728e6e49bd5ae6ea13b8118190eea18af0b3e85ab7f1","schema_id":"dashboard_render_profiles"});
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

const TEMPLATE_VARIANT = 'scatter';
const numericOrNaN = (value) => value == null || value === '' ? NaN : Number(value);

const rows = normalizeRows('rows').map((row) => ({
  label: String(row.label || ''),
  value: numericOrNaN(row.value),
  x: numericOrNaN(row.x),
  y: numericOrNaN(row.y),
  size: numericOrNaN(row.size),
  min: numericOrNaN(row.min),
  q1: numericOrNaN(row.q1),
  median: numericOrNaN(row.median),
  q3: numericOrNaN(row.q3),
  max: numericOrNaN(row.max),
})).filter((row) => {
  if (TEMPLATE_VARIANT === 'box_plot') {
    return [row.min, row.q1, row.median, row.q3, row.max].every(Number.isFinite)
      && row.min <= row.q1 && row.q1 <= row.median && row.median <= row.q3 && row.q3 <= row.max;
  }
  if (TEMPLATE_VARIANT === 'scatter') return [row.x, row.y].every(Number.isFinite);
  if (TEMPLATE_VARIANT === 'bubble') return [row.x, row.y, row.size].every(Number.isFinite) && row.size > 0;
  return Number.isFinite(row.value);
});
const model = {variant: TEMPLATE_VARIANT, rows, hint: 'Распределение или связь с явными числовыми полями.', theme: themeName(), style: HOUSE_STYLE};

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
      function extent(values, includeZero) {
        const finite = values.filter(Number.isFinite);
        let min = finite.length ? Math.min(...finite) : 0;
        let max = finite.length ? Math.max(...finite) : 1;
        if (includeZero) {
          min = Math.min(0, min);
          max = Math.max(0, max);
        }
        if (min === max) {
          const padding = Math.max(1, Math.abs(min) * 0.05);
          min -= padding;
          max += padding;
        }
        return {min, max, span: Math.max(Number.EPSILON, max - min)};
      }
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 320;
      const compact = width < 530 || height < 260;
      const margin = {l: compact ? 30 : 42, r: width < 720 ? 10 : 16, t: 22, b: 34};
      function renderHistogram() {
        const band = (width - margin.l - margin.r) / Math.max(1, data.rows.length);
        const domain = extent(data.rows.map((row) => row.value), true);
        const scale = (value) => margin.t + (domain.max - value) / domain.span * (height - margin.t - margin.b);
        const baseline = scale(0);
        return data.rows.map((row, index) => {
          const valueY = scale(row.value);
          const barHeight = Math.abs(baseline - valueY);
          const x = margin.l + index * band + 3;
          const y = Math.min(baseline, valueY);
          const color = row.value < 0 ? (style.colors.negative || style.colors.critical) : style.colors.primary;
          const valueLabelY = row.value < 0 ? Math.min(height - margin.b - 2, valueY + 13) : Math.max(margin.t + 10, valueY - 5);
          return `<rect x="${x}" y="${y}" width="${Math.max(4, band - 6)}" height="${barHeight}" fill="${color}"/><text x="${x + band / 2}" y="${height - 10}" text-anchor="middle" font-size="11" fill="${style.colors.textMuted}">${esc(row.label)}</text><text x="${x + band / 2}" y="${valueLabelY}" text-anchor="middle" font-size="10" font-weight="800" fill="${style.colors.text}">${fmt(row.value)}</text>`;
        }).join('');
      }
      function renderBoxPlot() {
        const groups = data.rows;
        const band = (width - margin.l - margin.r) / Math.max(1, groups.length);
        const domain = extent(groups.flatMap((row) => [row.min, row.max]), true);
        const scale = (value) => margin.t + (domain.max - value) / domain.span * (height - margin.t - margin.b);
        return groups.map((row, index) => {
          const center = margin.l + index * band + band / 2;
          const boxHalf = Math.max(3, Math.min(compact ? 12 : 20, band * 0.28));
          const low = scale(row.min);
          const q1 = scale(row.q1);
          const med = scale(row.median);
          const q3 = scale(row.q3);
          const high = scale(row.max);
          return `<line x1="${center}" y1="${high}" x2="${center}" y2="${low}" stroke="${style.colors.textMuted}"/><line x1="${center - boxHalf * 0.6}" y1="${high}" x2="${center + boxHalf * 0.6}" y2="${high}" stroke="${style.colors.textMuted}"/><line x1="${center - boxHalf * 0.6}" y1="${low}" x2="${center + boxHalf * 0.6}" y2="${low}" stroke="${style.colors.textMuted}"/><rect x="${center - boxHalf}" y="${q3}" width="${boxHalf * 2}" height="${Math.max(2, q1 - q3)}" fill="${style.colors.surfaceMuted}" stroke="${style.colors.primary}"/><line x1="${center - boxHalf}" y1="${med}" x2="${center + boxHalf}" y2="${med}" stroke="${style.colors.primary}" stroke-width="2"/><text x="${center}" y="${height - 10}" text-anchor="middle" font-size="${compact ? 10 : 11}" fill="${style.colors.textMuted}">${esc(row.label)}</text>`;
        }).join('');
      }
      function renderScatter(includeBubble) {
        const xDomain = extent(data.rows.map((row) => row.x), false);
        const yDomain = extent(data.rows.map((row) => row.y), false);
        const maxSize = Math.max(1, ...data.rows.map((row) => row.size).filter(Number.isFinite));
        const radiusLimit = includeBubble ? (compact ? 16 : 24) : (compact ? 4 : 5);
        const radiusInset = includeBubble ? radiusLimit : 0;
        const plotWidth = Math.max(0, width - margin.l - margin.r - radiusInset * 2);
        const plotHeight = Math.max(0, height - margin.t - margin.b - radiusInset * 2);
        return data.rows.map((row, index) => {
          const cx = margin.l + radiusInset + (row.x - xDomain.min) / xDomain.span * plotWidth;
          const cy = margin.t + radiusInset + (yDomain.max - row.y) / yDomain.span * plotHeight;
          const radius = includeBubble ? Math.max(4, Math.min(radiusLimit, row.size / maxSize * radiusLimit)) : radiusLimit;
          return `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="${style.colors.category[index % style.colors.category.length]}" opacity="0.72"><title>${esc(row.label)} ${fmt(row.x)} / ${fmt(row.y)}</title></circle>`;
        }).join('');
      }
      let marks = renderHistogram();
      if (data.variant === 'box_plot') marks = renderBoxPlot();
      if (data.variant === 'scatter') marks = renderScatter(false);
      if (data.variant === 'bubble') marks = renderScatter(true);
      return __dlGenerateProfileHtml(options, `<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 6 : 12}px ${compact ? 6 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;"><svg data-role="plot-area" data-inset-top="${margin.t}" data-inset-right="${margin.r}" data-inset-bottom="${margin.b}" width="100%" height="100%" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line x1="${margin.l}" y1="${height - margin.b}" x2="${width - margin.r}" y2="${height - margin.b}" stroke="${style.colors.border}"/><line x1="${margin.l}" y1="${margin.t}" x2="${margin.l}" y2="${height - margin.b}" stroke="${style.colors.border}"/>${marks}</svg></div>`);
    },
  }),
};
