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

// Prepare: keep category count small; long tails should be bucketed before this template.
const sourceRows = normalizeRows('rows');
const parsedRows = sourceRows.map((row) => ({
  label: String(row.label || ''),
  value: row.value == null || row.value === '' ? NaN : Number(row.value),
})).slice(0, 8);
const invalidReason = sourceRows.length > 8
  ? 'category_cap_exceeded'
  : parsedRows.some((row) => !row.label || !Number.isFinite(row.value) || row.value < 0)
    ? 'invalid_or_negative_part'
    : !(parsedRows.reduce((sum, row) => sum + row.value, 0) > 0)
      ? 'positive_total_required'
      : '';
const rows = parsedRows.map((row) => ({...row, value: Number.isFinite(row.value) ? row.value : 0}));
const total = rows.reduce((sum, row) => sum + row.value, 0);
const model = {variant: TEMPLATE_VARIANT, rows, total, invalidReason, hint: 'Small part-to-whole set; prefer bars for ranking.', theme: themeName(), style: HOUSE_STYLE};

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
      // Render/layout: pie, donut, and treemap each use a distinct branch.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = width < 530 || height < 260;
      if (data.invalidReason) {
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px;background:${style.colors.surface};color:${style.colors.textMuted};font-family:Inter,Arial,sans-serif;">N/A · ${esc(data.invalidReason)}</div>`);
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
      // Safe render contract: one chart object, no invented Editor APIs.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 8 : 12}px ${compact ? 8 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;"><div style="display:grid;${layout}width:100%;height:100%;align-items:stretch;gap:${compact ? 6 : 16}px;"><div style="min-width:0;min-height:0;">${chart}</div><div style="min-width:0;min-height:0;overflow-y:auto;overflow-x:hidden;">${legend}</div></div></div>`);
    },
  }),
};
