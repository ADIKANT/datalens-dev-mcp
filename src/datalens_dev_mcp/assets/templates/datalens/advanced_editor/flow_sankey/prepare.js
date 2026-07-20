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

// Prepare: validate flow shape. Source and target are mandatory for Sankey-like routing.
const parsedRows = normalizeRows('rows')
  .map((row) => ({
    source: String(row.source || ''),
    target: String(row.target || ''),
    value: row.value == null || row.value === '' ? NaN : Number(row.value),
  }));
const invalidReason = parsedRows.some((row) => !row.source || !row.target || !Number.isFinite(row.value) || !(row.value > 0))
  ? 'flow_rows_require_source_target_and_positive_value'
  : '';
const rows = parsedRows.map((row) => ({...row, value: Number.isFinite(row.value) ? row.value : 0}));
const model = {title: 'Flow', rows, invalidReason, hint: 'Flow chart requires explicit source, target, and positive value.', theme: themeName(), style: HOUSE_STYLE};

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
      // Render/layout: compact flow list baseline; upgrade to richer Sankey only after manual review.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = width < 530;
      const dense = compact || Math.max(220, data.rows.length * 44) > height;
      if (data.invalidReason) {
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px;background:${style.colors.surface};color:${style.colors.textMuted};font-family:Inter,Arial,sans-serif;">N/A · ${esc(data.invalidReason)}</div>`);
      }
      const maxValue = Math.max(1, ...data.rows.map((row) => row.value));
      const rowsHtml = data.rows.map((row, index) => {
        const shareWidth = Math.max(4, (row.value / maxValue) * 100);
        const color = style.colors.category[index % style.colors.category.length];
        const bar = `<span style="display:block;height:${dense ? 8 : 12}px;background:${style.colors.surfaceMuted};"><i style="display:block;height:100%;width:${shareWidth}%;background:${color};"></i></span>`;
        if (compact) {
          return `<div style="margin:${dense ? 6 : 10}px 0;font-size:${dense ? 11 : 12}px;color:${style.colors.text};"><div style="display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto;gap:6px;align-items:center;margin-bottom:4px;"><b style="min-width:0;overflow:hidden;text-overflow:ellipsis;">${esc(row.source)}</b><span>→</span><b style="min-width:0;overflow:hidden;text-overflow:ellipsis;">${esc(row.target)}</b><span style="text-align:right;">${fmt(row.value)}</span></div>${bar}</div>`;
        }
        return `<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr) minmax(0,1fr) auto;gap:8px;align-items:center;margin:${dense ? 6 : 10}px 0;font-size:${dense ? 11 : 12}px;color:${style.colors.text};"><b style="min-width:0;overflow:hidden;text-overflow:ellipsis;">${esc(row.source)}</b>${bar}<b style="min-width:0;overflow:hidden;text-overflow:ellipsis;">${esc(row.target)}</b><span style="text-align:right;">${fmt(row.value)}</span></div>`;
      }).join('');
      // Safe render contract: this is a gated flow template, not a generic category chart.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 8 : 12}px ${compact ? 8 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow-x:hidden;overflow-y:auto;">${rowsHtml || `<div style="color:${style.colors.textSubtle};font-weight:800;">NO FLOW DATA</div>`}</div>`);
    },
  }),
};
