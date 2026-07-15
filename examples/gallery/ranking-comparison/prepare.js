const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {
  bucketTailToOther,
  clamp,
  formatCompact,
  formatInteger,
  formatPercent,
  getParamScalar,
  getSourceRows,
  groupBy,
  safeId,
  sortDesc,
  sumBy,
  toNumber,
  toStringValue,
  withPalette,
} = require('../../../templates/advanced/chart-data-utils');
const {truncateLabel} = require('../../../templates/advanced/direct-labels');
const {renderLegendItems, renderInlineShareLegend} = require('../../../templates/advanced/legend');
const {renderSourceFreshness} = require('../../../templates/advanced/source-freshness');
const {renderTooltipShell} = require('../../../templates/advanced/tooltip');
const {HOUSE_STYLE} = require('../../../templates/advanced/style-tokens');
const {buildBandLayout, linearScale, maxOr} = require('../../../templates/advanced/chart-svg-utils');

const VARIANT = getParamScalar('chart_variant', 'horizontal_bar');

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

function buildHorizontalBarModel() {
  const sourceName = 'horizontalBarRows';
  const items = bucketTailToOther(
    withPalette(
      sortDesc(
        getSourceRows(sourceName).map((row) => ({
          label: truncateLabel(toStringValue(row.category_label), 18),
          value: toNumber(row.metric_value),
        })),
        'value',
      ),
    ),
    {valueKey: 'value'},
  );
  return {
    chartVariant: 'horizontal_bar',
    title: 'Horizontal Bar',
    helpBody: 'Ranked category comparison with direct labels. Tail categories are bucketed into Other when the legend cap is exceeded.',
    freshnessHtml: buildFreshnessHtml('Ranked comparison rows'),
    legendMode: 'inline_share',
    legendItems: items.map((item) => ({
      label: item.label,
      color: item.color,
      shareText: formatPercent((item.value / Math.max(1, sumBy(items, 'value'))) * 100),
    })),
    rows: items,
    dataLength: items.length,
    status: buildStatus([sourceName], items.length),
    tooltipItems: items.map((item) => ({
      id: safeId(item.label),
      title: item.label,
      rows: [{label: 'Value', value: formatCompact(item.value)}],
    })),
  };
}

function buildGroupedBarModel() {
  const sourceName = 'groupedBarRows';
  const rows = getSourceRows(sourceName).map((row) => ({
    category: truncateLabel(toStringValue(row.category_label), 14),
    series: toStringValue(row.series_label),
    value: toNumber(row.metric_value),
  }));
  const seriesKeys = [...new Set(rows.map((row) => row.series))];
  const categoryKeys = [...new Set(rows.map((row) => row.category))];
  const seriesColors = Object.fromEntries(seriesKeys.map((key, index) => [key, HOUSE_STYLE.colors.data[Object.keys(HOUSE_STYLE.colors.data)[index] || 'primary'] || HOUSE_STYLE.colors.data.primary]));
  return {
    chartVariant: 'grouped_bar',
    title: 'Grouped Bar',
    helpBody: 'Side-by-side comparison for summable subcategories. Keep category count low and use consistent color semantics.',
    freshnessHtml: buildFreshnessHtml('Grouped comparison rows'),
    legendMode: 'standard',
    legendItems: seriesKeys.map((key) => ({label: key, color: seriesColors[key]})),
    rows,
    seriesKeys,
    categoryKeys,
    seriesColors,
    tooltipItems: rows.map((row) => ({
      id: safeId(`${row.category}_${row.series}`),
      title: `${row.category} · ${row.series}`,
      rows: [{label: 'Value', value: formatCompact(row.value)}],
    })),
    dataLength: rows.length,
    status: buildStatus([sourceName], rows.length),
  };
}

