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

// Prepare: keep source rows generic; SQL chooses grain and measures.
const rows = normalizeRows('rows').map((row) => ({
  bucket: String(row.bucket || ''),
  metric: String(row.metric || 'value'),
  value: row.value == null || row.value === '' ? NaN : Number(row.value),
})).filter((row) => row.bucket && Number.isFinite(row.value));
const model = {variant: TEMPLATE_VARIANT, rows, hint: 'Grain-aware time chart with direct labels.', theme: themeName(), style: HOUSE_STYLE};

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
      // Render/layout: branch by approved time-oriented or funnel variant.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const width = Math.max(420, Number(options && options.width) || 640);
      const height = Math.max(260, Number(options && options.height) || 340);
      const margin = {l: 44, r: 26, t: 18, b: 34};
      const buckets = [...new Set(data.rows.map((row) => row.bucket))];
      const metrics = [...new Set(data.rows.map((row) => row.metric))];
      const maxValue = Math.max(1, ...data.rows.map((row) => row.value));
      const x = (index) => margin.l + (index / Math.max(1, buckets.length - 1)) * (width - margin.l - margin.r);
      const y = (value) => margin.t + (1 - value / maxValue) * (height - margin.t - margin.b);
      const grid = [0, 0.25, 0.5, 0.75, 1].map((part) => {
        const gy = y(maxValue * part);
        return `<line x1="${margin.l}" y1="${gy}" x2="${width - margin.r}" y2="${gy}" stroke="${style.colors.gridLine}"/><text x="${margin.l - 8}" y="${gy + 4}" text-anchor="end" font-size="11" fill="${style.colors.textSubtle}">${fmt(maxValue * part)}</text>`;
      }).join('');
      function buildLineSeries(fillArea) {
        return metrics.map((metric, metricIndex) => {
          const points = buckets.map((bucket, index) => {
            const found = data.rows.find((row) => row.bucket === bucket && row.metric === metric);
            return found ? {x: x(index), y: y(found.value), value: found.value} : null;
          });
          const segments = [];
          let segment = [];
          for (const point of points) {
            if (point) {
              segment.push(point);
            } else if (segment.length) {
              segments.push(segment);
              segment = [];
            }
          }
          if (segment.length) segments.push(segment);
          const color = style.colors.category[metricIndex % style.colors.category.length];
          const paths = segments.map((part) => {
            const path = part.map((point, index) => `${index ? 'L' : 'M'}${point.x},${point.y}`).join(' ');
            const areaPath = fillArea && part.length > 1
              ? `${path} L${part[part.length - 1].x},${height - margin.b} L${part[0].x},${height - margin.b} Z`
              : '';
            const area = areaPath ? `<path d="${areaPath}" fill="${color}" opacity="0.18"/>` : '';
            return `${area}<path d="${path}" fill="none" stroke="${color}" stroke-width="2.5"/>`;
          }).join('');
          const present = points.filter(Boolean);
          const last = present[present.length - 1];
          const label = last ? `<text x="${Math.min(width - 72, last.x + 8)}" y="${last.y + 4}" font-size="11" font-weight="800" fill="${style.colors.text}">${esc(metric)} ${fmt(last.value)}</text>` : '';
          return `${paths}${label}`;
        }).join('');
      }
      function buildVerticalBars(includeLine) {
        const band = (width - margin.l - margin.r) / Math.max(1, buckets.length);
        const bars = buckets.map((bucket, index) => {
          const total = data.rows.filter((row) => row.bucket === bucket).reduce((sum, row) => sum + row.value, 0);
          const barHeight = total / maxValue * (height - margin.t - margin.b);
          const bx = margin.l + index * band + 4;
          const by = height - margin.b - barHeight;
          return `<rect x="${bx}" y="${by}" width="${Math.max(4, band - 8)}" height="${barHeight}" fill="${style.colors.primary}" opacity="0.74"/><text x="${bx + band / 2}" y="${height - 8}" text-anchor="middle" font-size="10" fill="${style.colors.textMuted}">${esc(bucket)}</text>`;
        }).join('');
        return includeLine ? `${bars}${buildLineSeries(false)}` : bars;
      }
      function buildFunnel() {
        const ordered = data.rows.slice().sort((left, right) => right.value - left.value).slice(0, 6);
        const top = Math.max(1, ordered[0] ? ordered[0].value : 1);
        return ordered.map((row, index) => {
          const w = Math.max(18, row.value / top * 96);
          return `<div style="width:${w}%;margin:5px auto;padding:7px 10px;text-align:center;background:${style.colors.category[index % style.colors.category.length]};color:${style.colors.surface};font-size:12px;font-weight:800;">${esc(row.bucket || row.metric)} ${fmt(row.value)}</div>`;
        }).join('');
      }
      const legend = `<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px;font-size:12px;color:${style.colors.textMuted};">${metrics.map((metric, index) => `<span><i style="display:inline-block;width:9px;height:9px;background:${style.colors.category[index % style.colors.category.length]};margin-right:5px;"></i>${esc(metric)}</span>`).join('')}</div>`;
      let plot = buildLineSeries(false);
      if (data.variant === 'area_completion') plot = buildLineSeries(true);
      if (data.variant === 'vertical_bar_time_bucket') plot = buildVerticalBars(false);
      if (data.variant === 'combo_time_series_combo') plot = buildVerticalBars(true);
      if (data.variant === 'funnel_snapshot') {
        const funnel = buildFunnel();
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;">${funnel}</div>`);
      }
      const svg = `<svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${grid}${plot}<text x="${margin.l}" y="${height - 8}" font-size="11" fill="${style.colors.textMuted}">${esc(buckets[0] || '')}</text><text x="${width - margin.r}" y="${height - 8}" text-anchor="end" font-size="11" fill="${style.colors.textMuted}">${esc(buckets[buckets.length - 1] || '')}</text></svg>`;
      // Safe render contract: return HTML through Editor.generateHtml inside wrapFn.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;">${legend}${svg}</div>`);
    },
  }),
};
