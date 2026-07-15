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

// Prepare: normalize numeric fields; reject removed density/jitter/beeswarm paths upstream.
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
  if (TEMPLATE_VARIANT === 'bubble') return [row.x, row.y, row.size].every(Number.isFinite);
  return Number.isFinite(row.value);
});
const model = {variant: TEMPLATE_VARIANT, rows, hint: 'Distribution or relationship with explicit numeric fields.', theme: themeName(), style: HOUSE_STYLE};

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
      // Render/layout: branch by distribution or relationship variant.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const width = Math.max(420, Number(options && options.width) || 640);
      const height = Math.max(260, Number(options && options.height) || 320);
      const margin = {l: 42, r: 18, t: 18, b: 34};
      const numericValues = data.rows.flatMap((row) => [row.value, row.x, row.y, row.size, row.min, row.q1, row.median, row.q3, row.max]).filter(Number.isFinite);
      const maxValue = Math.max(1, ...numericValues);
      function renderHistogram() {
        const band = (width - margin.l - margin.r) / Math.max(1, data.rows.length);
        return data.rows.map((row, index) => {
        const barHeight = (row.value / maxValue) * (height - margin.t - margin.b);
        const x = margin.l + index * band + 3;
        const y = height - margin.b - barHeight;
        return `<rect x="${x}" y="${y}" width="${Math.max(4, band - 6)}" height="${barHeight}" fill="${style.colors.primary}"/><text x="${x + band / 2}" y="${height - 10}" text-anchor="middle" font-size="11" fill="${style.colors.textMuted}">${esc(row.label)}</text><text x="${x + band / 2}" y="${y - 5}" text-anchor="middle" font-size="10" font-weight="800" fill="${style.colors.text}">${fmt(row.value)}</text>`;
        }).join('');
      }
      function renderBoxPlot() {
        const groups = data.rows;
        const band = (width - margin.l - margin.r) / Math.max(1, groups.length);
        return groups.map((row, index) => {
          const center = margin.l + index * band + band / 2;
          const scale = (value) => height - margin.b - (value / maxValue) * (height - margin.t - margin.b);
          const low = scale(row.min);
          const q1 = scale(row.q1);
          const med = scale(row.median);
          const q3 = scale(row.q3);
          const high = scale(row.max);
          return `<line x1="${center}" y1="${high}" x2="${center}" y2="${low}" stroke="${style.colors.textMuted}"/><line x1="${center - 12}" y1="${high}" x2="${center + 12}" y2="${high}" stroke="${style.colors.textMuted}"/><line x1="${center - 12}" y1="${low}" x2="${center + 12}" y2="${low}" stroke="${style.colors.textMuted}"/><rect x="${center - 20}" y="${q3}" width="40" height="${Math.max(2, q1 - q3)}" fill="${style.colors.surfaceMuted}" stroke="${style.colors.primary}"/><line x1="${center - 20}" y1="${med}" x2="${center + 20}" y2="${med}" stroke="${style.colors.primary}" stroke-width="2"/><text x="${center}" y="${height - 10}" text-anchor="middle" font-size="11" fill="${style.colors.textMuted}">${esc(row.label)}</text>`;
        }).join('');
      }
      function renderScatter(includeBubble) {
        const maxX = Math.max(1, ...data.rows.map((row) => row.x));
        const maxY = Math.max(1, ...data.rows.map((row) => row.y));
        return data.rows.map((row, index) => {
          const cx = margin.l + row.x / maxX * (width - margin.l - margin.r);
          const cy = margin.t + (1 - row.y / maxY) * (height - margin.t - margin.b);
          const radius = includeBubble ? Math.max(5, Math.min(24, row.size / maxValue * 24)) : 5;
          return `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="${style.colors.category[index % style.colors.category.length]}" opacity="0.72"><title>${esc(row.label)} ${fmt(row.x)} / ${fmt(row.y)}</title></circle>`;
        }).join('');
      }
      let marks = renderHistogram();
      if (data.variant === 'box_plot') marks = renderBoxPlot();
      if (data.variant === 'scatter') marks = renderScatter(false);
      if (data.variant === 'bubble') marks = renderScatter(true);
      // Safe render contract: return generated HTML and keep axes visible.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;"><svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line x1="${margin.l}" y1="${height - margin.b}" x2="${width - margin.r}" y2="${height - margin.b}" stroke="${style.colors.border}"/><line x1="${margin.l}" y1="${margin.t}" x2="${margin.l}" y2="${height - margin.b}" stroke="${style.colors.border}"/>${marks}</svg></div>`);
    },
  }),
};