function buildNormalizedStackModel() {
  const sourceName = 'normalizedStackRows';
  const rows = getSourceRows(sourceName).map((row) => ({
    bucket: truncateLabel(toStringValue(row.bucket_label), 12),
    segment: toStringValue(row.segment_label),
    value: toNumber(row.metric_value),
  }));
  const bucketKeys = [...new Set(rows.map((row) => row.bucket))];
  const segmentKeys = [...new Set(rows.map((row) => row.segment))];
  const segmentColors = Object.fromEntries(segmentKeys.map((key, index) => [key, HOUSE_STYLE.colors.data[Object.keys(HOUSE_STYLE.colors.data)[index] || 'primary'] || HOUSE_STYLE.colors.data.primary]));
  const totals = Object.fromEntries(bucketKeys.map((bucket) => [bucket, sumBy(rows.filter((row) => row.bucket === bucket), 'value')]));
  const stacks = bucketKeys.map((bucket) => {
    let running = 0;
    return {
      bucket,
      segments: segmentKeys.map((segment) => {
        const match = rows.find((row) => row.bucket === bucket && row.segment === segment);
        const value = match ? match.value : 0;
        const share = totals[bucket] > 0 ? (value / totals[bucket]) * 100 : 0;
        const start = running;
        const end = running + share;
        running = end;
        return {
          segment,
          value,
          share,
          start,
          end,
          color: segmentColors[segment],
        };
      }).filter((segment) => segment.value > 0),
    };
  });
  return {
    chartVariant: 'stacked_100',
    title: '100% Stacked Bar',
    helpBody: 'Normalized stacked comparison by bucket. Use only for parts of a common whole; do not use for non-summable metrics.',
    freshnessHtml: buildFreshnessHtml('Normalized contribution rows'),
    legendMode: 'standard',
    legendItems: segmentKeys.map((key) => ({label: key, color: segmentColors[key]})),
    stacks,
    tooltipItems: stacks.flatMap((bucket) => bucket.segments.map((segment) => ({
      id: safeId(`${bucket.bucket}_${segment.segment}`),
      title: `${bucket.bucket} · ${segment.segment}`,
      rows: [
        {label: 'Value', value: formatCompact(segment.value)},
        {label: 'Share', value: formatPercent(segment.share)},
      ],
    }))),
    dataLength: stacks.length,
    status: buildStatus([sourceName], stacks.length),
  };
}

function buildHeatmapModel() {
  const sourceName = 'heatmapRows';
  const rows = getSourceRows(sourceName).map((row) => ({
    rowLabel: truncateLabel(toStringValue(row.row_label), 14),
    colLabel: truncateLabel(toStringValue(row.col_label), 10),
    value: toNumber(row.metric_value),
  }));
  return {
    chartVariant: 'heatmap',
    title: 'Heatmap',
    helpBody: 'Matrix comparison for pattern-first reading. If exact values dominate the task, move the problem to a table instead.',
    freshnessHtml: buildFreshnessHtml('Matrix comparison rows'),
    legendMode: 'standard',
    legendItems: [
      {label: 'Low', color: '#DCE8FA'},
      {label: 'Mid', color: '#7AA7F0'},
      {label: 'High', color: HOUSE_STYLE.colors.data.primary},
    ],
    rows,
    rowKeys: [...new Set(rows.map((row) => row.rowLabel))],
    colKeys: [...new Set(rows.map((row) => row.colLabel))],
    tooltipItems: rows.map((row) => ({
      id: safeId(`${row.rowLabel}_${row.colLabel}`),
      title: `${row.rowLabel} · ${row.colLabel}`,
      rows: [{label: 'Value', value: formatCompact(row.value)}],
    })),
    dataLength: rows.length,
    status: buildStatus([sourceName], rows.length),
  };
}

function buildWaterfallModel() {
  const sourceName = 'waterfallRows';
  const rows = getSourceRows(sourceName)
    .map((row) => ({
      sortOrder: toNumber(row.sort_order),
      label: truncateLabel(toStringValue(row.step_label), 18),
      delta: toNumber(row.delta_value),
      stepKind: toStringValue(row.step_kind, 'delta'),
    }))
    .sort((left, right) => left.sortOrder - right.sortOrder);

  let running = 0;
  const steps = rows.map((row) => {
    if (row.stepKind === 'absolute') {
      const absoluteStep = {
        label: row.label,
        kind: row.stepKind,
        start: 0,
        end: row.delta,
        delta: row.delta,
      };
      running = row.delta;
      return absoluteStep;
    }
    const step = {
      label: row.label,
      kind: row.stepKind,
      start: running,
      end: running + row.delta,
      delta: row.delta,
    };
    running = step.end;
    return step;
  });

  return {
    chartVariant: 'waterfall',
    title: 'Waterfall',
    helpBody: 'Ordered contribution bridge with explicit positive and negative steps. Keep running totals obvious and connector lines restrained.',
    freshnessHtml: buildFreshnessHtml('Waterfall bridge rows'),
    legendMode: 'standard',
    legendItems: [
      {label: 'Increase', color: HOUSE_STYLE.colors.semantic.ok},
      {label: 'Decrease', color: HOUSE_STYLE.colors.semantic.critical},
      {label: 'Absolute', color: HOUSE_STYLE.colors.data.primary},
    ],
    steps,
    tooltipItems: steps.map((step) => ({
      id: safeId(step.label),
      title: step.label,
      rows: [
        {label: 'Delta', value: formatCompact(step.delta)},
        {label: 'Range', value: `${formatCompact(step.start)} → ${formatCompact(step.end)}`},
      ],
    })),
    dataLength: steps.length,
    status: buildStatus([sourceName], steps.length),
  };
}

