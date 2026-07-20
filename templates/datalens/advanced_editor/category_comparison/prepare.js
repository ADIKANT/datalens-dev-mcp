/*
 * Advanced Editor template contract:
 * - Source/data contract: sources.js must expose rows that match schema.json and example_input.json.
 * - Params/config: params.json drives theme, filters, variants, and safe defaults.
 * - Prepare/model normalization: prepare.js converts loaded rows into a serializable model before render.
 * - Render lifecycle: render is exported only as Editor.wrapFn and returns Editor.generateHtml.
 * - Layout/scales: size, axes, and scales are derived from model and options without dashboard title rows.
 * - Labels/tooltips: labels, legends, and tooltips explain values without duplicating native widget hints.
 * - Theme tokens: colors and spacing come from shared HOUSE_STYLE tokens.
 * - Interactions: interactions stay explicit and selector bindings are represented outside chart body.
 * - Extension points: future edits should change schema, params, or shared helpers before ad hoc JS.
 */
/* __DATALENS_SHARED_STYLE_TOKENS__ */
/* __DATALENS_SHARED_RENDER_HELPERS__ */
const TEMPLATE_VARIANT = '__TEMPLATE_VARIANT__';
const numericOrNaN = (value) => value == null || value === '' ? NaN : Number(value);

// Prepare: sort comparisons deterministically, but preserve waterfall step order.
const normalizedRows = normalizeRows('rows')
  .map((row) => ({
    label: String(row.label || ''),
    group: String(row.group || 'All'),
    value: numericOrNaN(row.value),
    target: numericOrNaN(row.target),
  }))
  .filter((row) => Number.isFinite(row.value));
const rows = (TEMPLATE_VARIANT === 'waterfall'
  ? normalizedRows
  : normalizedRows.slice().sort((left, right) => right.value - left.value)
).slice(0, 18);
const hint = TEMPLATE_VARIANT === 'waterfall'
  ? 'Ordered cumulative deltas with start and end positions.'
  : 'Sorted comparison with zero baseline and direct labels.';
const model = {variant: TEMPLATE_VARIANT, rows, hint, theme: themeName(), style: HOUSE_STYLE};

module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      function esc(value) {
        return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function fmt(value) {
        if (value == null || value === '' || !Number.isFinite(Number(value))) return 'N/A';
        const number = Number(value);
        const abs = Math.abs(number);
        if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
        if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
        return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
      }
      // Render/layout: route each approved variant to a distinct visual grammar.
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
          return `<div style="color:${style.colors.textMuted};font-size:12px;">N/A · 100% stack requires non-negative values</div>`;
        }
        const total = data.rows.reduce((sum, row) => sum + row.value, 0);
        if (!(total > 0)) {
          return `<div style="color:${style.colors.textMuted};font-size:12px;">N/A · positive total required</div>`;
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
        const columns = compact ? 1 : medium ? 2 : 3;
        return `<div style="display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:6px;">${data.rows.map((row) => {
          const alpha = Math.max(0.16, Math.min(1, Math.abs(row.value) / maxAbs));
          return `<div style="min-height:54px;padding:8px;border:1px solid ${style.colors.border};background:color-mix(in srgb, ${style.colors.primary} ${Math.round(alpha * 75)}%, ${style.colors.surface});color:${style.colors.text};"><b style="display:block;font-size:12px;">${esc(row.label)}</b><span style="font-size:16px;font-weight:850;">${fmt(row.value)}</span></div>`;
        }).join('')}</div>`;
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
      // Safe render contract: no external DOM mutation and no unsupported Editor methods.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 8 : 12}px ${compact ? 8 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;line-height:1.25;overflow-x:hidden;overflow-y:auto;">${body || `<div style="color:${style.colors.textSubtle};font-weight:800;">N/A</div>`}</div>`);
    },
  }),
};
