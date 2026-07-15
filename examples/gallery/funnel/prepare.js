const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {getSourceRows, toStringValue} = require('../../../templates/advanced/chart-data-utils');
const {renderSourceFreshness} = require('../../../templates/advanced/source-freshness');
const {renderTooltipShell} = require('../../../templates/advanced/tooltip');
const {
  buildFunnelTooltipItems,
  normalizeFunnelStages,
  renderFunnelStageBars,
} = require('../../../templates/advanced/funnel-bars');

function hasSourceLoaded(name) {
  const direct = Editor.getLoadedData(name);
  if (direct !== undefined && direct !== null) {
    return true;
  }
  const loaded = Editor.getLoadedData() || {};
  return Object.prototype.hasOwnProperty.call(loaded, name);
}

const sourceName = 'stageRows';
const stages = normalizeFunnelStages(getSourceRows(sourceName));
const status = !hasSourceLoaded(sourceName) ? 'unavailable' : stages.length ? 'ok' : 'empty';
const tooltipItems = buildFunnelTooltipItems(stages);

module.exports = {
  render: Editor.wrapFn({
    args: [{
      stages,
      status,
      tooltipItems,
      freshnessHtml: renderSourceFreshness({
        sourceLabel: 'Focused funnel stages',
        freshnessLabel: 'Static demo data',
        updatedAt: '2026-01-31 09:00 UTC',
      }),
    }],
    fn: function(options, model) {
      const width = Math.max(420, Number(options?.width) || 640);
      const height = Math.max(300, Number(options?.height) || 360);
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
      const header = () => `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:8px;min-width:0;">
            <div style="font-size:18px;line-height:1.1;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5F6368;">FUNNEL SNAPSHOT</div>
            <span data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:999px;background:#F3F4F6;color:#5F6368;font-size:11px;font-weight:800;">?</span>
          </div>
          ${model.freshnessHtml || ''}
        </div>
      `;
      const state = (title, body) => `
        <div style="height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;color:#98A2B3;text-align:center;">
          <div style="font-size:13px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;">${title}</div>
          <div style="font-size:12px;font-weight:600;">${body}</div>
        </div>
      `;
      const renderBars = () => {
        const stagesList = Array.isArray(model.stages) ? model.stages : [];
        const bodyWidth = width - 32;
        const bodyHeight = Math.max(170, height - 72);
        const maxValue = Math.max(1, ...stagesList.map((stage) => Number(stage.metricValue) || 0));
        const rowHeight = Math.max(28, Math.floor(bodyHeight / Math.max(1, stagesList.length)));
        const labelWidth = 132;
        const valueWidth = 70;
        const barWidth = Math.max(160, bodyWidth - labelWidth - valueWidth - 24);
        const rowsHtml = stagesList.map((stage, index) => {
          const y = index * rowHeight + 18;
          const id = esc(stage.id || stage.stageLabel || `stage_${index}`);
          const fillWidth = Math.max(8, ((Number(stage.metricValue) || 0) / maxValue) * barWidth);
          const conversion = index === 0 ? '100%' : `${Math.round(Number(stage.conversionRate) || 0)}%`;
          return `
            <text x="0" y="${y}" font-size="12" font-weight="800" letter-spacing="0.08em" fill="#667085">${esc(stage.stageLabel).toUpperCase()}</text>
            <text x="0" y="${y + 14}" font-size="11" font-weight="600" fill="#98A2B3">${conversion}</text>
            <rect x="${labelWidth}" y="${y - 11}" width="${barWidth}" height="16" fill="#EAECF0"></rect>
            <rect data-id="${id}" x="${labelWidth}" y="${y - 11}" width="${fillWidth}" height="16" fill="#2B75E2"></rect>
            <text x="${labelWidth + barWidth + 12}" y="${y}" font-size="12" font-weight="800" fill="#111827">${fmt(stage.metricValue)}</text>
          `;
        }).join('');
        return `<svg width="100%" height="${bodyHeight}" viewBox="0 0 ${bodyWidth} ${bodyHeight}" role="img">${rowsHtml}</svg>`;
      };
      const body = model.status === 'unavailable'
        ? state('SOURCE MISSING', 'The required source is not available.')
        : model.status !== 'ok'
          ? state('NO DATA', 'No rows matched the active filters.')
          : renderBars();
      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:${width}px;height:${height}px;padding:12px 16px 16px;background:transparent;border:none;box-shadow:none;display:flex;flex-direction:column;gap:12px;font-family:Inter,Arial,sans-serif;overflow:hidden;">
          ${header()}
          <div style="flex:1;min-height:0;">${body}</div>
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
            <div style="font-size:13px;font-weight:800;margin-bottom:6px;">Funnel Snapshot</div>
            <div style="font-size:12px;line-height:1.35;">Use when one funnel alone is the whole analytical object.</div>
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
