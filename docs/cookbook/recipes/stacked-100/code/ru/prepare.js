/**
 * Защищённая подготовка модели и рендер. Обычный перенос не требует изменений.
 * Route: editor_advanced. Технические имена параметров и aliases оставлены без перевода.
 */
// Prepare нормализует поля и оставляет пользовательские изменения в Meta и Sources.
// CUSTOMIZE — Необязательная настройка: меняйте значения только внутри этого блока.
const COOKBOOK_CUSTOMIZE = Object.freeze({
  palette: ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'],
  numberFormat: 'decimal1',
  unit: '',
  emptyLabel: "Нет данных",
});

const __DL_TITLE_CONTRACT = Object.freeze({"display_title":"Столбцы с нормировкой до 100%","family":"stacked_100","hint":"Состав целого в процентах.","issues":[],"mode":"embedded_title","mutual_exclusion":{"native_and_runtime_hint":"forbidden","native_and_runtime_title":"forbidden"},"native_metadata":{"enableHint":false,"hideTitle":true,"hint":"Состав целого в процентах.","title":"Столбцы с нормировкой до 100%"},"ok":true,"route":"editor_advanced","runtime":{"renders_content_label":false,"renders_hint":true,"renders_title":true},"schema_id":"dashboard_title_contract","sha256":"5d008e618c6cb3b2662e9a2756ecc6d18ecc451972bf3ecf42569b32cf171394"});
function __dlTitleEsc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
}

const __DL_RENDER_CONTRACT = Object.freeze({"adapter_ids":["horizontal_rank"],"adapters":{"horizontal_rank":{"allowed_tooltip_owners":["native"],"tokens":{"component":{"kind":"horizontal_rank"},"horizontal_rank":{"bar_corner_radius_px":0.75,"label_width_px":184,"preferred_bar_width_px":234,"row_gap_px":4,"row_min_height_px":32,"scroll":false,"stable_secondary_sort":true,"value_width_px":106,"wrap_labels":true}}}},"composite_sha256":"c40cd134e46801ce58d228122e2c2bec4abc0243419bc07179c4b9d82609d72a","core":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"schema_id":"dashboard_composition"},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"owner":"native","period_value_source":"normalized","show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"effective_tokens":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"component":{"kind":"horizontal_rank"},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"schema_id":"dashboard_composition"},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"horizontal_rank":{"bar_corner_radius_px":0.75,"label_width_px":184,"preferred_bar_width_px":234,"row_gap_px":4,"row_min_height_px":32,"scroll":false,"stable_secondary_sort":true,"value_width_px":106,"wrap_labels":true},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"owner":"native","period_value_source":"normalized","show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"family":"stacked_100","overlay_ids":[],"overrides":{},"profile_id":"standard_dashboard","profile_sha256":"d02f86a0ea31b1d03d87fc734f58d166327ae7bdc0af8e33a29dbc921cf6a35d","registry_sha256":"c068d515bb5cbaa031fc728e6e49bd5ae6ea13b8118190eea18af0b3e85ab7f1","schema_id":"dashboard_render_profiles"});
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

const TEMPLATE_VARIANT = 'stacked_100';
const numericOrNaN = (value) => value == null || value === '' ? NaN : Number(value);

const normalizedRows = normalizeRows('rows')
  .map((row) => ({
    label: String(row.label || ''),
    group: String(row.group || 'Все'),
    value: numericOrNaN(row.value),
    target: numericOrNaN(row.target),
  }))
  .filter((row) => Number.isFinite(row.value));
const rows = (TEMPLATE_VARIANT === 'waterfall' || TEMPLATE_VARIANT === 'heatmap'
  ? normalizedRows
  : normalizedRows.slice().sort((left, right) => right.value - left.value)
).slice(0, 18);
const hint = TEMPLATE_VARIANT === 'waterfall'
  ? 'Последовательные изменения с начальной и конечной позициями.'
  : 'Отсортированное сравнение с нулевой осью и прямыми подписями.';
const model = {variant: TEMPLATE_VARIANT, rows, hint, theme: themeName(), style: HOUSE_STYLE};

