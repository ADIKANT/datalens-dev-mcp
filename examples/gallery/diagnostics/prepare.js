const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {
  getSourceRows,
  safeId,
  toStringValue,
} = require('../../../templates/advanced/chart-data-utils');
const {renderSourceFreshness} = require('../../../templates/advanced/source-freshness');
const {renderTooltipShell} = require('../../../templates/advanced/tooltip');
const {HOUSE_STYLE} = require('../../../templates/advanced/style-tokens');

function hasSourceLoaded(name) {
  const direct = Editor.getLoadedData(name);
  if (direct !== undefined && direct !== null) {
    return true;
  }
  const loaded = Editor.getLoadedData() || {};
  return Object.prototype.hasOwnProperty.call(loaded, name);
}

function getToneAppearance(tone) {
  const normalized = toStringValue(tone, 'neutral').trim().toLowerCase();
  if (normalized === 'ok') {
    return {fg: HOUSE_STYLE.colors.semantic.ok, bg: '#E6F4EA'};
  }
  if (normalized === 'warning') {
    return {fg: HOUSE_STYLE.colors.semantic.warning, bg: '#FFF4E5'};
  }
  if (normalized === 'critical') {
    return {fg: HOUSE_STYLE.colors.semantic.critical, bg: '#FDF2F2'};
  }
  return {fg: HOUSE_STYLE.colors.semantic.neutral, bg: '#F3F4F6'};
}

const sourceName = 'actionRows';
const cards = getSourceRows(sourceName).map((row, index) => ({
  id: safeId(`${row.card_label}_${index}`),
  label: toStringValue(row.card_label),
  primary: toStringValue(row.primary_text),
  secondary: toStringValue(row.secondary_text),
  tone: toStringValue(row.state_tone, 'neutral'),
  appearance: getToneAppearance(row.state_tone),
}));
const status = !hasSourceLoaded(sourceName) ? 'unavailable' : cards.length ? 'ok' : 'empty';
const tooltipItems = cards.map((card) => ({
  id: card.id,
  title: card.label,
  rows: [
    {label: 'Primary', value: card.primary},
    {label: 'Context', value: card.secondary},
  ],
}));

function renderSummaryGrid(cardsList, width, height) {
  const cols = Math.min(3, Math.max(1, cardsList.length));
  const rowsCount = Math.ceil(cardsList.length / cols);
  const cardWidth = Math.floor((width - HOUSE_STYLE.spacing.sm * Math.max(0, cols - 1)) / cols);
  const cardHeight = Math.floor((height - HOUSE_STYLE.spacing.sm * Math.max(0, rowsCount - 1)) / Math.max(1, rowsCount));

  return `
    <div style="display:grid;grid-template-columns:repeat(${cols}, minmax(0, 1fr));gap:${HOUSE_STYLE.spacing.sm}px;width:${width}px;height:${height}px;">
      ${cardsList.map((card) => `
        <div
          data-id="${card.id}"
          style="
            min-width:${cardWidth}px;
            min-height:${Math.max(120, cardHeight)}px;
            padding:${HOUSE_STYLE.spacing.md}px;
            display:flex;
            flex-direction:column;
            justify-content:space-between;
            background:${HOUSE_STYLE.colors.surface.muted};
            border:none;
            box-shadow:none;
          "
        >
          <div>
            <div style="display:inline-flex;align-items:center;padding:4px 10px;border-radius:${HOUSE_STYLE.radius.chip}px;background:${card.appearance.bg};color:${card.appearance.fg};font-size:11px;line-height:1.25;font-weight:800;text-transform:uppercase;">${card.label}</div>
            <div style="margin-top:${HOUSE_STYLE.spacing.sm}px;font-size:28px;line-height:1.05;font-weight:800;letter-spacing:-0.03em;color:${HOUSE_STYLE.colors.text.strong};">${card.primary}</div>
          </div>
          <div style="font-size:12px;line-height:1.35;font-weight:600;color:${HOUSE_STYLE.colors.text.muted};">${card.secondary}</div>
        </div>
      `).join('')}
    </div>
  `;
}