function buildVariantModel() {
  if (VARIANT === 'grouped_bar') return buildGroupedBarModel();
  if (VARIANT === 'stacked_100') return buildNormalizedStackModel();
  if (VARIANT === 'heatmap') return buildHeatmapModel();
  if (VARIANT === 'waterfall') return buildWaterfallModel();
  return buildHorizontalBarModel();
}

function renderHorizontalBars(model, width, height) {
  const labelWidth = 120;
  const valueWidth = 56;
  const rowHeight = Math.max(26, Math.floor(height / Math.max(1, model.rows.length)));
  const barWidth = width - labelWidth - valueWidth - 24;
  const maxValue = maxOr(model.rows.map((item) => item.value), 1);

  const rows = model.rows.map((item, index) => {
    const y = index * rowHeight + 18;
    const fillWidth = Math.max(4, (item.value / maxValue) * barWidth);
    return `
      <text x="0" y="${y}" font-size="12" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${item.label}</text>
      <rect x="${labelWidth}" y="${y - 10}" width="${barWidth}" height="14" fill="${HOUSE_STYLE.colors.surface.line}" rx="0"></rect>
      <rect data-id="${safeId(item.label)}" x="${labelWidth}" y="${y - 10}" width="${fillWidth}" height="14" fill="${item.color}" rx="0"></rect>
      <text x="${labelWidth + fillWidth + 6}" y="${y}" font-size="12" font-weight="700" fill="${HOUSE_STYLE.colors.text.strong}">${formatCompact(item.value)}</text>
    `;
  }).join('');

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${rows}</svg>`;
}

function renderGroupedBars(model, width, height) {
  const layout = buildBandLayout(model.categoryKeys, 40, width - 12, 24);
  const innerBand = Math.max(10, (layout.bandwidth - 10) / Math.max(1, model.seriesKeys.length));
  const maxValue = maxOr(model.rows.map((row) => row.value), 1);
  const yScale = linearScale(0, maxValue, height - 28, 16);

  const bars = model.rows.map((row) => {
    const categoryX = layout.position(row.category);
    const seriesIndex = model.seriesKeys.indexOf(row.series);
    const x = categoryX + seriesIndex * innerBand;
    const y = yScale(row.value);
    const barHeight = height - 28 - y;
    return `
      <rect data-id="${safeId(`${row.category}_${row.series}`)}" x="${x}" y="${y}" width="${innerBand - 4}" height="${barHeight}" fill="${model.seriesColors[row.series]}" rx="0"></rect>
    `;
  }).join('');

  const labels = model.categoryKeys.map((key) => `
    <text x="${layout.position(key) + layout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${key}</text>
  `).join('');

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <line x1="34" x2="${width - 12}" y1="${height - 22}" y2="${height - 22}" stroke="${HOUSE_STYLE.colors.surface.hairline}" stroke-width="1"></line>
    ${bars}
    ${labels}
  </svg>`;
}

