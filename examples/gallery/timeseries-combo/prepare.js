const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {
  formatCompact,
  getParamScalar,
  getSourceRows,
  safeId,
  toNumber,
  toStringValue,
  withPalette,
} = require('../../../templates/advanced/chart-data-utils');
const {renderLegendItems} = require('../../../templates/advanced/legend');
const {renderSourceFreshness} = require('../../../templates/advanced/source-freshness');
const {renderTooltipShell} = require('../../../templates/advanced/tooltip');
const {HOUSE_STYLE} = require('../../../templates/advanced/style-tokens');
const {buildBandLayout, linearScale} = require('../../../templates/advanced/chart-svg-utils');
const {
  buildFunnelTooltipItems,
  normalizeFunnelStages,
  renderFunnelStageBars,
} = require('../../../templates/advanced/funnel-bars');

const VARIANT = getParamScalar('chart_variant', 'line_chart');

function hasSourceLoaded(name) {
  const direct = Editor.getLoadedData(name);
  if (direct !== undefined && direct !== null) {
    return true;
  }
  const loaded = Editor.getLoadedData() || {};
  return Object.prototype.hasOwnProperty.call(loaded, name);
}

function buildStatus(requiredSources, dataLength) {
  const missingRequired = requiredSources.some((sourceName) => !hasSourceLoaded(sourceName));
  if (missingRequired) {
    return 'unavailable';
  }
  return dataLength ? 'ok' : 'empty';
}

function buildFreshnessHtml(sourceLabel) {
  return renderSourceFreshness({
    sourceLabel,
    freshnessLabel: 'Static demo data',
    updatedAt: '2026-01-31 09:00 UTC',
  });
}

function buildLineModel() {
  const sourceName = 'lineRows';
  const series = withPalette([
    {
      label: 'Primary',
      color: HOUSE_STYLE.colors.data.primary,
      points: getSourceRows(sourceName).map((row, index) => ({
        id: safeId(`${row.period_label}_${index}`),
        label: toStringValue(row.period_label),
        value: toNumber(row.metric_value),
      })),
    },
  ]);
  const dataLength = series[0].points.length;
  return {
    chartVariant: 'line_chart',
    title: 'Line Chart',
    helpBody: 'Use this variant when continuity matters more than discrete bucket comparison and the series count stays small.',
    helpSource: 'datalens-advanced-editor timeseries umbrella family',
    freshnessHtml: buildFreshnessHtml('Trend series'),
    legendItems: series.map((item) => ({label: item.label, color: item.color})),
    series,
    tooltipItems: series[0].points.map((point) => ({
      id: point.id,
      title: point.label,
      rows: [{label: 'Value', value: formatCompact(point.value)}],
    })),
    dataLength,
    status: buildStatus([sourceName], dataLength),
  };
}

function buildBucketBarModel() {
  const sourceName = 'bucketRows';
  const points = getSourceRows(sourceName).map((row, index) => ({
    id: safeId(`${row.period_label}_${index}`),
    label: toStringValue(row.period_label),
    value: toNumber(row.metric_value),
  }));
  const dataLength = points.length;
  return {
    chartVariant: 'vertical_bar_time_bucket',
    title: 'Vertical Bar By Time Bucket',
    helpBody: 'Use this variant when discrete period magnitude matters more than continuity between points.',
    helpSource: 'datalens-advanced-editor timeseries umbrella family',
    freshnessHtml: buildFreshnessHtml('Bucketed trend rows'),
    legendItems: [{label: 'Metric', color: HOUSE_STYLE.colors.data.primary}],
    points,
    tooltipItems: points.map((point) => ({
      id: point.id,
      title: point.label,
      rows: [{label: 'Value', value: formatCompact(point.value)}],
    })),
    dataLength,
    status: buildStatus([sourceName], dataLength),
  };
}

