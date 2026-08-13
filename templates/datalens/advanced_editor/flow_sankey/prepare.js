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
// @cookbook-locale ru Sankey использует отдельные узлы и связи; циклические переходы должны быть устранены в Sources.
// @cookbook-locale en Sankey uses separate nodes and links; cyclic transitions must be removed in Sources.
/* __DATALENS_SHARED_STYLE_TOKENS__ */
/* __DATALENS_SHARED_RENDER_HELPERS__ */

// Prepare: validate flow shape. Source and target are mandatory for Sankey-like routing.
const parsedRows = normalizeRows('rows')
  .map((row) => ({
    source: String(row.source || ''),
    target: String(row.target || ''),
    value: row.value == null || row.value === '' ? NaN : Number(row.value),
  }));
const invalidReason = parsedRows.some((row) => !row.source || !row.target || !Number.isFinite(row.value) || !(row.value > 0))
  ? 'flow_rows_require_source_target_and_positive_value'
  : '';
const rows = parsedRows.map((row) => ({...row, value: Number.isFinite(row.value) ? row.value : 0}));
const model = {title: 'Flow', rows, invalidReason, hint: 'Flow chart requires explicit source, target, and positive value.', theme: themeName(), style: HOUSE_STYLE};

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
      // Render/layout: calculate deterministic node columns and curved weighted links.
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = width < 530;
      if (data.invalidReason) {
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px;background:${style.colors.surface};color:${style.colors.textMuted};font-family:Inter,Arial,sans-serif;">N/A · ${esc(data.invalidReason)}</div>`);
      }
      if (!data.rows.length) {
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px;background:${style.colors.surface};color:${style.colors.textMuted};font-family:Inter,Arial,sans-serif;">NO FLOW DATA</div>`);
      }
      const names = [...new Set(data.rows.flatMap((row) => [row.source, row.target]))];
      const depth = Object.fromEntries(names.map((name) => [name, 0]));
      let changed = false;
      for (let pass = 0; pass < names.length; pass += 1) {
        changed = false;
        data.rows.forEach((row) => {
          const next = depth[row.source] + 1;
          if (next > depth[row.target]) {
            depth[row.target] = next;
            changed = true;
          }
        });
        if (!changed) break;
      }
      if (changed) {
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:12px;background:${style.colors.surface};color:${style.colors.textMuted};font-family:Inter,Arial,sans-serif;">N/A · cyclic_flow</div>`);
      }
      const maxDepth = Math.max(1, ...Object.values(depth));
      const padding = compact ? 18 : 28;
      const nodeWidth = compact ? 12 : 16;
      const plotWidth = Math.max(180, width - padding * 2 - nodeWidth);
      const plotHeight = Math.max(140, height - padding * 2);
      const nodes = names.map((name, index) => {
        const columnNodes = names.filter((candidate) => depth[candidate] === depth[name]);
        const slot = columnNodes.indexOf(name);
        const incoming = data.rows.filter((row) => row.target === name).reduce((sum, row) => sum + row.value, 0);
        const outgoing = data.rows.filter((row) => row.source === name).reduce((sum, row) => sum + row.value, 0);
        const x = padding + depth[name] / maxDepth * plotWidth;
        const y = padding + (slot + 0.5) / Math.max(1, columnNodes.length) * plotHeight;
        return {name, index, x, y, value: Math.max(incoming, outgoing, 1)};
      });
      const maxValue = Math.max(1, ...nodes.map((node) => node.value), ...data.rows.map((row) => row.value));
      const links = data.rows.map((row, index) => {
        const source = nodes.find((node) => node.name === row.source);
        const target = nodes.find((node) => node.name === row.target);
        const strokeWidth = Math.max(2, row.value / maxValue * (compact ? 18 : 30));
        const x1 = source.x + nodeWidth;
        const x2 = target.x;
        const control = Math.max(24, (x2 - x1) * 0.52);
        const color = style.colors.category[index % style.colors.category.length];
        return `<path data-role="sankey-link" data-id="sankey-link-${index}" d="M ${x1.toFixed(1)} ${source.y.toFixed(1)} C ${(x1 + control).toFixed(1)} ${source.y.toFixed(1)}, ${(x2 - control).toFixed(1)} ${target.y.toFixed(1)}, ${x2.toFixed(1)} ${target.y.toFixed(1)}" fill="none" stroke="${color}" stroke-width="${strokeWidth.toFixed(1)}" stroke-opacity="0.35"><title>${esc(row.source)} → ${esc(row.target)} · ${fmt(row.value)}</title></path>`;
      }).join('');
      const nodeMarkup = nodes.map((node) => {
        const nodeHeight = Math.max(18, node.value / maxValue * (compact ? 54 : 82));
        const labelX = depth[node.name] === maxDepth ? node.x - 6 : node.x + nodeWidth + 6;
        const anchor = depth[node.name] === maxDepth ? 'end' : 'start';
        return `<g data-role="sankey-node" data-node="${esc(node.name)}"><rect x="${node.x.toFixed(1)}" y="${(node.y - nodeHeight / 2).toFixed(1)}" width="${nodeWidth}" height="${nodeHeight.toFixed(1)}" rx="3" fill="${style.colors.primary}"/><text x="${labelX.toFixed(1)}" y="${(node.y - nodeHeight / 2 - 5).toFixed(1)}" text-anchor="${anchor}" font-size="${compact ? 9 : 11}" font-weight="800" fill="${style.colors.text}">${esc(node.name)}</text></g>`;
      }).join('');
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:0;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow:auto;"><svg data-role="sankey" data-node-count="${nodes.length}" data-link-count="${data.rows.length}" viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">${links}${nodeMarkup}</svg></div>`);
    },
  }),
};
