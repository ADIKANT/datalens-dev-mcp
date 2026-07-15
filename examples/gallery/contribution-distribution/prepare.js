const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {
  formatCompact,
  formatPercent,
  getSourceRows,
  safeId,
  sumBy,
  toNumber,
  toStringValue,
} = require('../../../templates/advanced/chart-data-utils');
const {renderLegendItems} = require('../../../templates/advanced/legend');
const {renderTooltipShell} = require('../../../templates/advanced/tooltip');
const {HOUSE_STYLE} = require('../../../templates/advanced/style-tokens');
const {buildBandLayout} = require('../../../templates/advanced/chart-svg-utils');

const rawRows = getSourceRows('contributionRows').map((row) => ({
  bucket: toStringValue(row.bucket_label),
  segment: toStringValue(row.category_label),
  value: toNumber(row.metric_value),
}));
const buckets = [...new Set(rawRows.map((row) => row.bucket))];
const segments = [...new Set(rawRows.map((row) => row.segment))];
const segmentColors = {
  Organic: HOUSE_STYLE.colors.data.primary,
  Paid: HOUSE_STYLE.colors.data.accent,
  Other: HOUSE_STYLE.colors.data.other,
};
const stacks = buckets.map((bucket) => {
  const bucketRows = rawRows.filter((row) => row.bucket === bucket);
  const total = Math.max(1, sumBy(bucketRows, 'value'));
  let running = 0;
  return {
    bucket,
    total,
    segments: segments.map((segment) => {
      const match = bucketRows.find((row) => row.segment === segment);
      const value = match ? match.value : 0;
      const share = (value / total) * 100;
      const start = running;
      const end = running + share;
      running = end;
      return {
        segment,
        value,
        share,
        start,
        end,
        color: segmentColors[segment] || HOUSE_STYLE.colors.data.other,
      };
    }).filter((segment) => segment.value > 0),
  };
});
const tooltipItems = stacks.flatMap((bucket) => bucket.segments.map((segment) => ({
  id: safeId(`${bucket.bucket}_${segment.segment}`),
  title: `${bucket.bucket} · ${segment.segment}`,
  rows: [
    {label: 'Value', value: formatCompact(segment.value)},
    {label: 'Share', value: formatPercent(segment.share)},
  ],
})));

