const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {
  bucketTailToOther,
  formatCompact,
  formatPercent,
  getParamScalar,
  getSourceRows,
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

const VARIANT = getParamScalar('chart_variant', 'pie');

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

function polarToCartesian(centerX, centerY, radius, angleInDegrees) {
  const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
  return {
    x: centerX + (radius * Math.cos(angleInRadians)),
    y: centerY + (radius * Math.sin(angleInRadians)),
  };
}

function describeArc(centerX, centerY, radius, startAngle, endAngle, innerRadius = 0) {
  const start = polarToCartesian(centerX, centerY, radius, endAngle);
  const end = polarToCartesian(centerX, centerY, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';
  if (!innerRadius) {
    return [
      `M ${centerX} ${centerY}`,
      `L ${start.x} ${start.y}`,
      `A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`,
      'Z',
    ].join(' ');
  }
  const innerStart = polarToCartesian(centerX, centerY, innerRadius, endAngle);
  const innerEnd = polarToCartesian(centerX, centerY, innerRadius, startAngle);
  return [
    `M ${start.x} ${start.y}`,
    `A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 1 ${innerStart.x} ${innerStart.y}`,
    'Z',
  ].join(' ');
}

function buildSegmentModel(variant) {
  const sourceName = 'segmentRows';
  const segments = bucketTailToOther(
    withPalette(
      sortDesc(
        getSourceRows(sourceName).map((row) => ({
          label: truncateLabel(toStringValue(row.category_label), 14),
          value: toNumber(row.metric_value),
        })),
        'value',
      ),
    ),
    {valueKey: 'value'},
  );
  const total = Math.max(1, sumBy(segments, 'value'));
  let runningAngle = 0;
  const slices = segments.map((segment) => {
    const share = (segment.value / total) * 100;
    const angle = (segment.value / total) * 360;
    const slice = {
      ...segment,
      share,
      startAngle: runningAngle,
      endAngle: runningAngle + angle,
      id: safeId(segment.label),
    };
    runningAngle += angle;
    return slice;
  });
  return {
    chartVariant: variant,
    title: variant === 'donut' ? 'Donut Chart' : 'Pie Chart',
    helpBody: variant === 'donut'
      ? 'Use donut when the center can carry a useful summary without hiding slice meaning.'
      : 'Use pie only for a few clearly differentiated shares and direct-label where possible.',
    freshnessHtml: buildFreshnessHtml('Segment share rows'),
    legendMode: 'inline',
    legendItems: slices.map((slice) => ({
      label: slice.label,
      color: slice.color,
      shareText: formatPercent(slice.share),
    })),
    slices,
    total,
    tooltipItems: slices.map((slice) => ({
      id: slice.id,
      title: slice.label,
      rows: [
        {label: 'Value', value: formatCompact(slice.value)},
        {label: 'Share', value: formatPercent(slice.share)},
      ],
    })),
    dataLength: slices.length,
    status: buildStatus([sourceName], slices.length),
  };
}

function buildTreemapModel() {
  const sourceName = 'treemapRows';
  const slices = withPalette(
    sortDesc(
      getSourceRows(sourceName).map((row) => ({
        parent: toStringValue(row.parent_label),
        label: truncateLabel(toStringValue(row.child_label), 14),
        value: toNumber(row.metric_value),
      })),
      'value',
    ),
  );
  return {
    chartVariant: 'treemap',
    title: 'Treemap',
    helpBody: 'Use treemap only when hierarchy is real and area can honestly carry the message.',
    freshnessHtml: buildFreshnessHtml('Hierarchy share rows'),
    legendMode: 'standard',
    legendItems: slices.map((slice) => ({label: slice.label, color: slice.color})),
    slices,
    tooltipItems: slices.map((slice) => ({
      id: safeId(slice.label),
      title: slice.label,
      rows: [{label: 'Value', value: formatCompact(slice.value)}],
    })),
    dataLength: slices.length,
    status: buildStatus([sourceName], slices.length),
  };
}

function buildVariantModel() {
  if (VARIANT === 'donut') return buildSegmentModel('donut');
  if (VARIANT === 'treemap') return buildTreemapModel();
  return buildSegmentModel('pie');
}

function renderPieLike(model, width, height) {
  const radius = Math.min(width, height) / 2 - 24;
  const centerX = width / 2;
  const centerY = height / 2;
  const innerRadius = model.chartVariant === 'donut' ? radius * 0.52 : 0;
  const paths = model.slices.map((slice) => `
    <path data-id="${slice.id}" d="${describeArc(centerX, centerY, radius, slice.startAngle, slice.endAngle, innerRadius)}" fill="${slice.color}"></path>
  `).join('');

  const labels = model.slices.map((slice) => {
    const midAngle = (slice.startAngle + slice.endAngle) / 2;
    const labelRadius = model.chartVariant === 'donut' ? radius + 18 : radius + 14;
    const point = polarToCartesian(centerX, centerY, labelRadius, midAngle);
    return `<text x="${point.x}" y="${point.y}" text-anchor="middle" font-size="11" font-weight="800" fill="${HOUSE_STYLE.colors.text.strong}">${slice.label} · ${formatPercent(slice.share, 0)}</text>`;
  }).join('');

  const centerLabel = model.chartVariant === 'donut'
    ? `<text x="${centerX}" y="${centerY}" text-anchor="middle" font-size="18" font-weight="800" fill="${HOUSE_STYLE.colors.text.strong}">${formatCompact(model.total)}</text>
       <text x="${centerX}" y="${centerY + 18}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">Total</text>`
    : '';

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    ${paths}
    ${labels}
    ${centerLabel}
  </svg>`;
}

function renderTreemap(model, width, height) {
  const total = Math.max(1, sumBy(model.slices, 'value'));
  let cursorX = 0;
  const tiles = model.slices.map((slice) => {
    const tileWidth = (slice.value / total) * width;
    const tile = `
      <rect data-id="${safeId(slice.label)}" x="${cursorX}" y="0" width="${Math.max(24, tileWidth)}" height="${height}" fill="${slice.color}" fill-opacity="0.85"></rect>
      <text x="${cursorX + 12}" y="24" font-size="12" font-weight="800" fill="#F9FAFB">${slice.label}</text>
      <text x="${cursorX + 12}" y="42" font-size="11" font-weight="700" fill="#F9FAFB">${formatCompact(slice.value)}</text>
    `;
    cursorX += tileWidth;
    return tile;
  }).join('');
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${tiles}</svg>`;
}

const model = buildVariantModel();

module.exports = {
  chartVariant: model.chartVariant,
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, currentModel) {
      const width = Math.max(420, Number(options?.width) || 640);
      const height = Math.max(320, Number(options?.height) || 380);
      const esc = (value) => String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
      const fmt = (value) => {
        const number = Number(value);
        if (!Number.isFinite(number)) return '0';
        return String(Math.round(number)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      };
      const pct = (value, digits = 0) => {
        const number = Number(value);
        if (!Number.isFinite(number)) return '0%';
        return `${number.toFixed(digits)}%`;
      };
      const safe = (value) => String(value == null ? 'item' : value).replace(/[^\w-]+/g, '_');
      const legend = (items, inline) => (items || []).slice(0, inline ? 6 : 8).map((item) => `
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:#667085;white-space:nowrap;">
          <span style="width:8px;height:8px;background:${esc(item.color)};display:inline-block;"></span>
          ${esc(item.label)}${inline && item.shareText ? ` <b style="color:#111827;">${esc(item.shareText)}</b>` : ''}
        </span>
      `).join('');
      const polar = (cx, cy, radius, angle) => {
        const radians = (angle - 90) * Math.PI / 180;
        return {x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians)};
      };
      const arc = (cx, cy, radius, startAngle, endAngle, innerRadius) => {
        const start = polar(cx, cy, radius, endAngle);
        const end = polar(cx, cy, radius, startAngle);
        const large = endAngle - startAngle <= 180 ? '0' : '1';
        if (!innerRadius) {
          return `M ${cx} ${cy} L ${start.x} ${start.y} A ${radius} ${radius} 0 ${large} 0 ${end.x} ${end.y} Z`;
        }
        const innerStart = polar(cx, cy, innerRadius, endAngle);
        const innerEnd = polar(cx, cy, innerRadius, startAngle);
        return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${large} 0 ${end.x} ${end.y} L ${innerEnd.x} ${innerEnd.y} A ${innerRadius} ${innerRadius} 0 ${large} 1 ${innerStart.x} ${innerStart.y} Z`;
      };
      const pieLike = () => {
        const slices = Array.isArray(currentModel.slices) ? currentModel.slices : [];
        const bodyWidth = width - 32;
        const bodyHeight = Math.max(190, height - 88);
        const radius = Math.max(74, Math.min(bodyWidth, bodyHeight) / 2 - 30);
        const cx = bodyWidth / 2;
        const cy = bodyHeight / 2;
        const inner = currentModel.chartVariant === 'donut' ? radius * 0.52 : 0;
        const paths = slices.map((slice) => `<path data-id="${esc(slice.id)}" d="${arc(cx, cy, radius, Number(slice.startAngle) || 0, Number(slice.endAngle) || 0, inner)}" fill="${esc(slice.color || '#2B75E2')}"></path>`).join('');
        const labels = slices.filter((slice) => Number(slice.share) >= 8).map((slice) => {
          const mid = ((Number(slice.startAngle) || 0) + (Number(slice.endAngle) || 0)) / 2;
          const point = polar(cx, cy, radius + 18, mid);
          return `<text x="${point.x}" y="${point.y}" text-anchor="middle" font-size="11" font-weight="800" fill="#111827">${esc(slice.label)} · ${pct(slice.share)}</text>`;
        }).join('');
        const center = currentModel.chartVariant === 'donut'
          ? `<text x="${cx}" y="${cy}" text-anchor="middle" font-size="18" font-weight="800" fill="#111827">${fmt(currentModel.total)}</text><text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="11" font-weight="700" fill="#667085">Total</text>`
          : '';
        return `<svg width="100%" height="${bodyHeight}" viewBox="0 0 ${bodyWidth} ${bodyHeight}" role="img">${paths}${labels}${center}</svg>`;
      };
      const treemap = () => {
        const slices = Array.isArray(currentModel.slices) ? currentModel.slices : [];
        const bodyWidth = width - 32;
        const bodyHeight = Math.max(190, height - 88);
        const total = Math.max(1, ...[slices.reduce((sum, item) => sum + (Number(item.value) || 0), 0)]);
        let cursor = 0;
        const tiles = slices.map((slice) => {
          const tileWidth = Math.max(28, ((Number(slice.value) || 0) / total) * bodyWidth);
          const html = `
            <rect data-id="${safe(slice.label)}" x="${cursor}" y="0" width="${tileWidth}" height="${bodyHeight}" fill="${esc(slice.color || '#2B75E2')}" fill-opacity="0.85"></rect>
            <text x="${cursor + 12}" y="24" font-size="12" font-weight="800" fill="#F9FAFB">${esc(slice.label)}</text>
            <text x="${cursor + 12}" y="42" font-size="11" font-weight="700" fill="#F9FAFB">${fmt(slice.value)}</text>
          `;
          cursor += tileWidth;
          return html;
        }).join('');
        return `<svg width="100%" height="${bodyHeight}" viewBox="0 0 ${bodyWidth} ${bodyHeight}" role="img">${tiles}</svg>`;
      };
      const state = (title, body) => `
        <div style="height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;color:#98A2B3;text-align:center;">
          <div style="font-size:13px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;">${title}</div>
          <div style="font-size:12px;font-weight:600;">${body}</div>
        </div>
      `;
      const body = currentModel.status === 'unavailable'
        ? state('SOURCE MISSING', 'The required source is not available.')
        : currentModel.status !== 'ok'
          ? state('NO DATA', 'No rows matched the active filters.')
          : currentModel.chartVariant === 'treemap'
            ? treemap()
            : pieLike();
      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:${width}px;height:${height}px;padding:12px 16px 16px;background:transparent;border:none;box-shadow:none;display:flex;flex-direction:column;gap:12px;font-family:Inter,Arial,sans-serif;overflow:hidden;">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;min-width:0;">
              <div style="font-size:18px;line-height:1.1;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5F6368;">${esc(currentModel.title).toUpperCase()}</div>
              <span data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:999px;background:#F3F4F6;color:#5F6368;font-size:11px;font-weight:800;">?</span>
            </div>
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">${legend(currentModel.legendItems, currentModel.legendMode === 'inline')}${currentModel.freshnessHtml || ''}</div>
          </div>
          <div style="flex:1;min-height:0;">${body}</div>
        </div>
      `);
    },
  }),
  tooltip: {
    renderer: Editor.wrapFn({
      args: [{items: model.tooltipItems}],
      fn: function(event, payload) {
        const esc = (value) => String(value == null ? '' : value)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
        const id = event?.target?.closest?.('[data-id]')?.getAttribute('data-id') || event?.target?.getAttribute?.('data-id');
        if (id === 'hint') {
          return `<div style="max-width:280px;padding:10px 12px;background:#FFFFFF;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,0.28);font-family:Inter,Arial,sans-serif;color:#111827;">
            <div style="font-size:13px;font-weight:800;margin-bottom:6px;">Part-to-whole / Hierarchy</div>
            <div style="font-size:12px;line-height:1.35;">Use only when shares or hierarchy are the analytical question.</div>
            <div style="margin-top:6px;font-size:11px;color:#667085;">datalens-advanced-editor part-to-whole family asset</div>
          </div>`;
        }
        if (!id) return null;
        const match = payload.items.find((item) => item.id === id);
        if (!match) return null;
        const rows = (match.rows || []).map((row) => `<div style="display:flex;justify-content:space-between;gap:16px;"><span style="color:#667085;">${esc(row.label)}</span><b>${esc(row.value)}</b></div>`).join('');
        return `<div style="min-width:180px;padding:10px 12px;background:#FFFFFF;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,0.28);font-family:Inter,Arial,sans-serif;color:#111827;font-size:12px;">
          <div style="font-size:13px;font-weight:800;margin-bottom:8px;">${esc(match.title)}</div>
          <div style="display:flex;flex-direction:column;gap:6px;">${rows}</div>
        </div>`;
      },
    }),
  },
};