function buildComboModel() {
  const barSource = 'comboBarRows';
  const lineSource = 'comboLineRows';
  const barPoints = getSourceRows(barSource).map((row, index) => ({
    id: safeId(`bar_${row.period_label}_${index}`),
    label: toStringValue(row.period_label),
    value: toNumber(row.metric_value),
  }));
  const linePoints = getSourceRows(lineSource).map((row, index) => ({
    id: safeId(`line_${row.period_label}_${index}`),
    label: toStringValue(row.period_label),
    value: toNumber(row.metric_value),
  }));
  const periodKeys = [...new Set([...barPoints.map((point) => point.label), ...linePoints.map((point) => point.label)])];
  const dataLength = Math.max(barPoints.length, linePoints.length);
  return {
    chartVariant: 'combo_time_series_combo',
    title: 'Combo Time Series',
    helpBody: 'Bars and line share one analytical frame here: buckets show the base count while the line carries the comparison metric.',
    helpSource: 'datalens-advanced-editor timeseries umbrella family',
    freshnessHtml: buildFreshnessHtml('Combo bar and line rows'),
    legendItems: [
      {label: 'Volume', color: HOUSE_STYLE.colors.data.primary},
      {label: 'Rate', color: HOUSE_STYLE.colors.data.accent},
    ],
    barPoints,
    linePoints,
    periodKeys,
    tooltipItems: [
      ...barPoints.map((point) => ({
        id: point.id,
        title: `${point.label} · Volume`,
        rows: [{label: 'Value', value: formatCompact(point.value)}],
      })),
      ...linePoints.map((point) => ({
        id: point.id,
        title: `${point.label} · Rate`,
        rows: [{label: 'Value', value: formatCompact(point.value)}],
      })),
    ],
    dataLength,
    status: buildStatus([barSource, lineSource], dataLength),
  };
}

function buildFunnelSnapshotModel() {
  const sourceName = 'funnelStageRows';
  const stages = normalizeFunnelStages(getSourceRows(sourceName));
  const dataLength = stages.length;
  return {
    chartVariant: 'funnel_snapshot',
    title: 'Funnel Snapshot',
    helpBody: 'Ordered stage leakage belongs in one focused funnel frame when the question is where the conversion drops between stages.',
    helpSource: 'datalens-advanced-editor timeseries umbrella family',
    freshnessHtml: buildFreshnessHtml('Stage snapshot rows'),
    legendItems: [],
    stages,
    tooltipItems: buildFunnelTooltipItems(stages),
    dataLength,
    status: buildStatus([sourceName], dataLength),
  };
}

function buildVariantModel() {
  if (VARIANT === 'vertical_bar_time_bucket') return buildBucketBarModel();
  if (VARIANT === 'combo_time_series_combo') return buildComboModel();
  if (VARIANT === 'funnel_snapshot') return buildFunnelSnapshotModel();
  return buildLineModel();
}

function renderLineSvg(series, width, height) {
  const points = series[0].points;
  const xLayout = buildBandLayout(points.map((point) => point.label), 24, width - 14, 18);
  const maxValue = Math.max(...points.map((point) => point.value), 1);
  const yScale = linearScale(0, maxValue, height - 28, 16);
  const linePoints = points.map((point) => ({
    x: xLayout.position(point.label) + xLayout.bandwidth / 2,
    y: yScale(point.value),
    id: point.id,
  }));
  const pointsHtml = linePoints.map((point) => `
    <circle data-id="${point.id}" cx="${point.x}" cy="${point.y}" r="4" fill="${series[0].color}"></circle>
  `).join('');
  const labels = points.map((point) => `
    <text x="${xLayout.position(point.label) + xLayout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${point.label}</text>
  `).join('');
  const directLabel = points.length
    ? `<text x="${linePoints[linePoints.length - 1].x + 8}" y="${linePoints[linePoints.length - 1].y + 4}" font-size="12" font-weight="800" fill="${HOUSE_STYLE.colors.text.strong}">${formatCompact(points[points.length - 1].value)}</text>`
    : '';

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <polyline fill="none" stroke="${series[0].color}" stroke-width="3" points="${linePoints.map((point) => `${point.x},${point.y}`).join(' ')}"></polyline>
    ${pointsHtml}
    ${labels}
    ${directLabel}
  </svg>`;
}

function renderBucketBars(points, width, height) {
  const layout = buildBandLayout(points.map((point) => point.label), 32, width - 12, 18);
  const maxValue = Math.max(...points.map((point) => point.value), 1);
  const yScale = linearScale(0, maxValue, height - 28, 16);
  const bars = points.map((point) => {
    const x = layout.position(point.label);
    const y = yScale(point.value);
    return `
      <rect data-id="${point.id}" x="${x}" y="${y}" width="${layout.bandwidth}" height="${height - 28 - y}" fill="${HOUSE_STYLE.colors.data.primary}" rx="0"></rect>
      <text x="${x + layout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${point.label}</text>
      <text x="${x + layout.bandwidth / 2}" y="${y - 6}" text-anchor="middle" font-size="11" font-weight="800" fill="${HOUSE_STYLE.colors.text.strong}">${formatCompact(point.value)}</text>
    `;
  }).join('');
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${bars}</svg>`;
}