module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      function esc(value) {
        return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function fmt(value) {
        if (value == null || value === '' || !Number.isFinite(Number(value))) return 'Нет данных';
        const number = Number(value);
        const abs = Math.abs(number);
        if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
        if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
        return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
      }
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const viewportWidth = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const viewportHeight = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = viewportWidth < 480;
      const dense = viewportHeight < 260;
      const medium = viewportWidth < 700;
      const labelColumn = compact ? 'minmax(0,36%)' : medium ? 'minmax(0,38%)' : 'minmax(0,220px)';
      const valueColumn = compact ? '46px' : '58px';
      const gap = compact ? 6 : 10;
      const numericValues = data.rows.flatMap((row) => [row.value, row.target]).filter(Number.isFinite);
      const domainMin = Math.min(0, ...numericValues);
      const domainMax = Math.max(0, ...numericValues);
      const domainSpan = Math.max(1, domainMax - domainMin);
      const zeroPercent = (0 - domainMin) / domainSpan * 100;
      const maxAbs = Math.max(1, ...numericValues.map(Math.abs));
      function signedBar(value, color, height) {
        const valuePercent = (value - domainMin) / domainSpan * 100;
        const left = Math.min(zeroPercent, valuePercent);
        const width = Math.abs(valuePercent - zeroPercent);
        return `<i style="position:absolute;display:block;left:${left}%;height:${height}px;width:${width}%;background:${color};"></i>`;
      }
      function renderHorizontalRows() {
        return data.rows.map((row, index) => {
          const color = row.value < 0
            ? (style.colors.negative || style.colors.critical)
            : style.colors.category[index % style.colors.category.length];
          return `<div style="display:grid;grid-template-columns:${labelColumn} minmax(0,1fr) ${valueColumn};gap:${gap}px;align-items:center;margin:${dense ? 4 : compact ? 6 : 8}px 0;font-size:${compact ? 11 : 12}px;line-height:1.25;color:${style.colors.text};"><span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row.label)}</span><span style="position:relative;height:12px;background:${style.colors.surfaceMuted};"><em style="position:absolute;left:${zeroPercent}%;height:12px;border-left:1px solid ${style.colors.border};"></em>${signedBar(row.value, color, 12)}</span><b style="text-align:right;">${fmt(row.value)}</b></div>`;
        }).join('');
      }
      function renderGroupedBar() {
        const groups = [...new Set(data.rows.map((row) => row.group))];
        return groups.map((group) => `<div style="margin:8px 0 12px;"><b style="font-size:11px;color:${style.colors.textMuted};">${esc(group)}</b>${data.rows.filter((row) => row.group === group).map((row, index) => {
          const color = row.value < 0
            ? (style.colors.negative || style.colors.critical)
            : style.colors.category[index % style.colors.category.length];
          return `<div style="display:grid;grid-template-columns:${labelColumn} minmax(0,1fr) ${valueColumn};gap:${gap}px;align-items:center;margin:${dense ? 3 : 4}px 0;font-size:${compact ? 11 : 12}px;line-height:1.25;color:${style.colors.text};"><span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row.label)}</span><span style="position:relative;height:10px;background:${style.colors.surfaceMuted};"><em style="position:absolute;left:${zeroPercent}%;height:10px;border-left:1px solid ${style.colors.border};"></em>${signedBar(row.value, color, 10)}</span><b style="text-align:right;">${fmt(row.value)}</b></div>`;
        }).join('')}</div>`).join('');
      }
      function renderStacked100() {
        if (data.rows.some((row) => row.value < 0)) {
          return `<div style="color:${style.colors.textMuted};font-size:12px;">N/A · для 100% stacked нужны неотрицательные значения</div>`;
        }
        const total = data.rows.reduce((sum, row) => sum + row.value, 0);
        if (!(total > 0)) {
          return `<div style="color:${style.colors.textMuted};font-size:12px;">N/A · нужен положительный итог</div>`;
        }
        const segments = data.rows.map((row, index) => {
          const share = row.value / total * 100;
          return `<i title="${esc(row.label)} ${fmt(row.value)}" style="display:block;width:${share}%;background:${style.colors.category[index % style.colors.category.length]};"></i>`;
        }).join('');
        const legend = data.rows.map((row, index) => `<span style="font-size:12px;color:${style.colors.textMuted};"><i style="display:inline-block;width:9px;height:9px;background:${style.colors.category[index % style.colors.category.length]};margin-right:5px;"></i>${esc(row.label)} ${Math.round(row.value / total * 100)}%</span>`).join('');
        return `<div style="display:flex;height:28px;border-radius:4px;overflow:hidden;margin:14px 0;">${segments}</div><div style="display:flex;gap:12px;flex-wrap:wrap;">${legend}</div>`;
      }
      function renderBulletAssignees() {
        return data.rows.filter((row) => Number.isFinite(row.target)).map((row) => {
          const target = Math.min(100, Math.max(0, (row.target - domainMin) / domainSpan * 100));
          const color = row.value < 0 ? (style.colors.negative || style.colors.critical) : style.colors.primary;
          return `<div style="display:grid;grid-template-columns:${labelColumn} minmax(0,1fr) ${valueColumn};gap:${gap}px;align-items:center;margin:${dense ? 5 : 8}px 0;font-size:${compact ? 11 : 12}px;line-height:1.25;color:${style.colors.text};"><span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row.label)}</span><span style="position:relative;height:14px;background:${style.colors.surfaceMuted};">${signedBar(row.value, color, 14)}<em style="position:absolute;left:${target}%;top:-3px;height:20px;border-left:2px solid ${style.colors.critical};"></em></span><b style="text-align:right;">${fmt(row.value)}</b></div>`;
        }).join('');
      }
      function renderHeatmap() {
        const xValues = [...new Set(data.rows.map((row) => row.label))];
        const yValues = [...new Set(data.rows.map((row) => row.group || 'Все'))];
        const cellWidth = compact ? 82 : medium ? 96 : 112;
        const header = `<span></span>${xValues.map((value) => `<b style="padding:5px 6px;text-align:center;font-size:11px;color:${style.colors.textMuted};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(value)}</b>`).join('')}`;
        const cells = yValues.map((yValue, yIndex) => {
          const rowLabel = `<b style="padding:8px 6px;font-size:11px;color:${style.colors.textMuted};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(yValue)}</b>`;
          const rowCells = xValues.map((xValue, xIndex) => {
            const row = data.rows.find((item) => item.label === xValue && (item.group || 'Все') === yValue);
            const value = row && Number.isFinite(row.value) ? row.value : null;
            const alpha = value === null ? 0 : Math.max(0.16, Math.min(1, Math.abs(value) / maxAbs));
            const background = value === null
              ? style.colors.surfaceMuted
              : `color-mix(in srgb, ${style.colors.primary} ${Math.round(alpha * 78)}%, ${style.colors.surface})`;
            return `<div data-role="heatmap-cell" data-x="${esc(xValue)}" data-y="${esc(yValue)}" data-id="heatmap-cell-${yIndex}-${xIndex}" title="${esc(xValue)} · ${esc(yValue)} · ${value === null ? 'Нет данных' : fmt(value)}" style="min-height:${dense ? 42 : 54}px;padding:7px;border:1px solid ${style.colors.border};background:${background};display:grid;place-items:center;color:${style.colors.text};font-size:${compact ? 12 : 14}px;font-weight:850;">${value === null ? '—' : fmt(value)}</div>`;
          }).join('');
          return rowLabel + rowCells;
        }).join('');
        return `<div data-role="heatmap-matrix" data-x-count="${xValues.length}" data-y-count="${yValues.length}" style="overflow:auto;"><div style="display:grid;grid-template-columns:minmax(min-content,auto) repeat(${xValues.length},${cellWidth}px);gap:4px;min-width:max-content;">${header}${cells}</div></div>`;
      }
      function renderWaterfall() {
        let running = 0;
        const steps = data.rows.map((row) => {
          const start = running;
          const end = start + row.value;
          running = end;
          return {...row, start, end};
        });
        const cumulativeValues = [0, ...steps.flatMap((row) => [row.start, row.end])];
        const waterfallMin = Math.min(...cumulativeValues);
        const waterfallMax = Math.max(...cumulativeValues);
        const waterfallSpan = Math.max(Number.EPSILON, waterfallMax - waterfallMin);
        const position = (value) => (value - waterfallMin) / waterfallSpan * 100;
        const zero = position(0);
        return steps.map((row) => {
          const start = position(row.start);
          const end = position(row.end);
          const left = Math.min(start, end);
          const width = Math.abs(end - start);
          const color = row.value < 0 ? (style.colors.negative || style.colors.critical) : style.colors.ok;
          return `<div style="display:grid;grid-template-columns:${labelColumn} minmax(0,1fr) ${compact ? '58px' : '70px'};gap:${gap}px;align-items:center;margin:7px 0;font-size:${compact ? 11 : 12}px;line-height:1.25;color:${style.colors.text};"><span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row.label)}</span><span style="position:relative;height:12px;background:${style.colors.surfaceMuted};"><em style="position:absolute;left:${zero}%;height:12px;border-left:1px solid ${style.colors.border};"></em><i title="${fmt(row.start)} → ${fmt(row.end)}" style="position:absolute;display:block;left:${left}%;height:12px;width:${width}%;background:${color};"></i></span><b style="text-align:right;">${fmt(row.end)}</b></div>`;
        }).join('');
      }
      let body = renderHorizontalRows();
      if (data.variant === 'grouped_bar') body = renderGroupedBar();
      if (data.variant === 'stacked_100') body = renderStacked100();
      if (data.variant === 'bullet_assignees') body = renderBulletAssignees();
      if (data.variant === 'heatmap') body = renderHeatmap();
      if (data.variant === 'waterfall') body = renderWaterfall();
      return __dlGenerateProfileHtml(options, `<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 8 : 12}px ${compact ? 8 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;line-height:1.25;overflow-x:hidden;overflow-y:auto;">${body || `<div style="color:${style.colors.textSubtle};font-weight:800;">N/A</div>`}</div>`);
    },
  }),
};
