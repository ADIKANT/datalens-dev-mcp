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

// Prepare: validate flow shape. Source and target are mandatory for Sankey-like routing.
const rows = normalizeRows('rows')
  .map((row) => ({source: String(row.source || ''), target: String(row.target || ''), value: Number(row.value || 0)}))
  .filter((row) => row.source && row.target);
const model = {title: 'Flow', rows, hint: 'Flow chart requires explicit source, target, and value.', theme: themeName(), style: HOUSE_STYLE};

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
      // Render/layout: compact flow list baseline; upgrade to richer Sankey only after manual review.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const maxValue = Math.max(1, ...data.rows.map((row) => row.value));
      const rowsHtml = data.rows.map((row, index) => {
        const width = Math.max(4, (row.value / maxValue) * 100);
        const color = style.colors.category[index % style.colors.category.length];
        return `<div style="display:grid;grid-template-columns:minmax(90px,1fr) 1fr minmax(90px,1fr) 56px;gap:8px;align-items:center;margin:10px 0;font-size:12px;color:${style.colors.text};"><b>${esc(row.source)}</b><span style="height:12px;background:${style.colors.surfaceMuted};"><i style="display:block;height:12px;width:${width}%;background:${color};"></i></span><b>${esc(row.target)}</b><span style="text-align:right;">${fmt(row.value)}</span></div>`;
      }).join('');
      // Safe render contract: this is a gated flow template, not a generic category chart.
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px 14px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:hidden;">${rowsHtml || `<div style="color:${style.colors.textSubtle};font-weight:800;">NO FLOW DATA</div>`}</div>`);
    },
  }),
};