function renderNormalizedStack(model, width, height) {
  const layout = buildBandLayout(model.stacks.map((stack) => stack.bucket), 48, width - 12, 24);
  const barHeight = Math.max(16, height - 44);
  const bars = model.stacks.map((stack) => {
    const x = layout.position(stack.bucket);
    const segments = stack.segments.map((segment) => {
      const segX = x + (segment.start / 100) * layout.bandwidth;
      const segWidth = Math.max(2, ((segment.end - segment.start) / 100) * layout.bandwidth);
      const label = segment.share >= 18 ? `<text x="${segX + segWidth / 2}" y="${barHeight / 2 + 8}" text-anchor="middle" font-size="11" font-weight="800" fill="#F9FAFB">${formatPercent(segment.share, 0)}</text>` : '';
      return `
        <rect data-id="${safeId(`${stack.bucket}_${segment.segment}`)}" x="${segX}" y="18" width="${segWidth}" height="${barHeight}" fill="${segment.color}" rx="0"></rect>
        ${label}
      `;
    }).join('');
    return `
      ${segments}
      <text x="${x + layout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${stack.bucket}</text>
    `;
  }).join('');
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${bars}</svg>`;
}

function renderHeatmap(model, width, height) {
  const rowLayout = buildBandLayout(model.rowKeys, 96, height - 12, 10);
  const colLayout = buildBandLayout(model.colKeys, 96, width - 12, 10);
  const maxValue = maxOr(model.rows.map((row) => row.value), 1);

  const colorFor = (value) => {
    const t = clamp(value / Math.max(1, maxValue), 0, 1);
    const blue = 220 - Math.round(80 * t);
    return `rgb(${43 + Math.round(20 * t)}, ${117 + Math.round(20 * t)}, ${blue})`;
  };

  const cells = model.rows.map((row) => {
    const x = colLayout.position(row.colLabel);
    const y = rowLayout.position(row.rowLabel);
    return `
      <rect data-id="${safeId(`${row.rowLabel}_${row.colLabel}`)}" x="${x}" y="${y}" width="${colLayout.bandwidth}" height="${rowLayout.bandwidth}" fill="${colorFor(row.value)}" rx="0"></rect>
      <text x="${x + colLayout.bandwidth / 2}" y="${y + rowLayout.bandwidth / 2 + 4}" text-anchor="middle" font-size="11" font-weight="800" fill="#F9FAFB">${formatInteger(row.value)}</text>
    `;
  }).join('');

  const rowLabels = model.rowKeys.map((key) => `
    <text x="0" y="${rowLayout.position(key) + rowLayout.bandwidth / 2 + 4}" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${key}</text>
  `).join('');
  const colLabels = model.colKeys.map((key) => `
    <text x="${colLayout.position(key) + colLayout.bandwidth / 2}" y="14" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${key}</text>
  `).join('');

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${rowLabels}${colLabels}${cells}</svg>`;
}

