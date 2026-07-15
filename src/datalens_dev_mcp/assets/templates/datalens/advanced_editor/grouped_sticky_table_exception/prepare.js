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

// Prepare: normalize grouped rows for a rare table-like Advanced renderer.
const rows = normalizeRows('rows').map((row) => ({
  group: String(row.group_label || row.group || ''),
  metric: String(row.metric_label || row.metric || ''),
  value: Number(row.value || 0),
}));
const model = {
  title: 'Grouped Table Exception',
  rows,
  hint: 'Use only when table_node cannot express grouped or sticky layout requirements.',
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
        const number = Number(value || 0);
        const abs = Math.abs(number);
        if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
        if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
        return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
      }
      // Render/layout: table-like HTML is intentionally plain and operational.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const rowsHtml = data.rows.map((row) => `
        <tr>
          <th style="position:sticky;left:0;background:${style.colors.surface};text-align:left;padding:8px;border-bottom:1px solid ${style.colors.border};">${esc(row.group)}</th>
          <td style="padding:8px;border-bottom:1px solid ${style.colors.border};">${esc(row.metric)}</td>
          <td style="padding:8px;border-bottom:1px solid ${style.colors.border};text-align:right;font-weight:800;">${fmt(row.value)}</td>
        </tr>
      `).join('');
      // Safe render contract: explicit Advanced exception, never a default table route.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;color:${style.colors.text};"><thead><tr><th style="text-align:left;padding:8px;border-bottom:1px solid ${style.colors.border};">Group</th><th style="text-align:left;padding:8px;border-bottom:1px solid ${style.colors.border};">Metric</th><th style="text-align:right;padding:8px;border-bottom:1px solid ${style.colors.border};">Value</th></tr></thead><tbody>${rowsHtml}</tbody></table></div>`);
    },
  }),
};