function renderComboSvg(model, width, height) {
  const xLayout = buildBandLayout(model.periodKeys, 28, width - 20, 18);
  const barMax = Math.max(...model.barPoints.map((point) => point.value), 1);
  const lineMax = Math.max(...model.linePoints.map((point) => point.value), 1);
  const maxValue = Math.max(barMax, lineMax);
  const yScale = linearScale(0, maxValue, height - 30, 18);

  const bars = model.barPoints.map((point) => {
    const x = xLayout.position(point.label);
    const y = yScale(point.value);
    return `
      <rect data-id="${point.id}" x="${x}" y="${y}" width="${xLayout.bandwidth}" height="${height - 30 - y}" fill="${HOUSE_STYLE.colors.data.primary}" fill-opacity="0.75" rx="0"></rect>
    `;
  }).join('');

  const linePoints = model.linePoints.map((point) => ({
    x: xLayout.position(point.label) + xLayout.bandwidth / 2,
    y: yScale(point.value),
    id: point.id,
  }));

  const lineHtml = `
    <polyline fill="none" stroke="${HOUSE_STYLE.colors.data.accent}" stroke-width="3" points="${linePoints.map((point) => `${point.x},${point.y}`).join(' ')}"></polyline>
    ${linePoints.map((point, index) => `<circle data-id="${point.id}" cx="${point.x}" cy="${point.y}" r="${index === linePoints.length - 1 ? 4 : 3}" fill="${HOUSE_STYLE.colors.data.accent}"></circle>`).join('')}
    ${linePoints.length ? `<text x="${linePoints[linePoints.length - 1].x + 8}" y="${linePoints[linePoints.length - 1].y + 4}" font-size="11" font-weight="800" fill="${HOUSE_STYLE.colors.text.strong}">${formatCompact(model.linePoints[model.linePoints.length - 1].value)}</text>` : ''}
  `;

  const labels = model.periodKeys.map((key) => `
    <text x="${xLayout.position(key) + xLayout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${key}</text>
  `).join('');

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    ${bars}
    ${lineHtml}
    ${labels}
  </svg>`;
}

const model = buildVariantModel();

module.exports = {
  chartVariant: model.chartVariant,
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, currentModel) {
      function esc(value) {
        return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function fmt(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return '—';
        const abs = Math.abs(n);
        if (abs >= 1000000) return `${(n / 1000000).toFixed(1).replace('.0', '')}M`;
        if (abs >= 1000) return `${(n / 1000).toFixed(1).replace('.0', '')}K`;
        return String(Math.round(n * 10) / 10).replace('.0', '');
      }
      function xAt(index, count, left, width) {
        return left + (count <= 1 ? width / 2 : (index / (count - 1)) * width);
      }
      function yAt(value, maxValue, top, height) {
        return top + height - ((Number(value) || 0) / Math.max(1, maxValue)) * height;
      }
      function legend(items) {
        if (!items || items.length <= 1) return '';
        return `<div style="height:32px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;overflow:hidden;">${items.slice(0, 6).map((item) => `<div style="display:flex;align-items:center;gap:6px;min-width:0;"><span style="width:9px;height:9px;border-radius:999px;background:${esc(item.color || '#2B75E2')};"></span><span style="font-size:12px;line-height:14px;color:#667085;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(item.label)}</span></div>`).join('')}</div>`;
      }
      function lineChart(series, width, height) {
        const points = ((series && series[0] && series[0].points) || []).slice(0, 36);
        const maxValue = Math.max(1, ...points.map((point) => Number(point.value) || 0));
        const margin = {l: 42, r: 20, t: 12, b: 28};
        const plotW = Math.max(1, width - margin.l - margin.r);
        const plotH = Math.max(1, height - margin.t - margin.b);
        const guides = [0, 0.5, 1].map((frac) => {
          const value = maxValue * frac;
          const y = yAt(value, maxValue, margin.t, plotH);
          return `<line x1="${margin.l}" y1="${y.toFixed(1)}" x2="${margin.l + plotW}" y2="${y.toFixed(1)}" stroke="#E4E7EC" stroke-dasharray="4 4"></line><text x="${margin.l - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#98A2B3">${fmt(value)}</text>`;
        }).join('');
        const coords = points.map((point, index) => ({x: xAt(index, points.length, margin.l, plotW), y: yAt(point.value, maxValue, margin.t, plotH), id: point.id}));
        const line = coords.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
        const circles = coords.map((point, index) => `<circle data-id="${esc(point.id)}" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="${index === coords.length - 1 ? 4 : 3}" fill="#2B75E2"></circle>`).join('');
        const labels = points.filter((_, index) => index === 0 || index === points.length - 1 || index % Math.ceil(points.length / 4) === 0).map((point, index, shown) => {
          const realIndex = points.indexOf(point);
          return `<text x="${coords[realIndex].x.toFixed(1)}" y="${height - 8}" text-anchor="${index === 0 ? 'start' : index === shown.length - 1 ? 'end' : 'middle'}" font-size="11" font-weight="700" fill="#667085">${esc(point.label)}</text>`;
        }).join('');
        const direct = points.length ? `<text x="${Math.min(width - 40, coords[coords.length - 1].x + 8).toFixed(1)}" y="${(coords[coords.length - 1].y + 4).toFixed(1)}" font-size="12" font-weight="800" fill="#111827">${fmt(points[points.length - 1].value)}</text>` : '';
        return `<svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;overflow:visible;">${guides}<line x1="${margin.l}" y1="${margin.t + plotH}" x2="${margin.l + plotW}" y2="${margin.t + plotH}" stroke="#D0D5DD"></line><polyline fill="none" stroke="#2B75E2" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" points="${line}"></polyline>${circles}${labels}${direct}</svg>`;
      }
      function bars(points, width, height) {
        const safePoints = (points || []).slice(0, 18);
        const maxValue = Math.max(1, ...safePoints.map((point) => Number(point.value) || 0));
        const margin = {l: 42, r: 16, t: 12, b: 28};
        const plotW = Math.max(1, width - margin.l - margin.r);
        const plotH = Math.max(1, height - margin.t - margin.b);
        const barW = Math.max(8, plotW / Math.max(1, safePoints.length) - 6);
        const guides = [0, 0.5, 1].map((frac) => {
          const value = maxValue * frac;
          const y = yAt(value, maxValue, margin.t, plotH);
          return `<line x1="${margin.l}" y1="${y.toFixed(1)}" x2="${margin.l + plotW}" y2="${y.toFixed(1)}" stroke="#E4E7EC" stroke-dasharray="4 4"></line><text x="${margin.l - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#98A2B3">${fmt(value)}</text>`;
        }).join('');
        const marks = safePoints.map((point, index) => {
          const x = margin.l + index * (plotW / Math.max(1, safePoints.length)) + 3;
          const y = yAt(point.value, maxValue, margin.t, plotH);
          const h = margin.t + plotH - y;
          return `<rect data-id="${esc(point.id)}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="#2B75E2"></rect><text x="${(x + barW / 2).toFixed(1)}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="#667085">${esc(point.label)}</text>`;
        }).join('');
        return `<svg data-qa-axis-origin="zero" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;overflow:visible;">${guides}<line x1="${margin.l}" y1="${margin.t + plotH}" x2="${margin.l + plotW}" y2="${margin.t + plotH}" stroke="#D0D5DD"></line>${marks}</svg>`;
      }

      const rawWidth = Number(options && options.width) || 0;
      const rawHeight = Number(options && options.height) || 0;
      const width = rawWidth > 0 ? rawWidth : 640;
      const height = rawHeight > 0 ? rawHeight : 360;
      const dense = width < 460 || height < 260;
      const titleSize = dense ? 18 : 20;
      const headerH = titleSize + 14 + ((currentModel.legendItems || []).length > 1 ? 32 : 0);
      const bodyH = Math.max(160, height - headerH - 28);
      const empty = currentModel.status && currentModel.status !== 'ok';
      const chartBody = empty
        ? `<div style="flex:1;display:flex;align-items:center;justify-content:center;font-size:28px;line-height:34px;font-weight:800;color:#111827;">${currentModel.status === 'unavailable' ? 'SOURCE MISSING' : 'NO DATA'}</div>`
        : currentModel.chartVariant === 'vertical_bar_time_bucket'
          ? bars(currentModel.points, width - 28, bodyH)
          : currentModel.chartVariant === 'combo_time_series_combo'
            ? `${bars(currentModel.barPoints, width - 28, Math.floor(bodyH * 0.52))}${lineChart([{points: currentModel.linePoints}], width - 28, Math.floor(bodyH * 0.48))}`
            : currentModel.chartVariant === 'funnel_snapshot'
              ? bars((currentModel.stages || []).map((stage) => ({id: stage.id || stage.label, label: stage.label, value: stage.value})), width - 28, bodyH)
              : lineChart(currentModel.series, width - 28, bodyH);

      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:100%;height:100%;padding:${dense ? 10 : 12}px ${dense ? 12 : 14}px;background:transparent;border:none;font-family:Inter,Arial,sans-serif;color:#111827;display:flex;flex-direction:column;gap:8px;overflow:hidden;">
          <div style="display:flex;align-items:center;gap:8px;min-width:0;">
            <div style="font-size:${titleSize}px;line-height:${titleSize + 2}px;color:#5F6368;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(currentModel.title)}</div>
            <div data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:${dense ? 16 : 18}px;height:${dense ? 16 : 18}px;border-radius:999px;background:#F2F4F7;color:#667085;font-size:${dense ? 11 : 12}px;line-height:1;font-weight:800;cursor:help;flex:0 0 auto;">?</div>
          </div>
          ${legend(currentModel.legendItems || [])}
          ${currentModel.freshnessHtml || ''}
          ${chartBody}
        </div>
      `);
    },
  }),
  tooltip: {
    renderer: Editor.wrapFn({
      args: [{
        title: model.title,
        helpBody: model.helpBody,
        helpSource: model.helpSource,
        items: model.tooltipItems || [],
      }],
      fn: function(event, payload) {
        function esc(value) {
          return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }
        const target = event && event.target;
        const closest = target && target.closest ? target.closest('[data-id]') : target;
        const id = closest && closest.getAttribute ? closest.getAttribute('data-id') : null;
        if (!id) return null;
        const match = id === 'hint'
          ? {title: payload.title, rows: [{label: 'Rule', value: payload.helpBody}, {label: 'Source', value: payload.helpSource}]}
          : payload.items.find((item) => item.id === id);
        if (!match) return null;
        const rows = (match.rows || []).map((row) => `<div style="display:flex;justify-content:space-between;gap:18px;margin-top:6px;"><span style="color:#667085;">${esc(row.label)}</span><span style="font-weight:800;color:#111827;">${esc(row.value)}</span></div>`).join('');
        return Editor.generateHtml(`<div style="min-width:220px;max-width:340px;padding:10px 12px;border-radius:10px;background:#fff;color:#111827;font-family:Inter,Arial,sans-serif;font-size:12px;line-height:16px;"><div style="font-weight:800;">${esc(match.title)}</div>${rows}</div>`);
      },
    }),
  },
};