function renderWaterfall(model, width, height) {
  const layout = buildBandLayout(model.steps.map((step) => step.label), 32, width - 12, 18);
  const maxValue = maxOr(model.steps.flatMap((step) => [step.start, step.end]), 1);
  const minValue = Math.min(0, ...model.steps.flatMap((step) => [step.start, step.end]));
  const yScale = linearScale(minValue, maxValue, height - 30, 18);

  const bars = model.steps.map((step, index) => {
    const x = layout.position(step.label);
    const y = yScale(Math.max(step.start, step.end));
    const barHeight = Math.max(2, Math.abs(yScale(step.start) - yScale(step.end)));
    const fill = step.kind === 'absolute'
      ? HOUSE_STYLE.colors.data.primary
      : step.delta >= 0
        ? HOUSE_STYLE.colors.semantic.ok
        : HOUSE_STYLE.colors.semantic.critical;
    const connector = index < model.steps.length - 1
      ? `<line x1="${x + layout.bandwidth}" x2="${layout.position(model.steps[index + 1].label)}" y1="${yScale(step.end)}" y2="${yScale(step.end)}" stroke="${HOUSE_STYLE.colors.surface.hairline}" stroke-dasharray="4 4"></line>`
      : '';
    return `
      ${connector}
      <rect data-id="${safeId(step.label)}" x="${x}" y="${y}" width="${layout.bandwidth}" height="${barHeight}" fill="${fill}" rx="0"></rect>
      <text x="${x + layout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="10" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${step.label}</text>
    `;
  }).join('');

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <line x1="24" x2="${width - 12}" y1="${yScale(0)}" y2="${yScale(0)}" stroke="${HOUSE_STYLE.colors.surface.hairline}"></line>
    ${bars}
  </svg>`;
}

const model = buildVariantModel();

module.exports = {
  chartVariant: VARIANT,
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
      function legend(items) {
        if (!items || items.length <= 1) return '';
        return `<div style="height:32px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;overflow:hidden;">${items.slice(0, 6).map((item) => `<div style="display:flex;align-items:center;gap:6px;min-width:0;"><span style="width:9px;height:9px;border-radius:999px;background:${esc(item.color || '#2B75E2')};"></span><span style="font-size:12px;line-height:14px;color:#667085;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(item.label)}${item.shareText ? ` · ${esc(item.shareText)}` : ''}</span></div>`).join('')}</div>`;
      }
      function horizontal(rows, width, height) {
        const safeRows = (rows || []).slice(0, 10);
        const labelW = Math.min(160, Math.max(96, Math.floor(width * 0.32)));
        const valueW = 62;
        const maxValue = Math.max(1, ...safeRows.map((row) => Number(row.value) || 0));
        const rowH = Math.max(24, Math.floor(height / Math.max(1, safeRows.length)));
        return `<svg data-qa-axis-origin="zero" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;overflow:visible;">${safeRows.map((row, index) => {
          const y = index * rowH + rowH / 2;
          const barW = Math.max(2, (Number(row.value) || 0) / maxValue * (width - labelW - valueW - 18));
          const id = row.id || row.label;
          return `<text x="0" y="${(y + 4).toFixed(1)}" font-size="12" font-weight="700" fill="#667085">${esc(row.label)}</text><rect x="${labelW}" y="${(y - 7).toFixed(1)}" width="${Math.max(1, width - labelW - valueW - 18).toFixed(1)}" height="14" fill="#F2F4F7"></rect><rect data-id="${esc(id)}" x="${labelW}" y="${(y - 7).toFixed(1)}" width="${barW.toFixed(1)}" height="14" fill="${esc(row.color || '#2B75E2')}"></rect><text x="${(labelW + barW + 6).toFixed(1)}" y="${(y + 4).toFixed(1)}" font-size="12" font-weight="800" fill="#111827">${fmt(row.value)}</text>`;
        }).join('')}</svg>`;
      }
      function verticalGrouped(model, width, height) {
        const rows = (model.rows || []).slice(0, 24);
        const categories = model.categoryKeys || [];
        const series = model.seriesKeys || [];
        const maxValue = Math.max(1, ...rows.map((row) => Number(row.value) || 0));
        const m = {l: 42, r: 16, t: 12, b: 30};
        const plotW = Math.max(1, width - m.l - m.r);
        const plotH = Math.max(1, height - m.t - m.b);
        const groupW = plotW / Math.max(1, categories.length);
        const barW = Math.max(6, (groupW - 8) / Math.max(1, series.length) - 3);
        const guides = [0, 0.5, 1].map((frac) => {
          const value = maxValue * frac;
          const y = m.t + plotH - frac * plotH;
          return `<line x1="${m.l}" y1="${y.toFixed(1)}" x2="${m.l + plotW}" y2="${y.toFixed(1)}" stroke="#E4E7EC" stroke-dasharray="4 4"></line><text x="${m.l - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#98A2B3">${fmt(value)}</text>`;
        }).join('');
        const bars = rows.map((row) => {
          const categoryIndex = Math.max(0, categories.indexOf(row.category));
          const seriesIndex = Math.max(0, series.indexOf(row.series));
          const x = m.l + categoryIndex * groupW + 4 + seriesIndex * (barW + 3);
          const h = ((Number(row.value) || 0) / maxValue) * plotH;
          const y = m.t + plotH - h;
          const color = (model.seriesColors && model.seriesColors[row.series]) || '#2B75E2';
          return `<rect data-id="${esc(`${row.category}_${row.series}`)}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${esc(color)}"></rect>`;
        }).join('');
        const labels = categories.map((key, index) => `<text x="${(m.l + index * groupW + groupW / 2).toFixed(1)}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="#667085">${esc(key)}</text>`).join('');
        return `<svg data-qa-axis-origin="zero" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;overflow:visible;">${guides}<line x1="${m.l}" y1="${m.t + plotH}" x2="${m.l + plotW}" y2="${m.t + plotH}" stroke="#D0D5DD"></line>${bars}${labels}</svg>`;
      }
      function stack(model, width, height) {
        const stacks = model.stacks || [];
        const rowH = Math.max(28, Math.floor(height / Math.max(1, stacks.length)));
        return `<svg data-qa-axis-origin="zero" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;overflow:visible;">${stacks.map((bucket, index) => {
          const y = index * rowH + 8;
          const labelW = 70;
          const plotW = Math.max(1, width - labelW - 8);
          const segments = (bucket.segments || []).map((segment) => {
            const x = labelW + (Number(segment.start) || 0) / 100 * plotW;
            const w = Math.max(2, ((Number(segment.end) || 0) - (Number(segment.start) || 0)) / 100 * plotW);
            const label = Number(segment.share || 0) >= 18 ? `<text x="${(x + w / 2).toFixed(1)}" y="${y + 14}" text-anchor="middle" font-size="11" font-weight="800" fill="#fff">${Math.round(segment.share)}%</text>` : '';
            return `<rect data-id="${esc(`${bucket.bucket}_${segment.segment}`)}" x="${x.toFixed(1)}" y="${y}" width="${w.toFixed(1)}" height="18" fill="${esc(segment.color || '#2B75E2')}"></rect>${label}`;
          }).join('');
          return `<text x="0" y="${y + 14}" font-size="12" font-weight="700" fill="#667085">${esc(bucket.bucket)}</text>${segments}`;
        }).join('')}</svg>`;
      }

      const rawWidth = Number(options && options.width) || 0;
      const rawHeight = Number(options && options.height) || 0;
      const width = rawWidth > 0 ? rawWidth : 640;
      const height = rawHeight > 0 ? rawHeight : 360;
      const dense = width < 460 || height < 260;
      const titleSize = dense ? 18 : 20;
      const bodyH = Math.max(150, height - titleSize - 62 - ((currentModel.legendItems || []).length > 1 ? 32 : 0));
      const empty = currentModel.status && currentModel.status !== 'ok';
      let body;
      if (empty) {
        body = `<div style="flex:1;display:flex;align-items:center;justify-content:center;font-size:28px;line-height:34px;font-weight:800;color:#111827;">${currentModel.status === 'unavailable' ? 'SOURCE MISSING' : 'NO DATA'}</div>`;
      } else if (currentModel.chartVariant === 'grouped_bar') {
        body = verticalGrouped(currentModel, width - 28, bodyH);
      } else if (currentModel.chartVariant === 'stacked_100') {
        body = stack(currentModel, width - 28, bodyH);
      } else if (currentModel.chartVariant === 'heatmap') {
        body = horizontal((currentModel.rows || []).map((row) => ({id: `${row.rowLabel}_${row.colLabel}`, label: `${row.rowLabel} / ${row.colLabel}`, value: row.value, color: '#2B75E2'})), width - 28, bodyH);
      } else if (currentModel.chartVariant === 'waterfall') {
        body = horizontal((currentModel.steps || []).map((step) => ({id: step.label, label: step.label, value: Math.abs(Number(step.delta) || 0), color: Number(step.delta) < 0 ? '#B3261E' : '#0B8043'})), width - 28, bodyH);
      } else {
        body = horizontal(currentModel.rows || [], width - 28, bodyH);
      }

      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:100%;height:100%;padding:${dense ? 10 : 12}px ${dense ? 12 : 14}px;background:transparent;border:none;font-family:Inter,Arial,sans-serif;color:#111827;display:flex;flex-direction:column;gap:8px;overflow:hidden;">
          <div style="display:flex;align-items:center;gap:8px;min-width:0;">
            <div style="font-size:${titleSize}px;line-height:${titleSize + 2}px;color:#5F6368;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(currentModel.title)}</div>
            <div data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:${dense ? 16 : 18}px;height:${dense ? 16 : 18}px;border-radius:999px;background:#F2F4F7;color:#667085;font-size:${dense ? 11 : 12}px;line-height:1;font-weight:800;cursor:help;flex:0 0 auto;">?</div>
          </div>
          ${legend(currentModel.legendItems || [])}
          ${currentModel.freshnessHtml || ''}
          ${body}
        </div>
      `);
    },
  }),
  tooltip: {
    renderer: Editor.wrapFn({
      args: [{
        title: model.title,
        helpBody: model.helpBody,
        helpSource: 'datalens-advanced-editor comparison-flow family asset',
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
        return Editor.generateHtml(`<div style="min-width:220px;max-width:360px;padding:10px 12px;border-radius:10px;background:#fff;color:#111827;font-family:Inter,Arial,sans-serif;font-size:12px;line-height:16px;"><div style="font-weight:800;">${esc(match.title)}</div>${rows}</div>`);
      },
    }),
  },
};
