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
const SHOW_DELTA = __SHOW_DELTA__;
const SHOW_SPARKLINE = __SHOW_SPARKLINE__;

// Prepare: normalize one metric row. Comparator values render only for explicit delta variants.
const row = normalizeRows('rows')[0] || {};
const numericOrNull = (value) => {
  if (value == null || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};
const current = numericOrNull(row.current_value);
const comparator = numericOrNull(row.comparator_value);
const delta = current != null && comparator != null ? current - comparator : null;
const deltaPercent = delta != null && comparator ? (delta / comparator) * 100 : null;
const sparkline = String(row.sparkline == null ? '' : row.sparkline)
  .split(',')
  .map((rawValue) => rawValue.trim())
  .filter((rawValue) => rawValue !== '')
  .map(Number)
  .filter(Number.isFinite);
const model = {
  variant: TEMPLATE_VARIANT,
  current,
  comparator,
  delta,
  deltaPercent,
  sparkline,
  comparatorLabel: row.comparator_label || 'declared comparator',
  hint: row.hint || 'KPI value with explicit comparator only when declared.',
  theme: themeName(),
  style: HOUSE_STYLE,
};

module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      function esc(value) {
        return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function fmt(value) {
        if (value == null || !Number.isFinite(Number(value))) return '—';
        const number = Number(value);
        const abs = Math.abs(number);
        if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
        if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
        return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
      }
      // Render/layout: dashboard-level title and hint are native metadata; body renders values only.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const compact = Number(options && options.width) < 360;
      const bg = style.colors.surface;
      const text = style.colors.text;
      // Delta direction is business-specific; stay neutral unless a separate
      // accepted direction contract is added to the source and renderer.
      const deltaTone = style.colors.textMuted;
      const showDelta = SHOW_DELTA && data.delta != null && data.deltaPercent != null;
      const showSparkline = SHOW_SPARKLINE;
      const sparkMax = Math.max(1, ...data.sparkline);
      const sparkParts = [];
      for (let index = 0; index < data.sparkline.length; index += 1) {
        const value = data.sparkline[index];
        sparkParts.push(`${index / Math.max(1, data.sparkline.length - 1) * 120},${34 - value / sparkMax * 30}`);
      }
      const sparkPoints = sparkParts.join(' ');
      const deltaHtml = showDelta ? `<div style="margin-top:8px;font-size:12px;color:${deltaTone};font-weight:800;">${data.delta >= 0 ? '+' : ''}${fmt(data.delta)} (${data.deltaPercent.toFixed(1)}%) vs ${esc(data.comparatorLabel)}</div>` : '';
      const sparkHtml = showSparkline && data.sparkline.length > 1 ? `<svg viewBox="0 0 120 36" width="100%" height="36" preserveAspectRatio="none" style="margin-top:10px;"><polyline points="${sparkPoints}" fill="none" stroke="${style.colors.primary}" stroke-width="2.5"/></svg>` : '';
      const body = `
        <div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${bg};font-family:Inter,Arial,sans-serif;color:${text};display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;">
          <div>
            <div style="font-size:${compact ? 34 : 46}px;line-height:1;font-weight:850;">${fmt(data.current)}</div>
            ${deltaHtml}
            ${sparkHtml}
          </div>
        </div>`;
      return Editor.generateHtml(body);
    },
  }),
};
