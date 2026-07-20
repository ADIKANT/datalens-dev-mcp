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
  if (TEMPLATE_VARIANT === 'bubble') return [row.x, row.y, row.size].every(Number.isFinite) && row.size > 0;
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
      // Render/layout: branch by distribution or relationship variant.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 320;
      const compact = width < 530 || height < 260;
      const margin = {l: compact ? 30 : 42, r: compact ? 8 : 18, t: compact ? 10 : 18, b: compact ? 26 : 34};
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
      // Safe render contract: return generated HTML and keep axes visible.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 6 : 12}px ${compact ? 6 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;"><svg width="100%" height="100%" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line x1="${margin.l}" y1="${height - margin.b}" x2="${width - margin.r}" y2="${height - margin.b}" stroke="${style.colors.border}"/><line x1="${margin.l}" y1="${margin.t}" x2="${margin.l}" y2="${height - margin.b}" stroke="${style.colors.border}"/>${marks}</svg></div>`);
    },
  }),
};