function renderStacks(width, height) {
  const layout = buildBandLayout(buckets, 48, width - 12, 24);
  const barHeight = Math.max(18, height - 44);
  const items = stacks.map((bucket) => {
    const x = layout.position(bucket.bucket);
    const segmentsHtml = bucket.segments.map((segment) => {
      const segX = x + (segment.start / 100) * layout.bandwidth;
      const segWidth = Math.max(2, ((segment.end - segment.start) / 100) * layout.bandwidth);
      const label = segment.share >= 18
        ? `<text x="${segX + segWidth / 2}" y="${barHeight / 2 + 8}" text-anchor="middle" font-size="11" font-weight="800" fill="#F9FAFB">${formatPercent(segment.share, 0)}</text>`
        : '';
      return `
        <rect data-id="${safeId(`${bucket.bucket}_${segment.segment}`)}" x="${segX}" y="18" width="${segWidth}" height="${barHeight}" fill="${segment.color}" rx="0"></rect>
        ${label}
      `;
    }).join('');
    return `
      ${segmentsHtml}
      <text x="${x + layout.bandwidth / 2}" y="${height - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${HOUSE_STYLE.colors.text.muted}">${bucket.bucket}</text>
    `;
  }).join('');
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${items}</svg>`;
}

module.exports = {
  render: Editor.wrapFn({
    args: [{
      stacks,
      tooltipItems,
      segments: segments.map((segment) => ({
        label: segment,
        color: segmentColors[segment] || HOUSE_STYLE.colors.data.other,
      })),
    }],
    fn: function(options, data) {
      const width = Math.max(420, Number(options?.width) || 640);
      const height = Math.max(300, Number(options?.height) || 360);
      const esc = (value) => String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
      const pct = (value, digits = 0) => {
        const number = Number(value);
        if (!Number.isFinite(number)) return '0%';
        return `${number.toFixed(digits)}%`;
      };
      const safe = (value) => String(value == null ? 'item' : value).replace(/[^\w-]+/g, '_');
      const legend = (items) => (items || []).map((item) => `
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:#667085;white-space:nowrap;">
          <span style="width:8px;height:8px;background:${esc(item.color)};display:inline-block;"></span>${esc(item.label)}
        </span>
      `).join('');
      const body = () => {
        const stacksList = Array.isArray(data.stacks) ? data.stacks : [];
        const buckets = stacksList.map((stack) => stack.bucket);
        const bodyWidth = width - 32;
        const bodyHeight = Math.max(170, height - 78);
        const left = 28;
        const gap = 24;
        const count = Math.max(1, buckets.length);
        const bandWidth = Math.max(54, (bodyWidth - left - gap * Math.max(0, count - 1)) / count);
        const barHeight = Math.max(130, bodyHeight - 42);
        const items = stacksList.map((bucket, index) => {
          const x = left + index * (bandWidth + gap);
          const segmentsHtml = (bucket.segments || []).map((segment) => {
            const segX = x + (Number(segment.start) || 0) / 100 * bandWidth;
            const segWidth = Math.max(2, ((Number(segment.end) || 0) - (Number(segment.start) || 0)) / 100 * bandWidth);
            const label = Number(segment.share) >= 18
              ? `<text x="${segX + segWidth / 2}" y="${barHeight / 2 + 22}" text-anchor="middle" font-size="11" font-weight="800" fill="#F9FAFB">${pct(segment.share)}</text>`
              : '';
            return `
              <rect data-id="${safe(`${bucket.bucket}_${segment.segment}`)}" x="${segX}" y="18" width="${segWidth}" height="${barHeight}" fill="${esc(segment.color || '#2B75E2')}" rx="0"></rect>
              ${label}
            `;
          }).join('');
          return `
            ${segmentsHtml}
            <text x="${x + bandWidth / 2}" y="${bodyHeight - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="#667085">${esc(bucket.bucket)}</text>
          `;
        }).join('');
        return `<svg data-qa-axis-origin="zero" width="100%" height="${bodyHeight}" viewBox="0 0 ${bodyWidth} ${bodyHeight}" role="img">${items}</svg>`;
      };
      const state = (title, bodyText) => `
        <div style="height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;color:#98A2B3;text-align:center;">
          <div style="font-size:13px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;">${title}</div>
          <div style="font-size:12px;font-weight:600;">${bodyText}</div>
        </div>
      `;
      const bodyHtml = data.stacks && data.stacks.length ? body() : state('NO DATA', 'No rows matched the active filters.');
      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:${width}px;height:${height}px;padding:12px 16px 16px;background:transparent;border:none;box-shadow:none;display:flex;flex-direction:column;gap:12px;font-family:Inter,Arial,sans-serif;overflow:hidden;">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;min-width:0;">
              <div style="font-size:18px;line-height:1.1;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5F6368;">CHANNEL CONTRIBUTION</div>
              <span data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:999px;background:#F3F4F6;color:#5F6368;font-size:11px;font-weight:800;">?</span>
            </div>
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">${legend(data.segments)}</div>
          </div>
          <div style="flex:1;min-height:0;">${bodyHtml}</div>
        </div>
      `);
    },
  }),
  tooltip: {
    renderer: Editor.wrapFn({
      args: [{items: tooltipItems}],
      fn: function(event, payload) {
        const esc = (value) => String(value == null ? '' : value)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
        const id = event?.target?.closest?.('[data-id]')?.getAttribute('data-id') || event?.target?.getAttribute?.('data-id');
        if (id === 'hint') {
          return `<div style="max-width:280px;padding:10px 12px;background:#FFFFFF;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,0.28);font-family:Inter,Arial,sans-serif;color:#111827;">
            <div style="font-size:13px;font-weight:800;margin-bottom:6px;">Channel Contribution</div>
            <div style="font-size:12px;line-height:1.35;">Normalized stacked contribution by bucket. Use only for parts of a common whole.</div>
            <div style="margin-top:6px;font-size:11px;color:#667085;">datalens-advanced-editor focused family asset</div>
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
