/* The source owns grain and aggregation; missing cells remain missing. */
module.exports = function renderHeatmap(data, presentation) {
  return {
    render: Editor.wrapFn({args: [data, presentation], fn: function(options, data, presentation) {
      const esc = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      const number = value => value === null || value === undefined || value === '' ? null
        : Number.isFinite(Number(value)) ? Number(value) : null;
      const precision = Number.isInteger(presentation.labels.precision) ? presentation.labels.precision : 0;
      const format = value => number(value) === null ? presentation.heatmap.missing_label
        : number(value).toLocaleString('en-US', {maximumFractionDigits: precision});
      if (data.state === 'error') return Editor.generateHtml('<div role="status">Data unavailable</div>');
      if (data.state === 'loading') return Editor.generateHtml('<div role="status">Loading…</div>');
      const rows = data.row_labels || [], columns = data.column_labels || [], values = data.values || [];
      if (!rows.length || !columns.length) return Editor.generateHtml('<div role="status">No data</div>');
      if (!Array.isArray(rows) || !Array.isArray(columns) || !Array.isArray(values)
          || rows.length * columns.length > 10000 || values.length !== rows.length
          || values.some(row => !Array.isArray(row) || row.length !== columns.length)) {
        return Editor.generateHtml('<div role="status">Invalid heatmap dimensions</div>');
      }
      const observed = values.flat().map(number).filter(v => v !== null);
      const max = Math.max(1, ...observed.map(Math.abs));
      const fontSize = 11;
      const cellWidth = Math.max(...columns.map(x => String(x).length), ...observed.map(x => format(x).length), 1) * fontSize * .6 + 6;
      const rowWidth = Math.max(...rows.map(x => String(x).length), 1) * fontSize * .6 + 6;
      const minimumWidth = Math.max(Number(presentation.geometry.minimum_width) || 0,
        rowWidth + columns.length * cellWidth + (columns.length + 2) * 3);
      const color = /^#[0-9a-f]{6}$/i.test(presentation.heatmap.color) ? presentation.heatmap.color : '#4E79A7';
      const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)).join(',');
      const header = columns.map(label => `<th scope="col" style="font-weight:500;color:var(--g-color-text-secondary,#667085)">${esc(label)}</th>`).join('');
      const body = rows.map((label, row) => `<tr><th scope="row" style="font-weight:500;text-align:left">${esc(label)}</th>`
        + columns.map((_column, column) => {
          const value = number(values[row]?.[column]);
          const alpha = value === null ? 0 : .12 + .8 * Math.sqrt(Math.abs(value) / max);
          const title = `${label} · ${columns[column]} · ${format(value)}`;
          return `<td data-id="heat-${row}-${column}" title="${esc(title)}" style="height:calc((100% - 22px)/${rows.length});border-radius:4px;text-align:center;white-space:nowrap;background:rgba(${rgb},${alpha});color:${alpha > .52 ? '#FFFFFF' : 'var(--g-color-text-primary,#111827)'}">${presentation.labels.visible && value !== null ? esc(format(value)) : ''}</td>`;
        }).join('') + '</tr>').join('');
      return Editor.generateHtml(`<div style="font:11px Inter,Arial,sans-serif;overflow:auto;padding:4px 6px;height:100%;box-sizing:border-box;color:var(--g-color-text-primary,#111827)"><table style="width:100%;min-width:${minimumWidth}px;height:100%;border-spacing:3px;table-layout:fixed"><thead><tr><th style="width:${rowWidth}px"></th>${header}</tr></thead><tbody>${body}</tbody></table></div>`);
    }}),
    tooltip: {renderer: Editor.wrapFn({args: [], fn: function(event) {
      const title = event.target?.getAttribute('title');
      if (!title) return null;
      const safe = String(title).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return Editor.generateHtml(`<div style="padding:8px;color:var(--g-color-text-primary,#111827);background:var(--g-color-base-float,#FFFFFF)">${safe}</div>`);
    }})}
  };
};
