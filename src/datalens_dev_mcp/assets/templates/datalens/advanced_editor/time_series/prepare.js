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
  seriesRole: String(row.series_role || 'current').toLowerCase(),
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
        if (value == null || value === '' || !Number.isFinite(Number(value))) return 'N/A';
        const number = Number(value);
        const abs = Math.abs(number);
        if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
        if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
        return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
      }
      function dateLabel(value) {
        const text = String(value == null ? '' : value).trim();
        const daily = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$/);
        if (daily) return `${daily[3]}.${daily[2]}.${daily[1].slice(2)}`;
        const monthly = text.match(/^(\d{4})-(\d{2})$/);
        if (monthly) return `${monthly[2]}.${monthly[1].slice(2)}`;
        return text || 'N/A';
      }
      function niceAxis(maximum, count) {
        if (!Number.isFinite(maximum) || maximum <= 0) return {max: 1, ticks: [0, 1]};
        const rough = maximum / Math.max(2, count);
        const power = Math.pow(10, Math.floor(Math.log10(rough)));
        const fraction = rough / power;
        const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
        const step = niceFraction * power;
        const max = Math.ceil(maximum / step) * step;
        const ticks = [];
        for (let value = 0; value <= max + step / 2; value += step) ticks.push(Number(value.toPrecision(12)));
        return {max, ticks};
      }
      // Render/layout: branch by approved time-oriented or funnel variant.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = width < 530;
      const legendHeight = data.rows.length && new Set(data.rows.map((row) => row.metric)).size > 1 ? 28 : 0;
      const plotHeight = Math.max(80, height - legendHeight - 28);
      const margin = {l: compact ? 36 : 44, r: compact ? 10 : 26, t: 14, b: compact ? 28 : 34};
      const buckets = [...new Set(data.rows.map((row) => row.bucket))];
      const metrics = [...new Set(data.rows.map((row) => row.metric))];
      const observedMax = Math.max(0, ...data.rows.map((row) => row.value));
      const axis = niceAxis(observedMax, compact ? 3 : 4);
      const maxValue = axis.max;
      const x = (index) => margin.l + (index / Math.max(1, buckets.length - 1)) * (width - margin.l - margin.r);
      const y = (value) => margin.t + (1 - value / maxValue) * (plotHeight - margin.t - margin.b);
      const axisLabels = axis.ticks.map((tick) => {
        const gy = y(tick);
        return `<line x1="${margin.l - 3}" y1="${gy}" x2="${margin.l}" y2="${gy}" stroke="${style.colors.gridLine}"/><text x="${margin.l - 6}" y="${gy + 4}" text-anchor="end" font-size="${compact ? 10 : 11}" fill="${style.colors.textSubtle}">${fmt(tick)}</text>`;
      }).join('');
      function buildLineSeries(fillArea) {
        return metrics.map((metric, metricIndex) => {
          const role = (data.rows.find((row) => row.metric === metric) || {}).seriesRole || 'current';
          const isComparison = role === 'comparison';
          const points = buckets.map((bucket, index) => {
            const found = data.rows.find((row) => row.bucket === bucket && row.metric === metric);
            return found ? {x: x(index), y: y(found.value), value: found.value, bucket} : null;
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
            const areaPath = fillArea && part.length > 1 && !isComparison
              ? `${path} L${part[part.length - 1].x},${plotHeight - margin.b} L${part[0].x},${plotHeight - margin.b} Z`
              : '';
            const area = areaPath ? `<path d="${areaPath}" fill="${color}" opacity="0.18"/>` : '';
            const hitTargets = part.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="8" fill="transparent"><title>${esc(dateLabel(point.bucket))} · ${esc(metric)}: ${fmt(point.value)}</title></circle>`).join('');
            return `${area}<path d="${path}" fill="none" stroke="${color}" stroke-width="${isComparison ? 2 : 2.5}" stroke-dasharray="${isComparison ? '6 5' : 'none'}" opacity="${isComparison ? 0.45 : 1}"/>${hitTargets}`;
          }).join('');
          const present = points.filter(Boolean);
          const last = present[present.length - 1];
          const label = last ? `<text x="${Math.min(width - 72, last.x + 8)}" y="${last.y + 4}" font-size="11" font-weight="800" fill="${style.colors.text}" opacity="${isComparison ? 0.62 : 1}">${esc(metric)} ${fmt(last.value)}</text>` : '';
          return `${paths}${label}`;
        }).join('');
      }
      function buildVerticalBars(includeLine) {
        const band = (width - margin.l - margin.r) / Math.max(1, buckets.length);
        const bars = buckets.map((bucket, index) => {
          const total = data.rows.filter((row) => row.bucket === bucket).reduce((sum, row) => sum + row.value, 0);
          const barHeight = total / maxValue * (plotHeight - margin.t - margin.b);
          const bx = margin.l + index * band + 4;
          const by = plotHeight - margin.b - barHeight;
          const labelEvery = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor(width / 72))));
          const showLabel = index === 0 || index === buckets.length - 1 || index % labelEvery === 0;
          const bar = total === 0 ? '' : `<rect x="${bx}" y="${by}" width="${Math.max(2, band - 8)}" height="${barHeight}" fill="${style.colors.primary}" opacity="0.74"/>`;
          const label = showLabel ? `<text x="${bx + band / 2}" y="${plotHeight - 8}" text-anchor="middle" font-size="10" fill="${style.colors.textMuted}">${esc(dateLabel(bucket))}</text>` : '';
          return `${bar}${label}`;
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
      const legend = metrics.length > 1 ? `<div style="display:flex;gap:${compact ? 8 : 12}px;flex-wrap:wrap;margin-bottom:6px;font-size:${compact ? 11 : 12}px;line-height:1.25;color:${style.colors.textMuted};">${metrics.map((metric, index) => `<span><i style="display:inline-block;width:9px;height:9px;background:${style.colors.category[index % style.colors.category.length]};margin-right:5px;"></i>${esc(metric)}</span>`).join('')}</div>` : '';
      let plot = buildLineSeries(false);
      if (data.variant === 'area_completion') plot = buildLineSeries(true);
      if (data.variant === 'vertical_bar_time_bucket') plot = buildVerticalBars(false);
      if (data.variant === 'combo_time_series_combo') plot = buildVerticalBars(true);
      if (data.variant === 'funnel_snapshot') {
        const funnel = buildFunnel();
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;">${funnel}</div>`);
      }
      const svg = `<svg width="100%" height="${plotHeight}" viewBox="0 0 ${width} ${plotHeight}" preserveAspectRatio="none">${axisLabels}${plot}<text x="${margin.l}" y="${plotHeight - 8}" font-size="${compact ? 10 : 11}" fill="${style.colors.textMuted}">${esc(dateLabel(buckets[0] || ''))}</text><text x="${width - margin.r}" y="${plotHeight - 8}" text-anchor="end" font-size="${compact ? 10 : 11}" fill="${style.colors.textMuted}">${esc(dateLabel(buckets[buckets.length - 1] || ''))}</text></svg>`;
      // Safe render contract: return HTML through Editor.generateHtml inside wrapFn.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 8 : 12}px ${compact ? 8 : 14}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;line-height:1.25;overflow:hidden;">${legend}${svg}</div>`);
    },
  }),
};