module.exports = {
  render: Editor.wrapFn({
    args: [{
      cards,
      status,
      freshnessHtml: renderSourceFreshness({
        sourceLabel: 'Focused summary cards',
        freshnessLabel: 'Static demo data',
        updatedAt: '2026-01-31 09:00 UTC',
      }),
    }],
    fn: function(options, model) {
      const width = Math.max(420, Number(options?.width) || 640);
      const height = Math.max(280, Number(options?.height) || 340);
      const esc = (value) => String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
      const state = (title, body) => `
        <div style="height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;color:#98A2B3;text-align:center;">
          <div style="font-size:13px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;">${title}</div>
          <div style="font-size:12px;font-weight:600;">${body}</div>
        </div>
      `;
      const grid = () => {
        const cardsList = Array.isArray(model.cards) ? model.cards : [];
        const cols = Math.min(3, Math.max(1, cardsList.length));
        return `
          <div style="display:grid;grid-template-columns:repeat(${cols}, minmax(0, 1fr));gap:12px;width:100%;height:100%;">
            ${cardsList.map((card) => `
              <div data-id="${esc(card.id)}" style="min-height:118px;padding:16px;display:flex;flex-direction:column;justify-content:space-between;background:#F8FAFC;border:none;box-shadow:none;">
                <div>
                  <div style="display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;background:${esc(card.appearance?.bg || '#F3F4F6')};color:${esc(card.appearance?.fg || '#5F6368')};font-size:11px;line-height:1.25;font-weight:800;text-transform:uppercase;">${esc(card.label)}</div>
                  <div style="margin-top:12px;font-size:28px;line-height:1.05;font-weight:800;color:#111827;">${esc(card.primary)}</div>
                </div>
                <div style="font-size:12px;line-height:1.35;font-weight:600;color:#667085;">${esc(card.secondary)}</div>
              </div>
            `).join('')}
          </div>
        `;
      };
      const body = model.status === 'unavailable'
        ? state('SOURCE MISSING', 'The required source is not available.')
        : model.status !== 'ok'
          ? state('NO DATA', 'No rows matched the active filters.')
          : grid();
      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:${width}px;height:${height}px;padding:12px 16px 16px;background:transparent;border:none;box-shadow:none;display:flex;flex-direction:column;gap:12px;font-family:Inter,Arial,sans-serif;overflow:hidden;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;min-width:0;">
              <div style="font-size:18px;line-height:1.1;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5F6368;">ACTION ANNOTATION SUMMARY</div>
              <span data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:999px;background:#F3F4F6;color:#5F6368;font-size:11px;font-weight:800;">?</span>
            </div>
            ${model.freshnessHtml || ''}
          </div>
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
            <div style="font-size:13px;font-weight:800;margin-bottom:6px;">Action Annotation Summary</div>
            <div style="font-size:12px;line-height:1.35;">Use for one compact what-matters-now summary block, not for a prose-heavy note wall.</div>
            <div style="margin-top:6px;font-size:11px;color:#667085;">datalens-advanced-editor focused family asset</div>
          </div>`;
        }
        if (!id) return null;
        const match = payload.items.find((item) => item.id === id);
        if (!match) return null;
        const rows = (match.rows || []).map((row) => `<div style="display:flex;justify-content:space-between;gap:16px;"><span style="color:#667085;">${esc(row.label)}</span><b>${esc(row.value)}</b></div>`).join('');
        return `<div style="min-width:200px;padding:10px 12px;background:#FFFFFF;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,0.28);font-family:Inter,Arial,sans-serif;color:#111827;font-size:12px;">
          <div style="font-size:13px;font-weight:800;margin-bottom:8px;">${esc(match.title)}</div>
          <div style="display:flex;flex-direction:column;gap:6px;">${rows}</div>
        </div>`;
      },
    }),
  },
};
