/* Dynamic multi-level matrix. Prepared columns own header values; rows own cells. */
module.exports = function renderVersionMatrix(data, config) {
  return {
    render: Editor.wrapFn({
      fn: function(options, prepared, presentation) {
        const escape = value => String(value == null ? '' : value)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        const numeric = value => typeof value === 'number' && Number.isFinite(value);
        const precision = Number.isInteger(presentation.labels.precision)
          ? Math.max(0, Math.min(10, presentation.labels.precision)) : 2;
        const format = value => numeric(value) ? value.toFixed(precision) : String(value == null ? '—' : value);
        const table = presentation.table || {};
        const theme = presentation.states_theme.theme;
        const palette = theme === 'dark'
          ? {surface: '#202124', header: '#303134', line: '#55595e', text: '#f1f3f5', muted: '#b0b5bc'}
          : theme === 'light'
            ? {surface: '#ffffff', header: '#f4f7fb', line: '#dfe3e8', text: '#202124', muted: '#6b7280'}
            : {
                surface: 'var(--g-color-base-background,transparent)',
                header: 'var(--g-color-base-generic,#f4f7fb)',
                line: 'var(--g-color-line-generic,#dfe3e8)',
                text: 'var(--g-color-text-primary,#202124)',
                muted: 'var(--g-color-text-secondary,#6b7280)'
              };
        const statusPalette = {
          increase: 'var(--g-color-base-positive-light,#d9f2e6)',
          unchanged: 'var(--g-color-base-generic,#eef2f6)',
          decrease: 'var(--g-color-base-danger-light,#fde3e1)',
          missing: 'transparent',
          manual_not_applicable: 'var(--g-color-base-neutral-light,#f8fafc)'
        };
        let columns = Array.isArray(prepared && prepared.columns) ? prepared.columns : [];
        let rows = Array.isArray(prepared && prepared.rows) ? prepared.rows : [];
        if (!columns.length && rows.length) {
          columns = [
            {key: 'current', headers: ['Current']},
            {key: 'previous', headers: ['Previous']},
            {key: 'delta', headers: ['Δ']},
            {key: 'relative', headers: ['Δ %']}
          ];
          rows = rows.map(row => {
            const valid = numeric(row.current) && numeric(row.previous);
            const delta = valid ? row.current - row.previous : null;
            const relative = !valid ? 'Missing comparison' : row.previous === 0
              ? 'Undefined: previous = 0' : format(delta / Math.abs(row.previous) * 100) + '%';
            const status = delta === null ? 'missing' : delta > 0 ? 'increase' : delta < 0 ? 'decrease' : 'unchanged';
            return {
              label: row.label,
              cells: [
                {value: format(row.current), status: 'unchanged'},
                {value: format(row.previous), status: 'unchanged'},
                {value: format(delta), status: status},
                {value: relative, status: status}
              ]
            };
          });
        }
        const state = prepared && prepared.state ? prepared.state : rows.length ? 'ready' : 'no_data';
        const messages = {loading: 'Loading…', error: 'Data unavailable', no_data: 'No data'};
        const title = presentation.visible_title || {};
        const spacing = Number.isFinite(Number(presentation.geometry.spacing))
          ? Math.max(0, Number(presentation.geometry.spacing)) : 8;
        let outer = title.visible && title.owner === 'body'
          ? '<div style="font-size:14px;font-weight:700;margin-bottom:' + spacing + 'px">' + escape(title.text) + '</div>' : '';
        if (messages[state]) {
          return Editor.generateHtml('<div role="status" style="box-sizing:border-box;height:100%;padding:' + spacing
            + 'px;background:' + palette.surface + ';color:' + palette.muted + '">' + outer + messages[state] + '</div>');
        }
        const headerLabels = Array.isArray(table.header_rows) && table.header_rows.length
          ? table.header_rows : ['Column'];
        const headerHeight = Number(table.header_height) > 0 ? Number(table.header_height) : 32;
        const firstWidth = Number(table.first_column_width) > 0 ? Number(table.first_column_width) : 150;
        const valueWidth = Number(table.value_column_width) > 0 ? Number(table.value_column_width) : 112;
        const gridColumns = firstWidth + 'px repeat(' + columns.length + ', ' + valueWidth + 'px)';
        const headerRows = [];
        for (let level = 0; level < headerLabels.length; level += 1) {
          let start = 0;
          while (start < columns.length) {
            const value = String((columns[start].headers || [])[level] == null ? '—' : (columns[start].headers || [])[level]);
            let end = start + 1;
            while (end < columns.length && String((columns[end].headers || [])[level] == null ? '—' : (columns[end].headers || [])[level]) === value) end += 1;
            headerRows.push('<div role="columnheader" style="position:sticky;top:' + (level * headerHeight)
              + 'px;z-index:' + (20 - level) + ';grid-column:' + (start + 2) + ' / span ' + (end - start)
              + ';grid-row:' + (level + 1) + ';box-sizing:border-box;height:' + headerHeight
              + 'px;padding:6px 8px;background:' + palette.header + ';border-right:1px solid ' + palette.line
              + ';border-bottom:1px solid ' + palette.line + ';color:' + palette.text
              + ';font-size:11px;font-weight:700;overflow:hidden"><span style="color:' + palette.muted + '">'
              + escape(headerLabels[level]) + ':</span> ' + escape(value) + '</div>');
            start = end;
          }
        }
        const firstHeader = '<div role="columnheader" style="position:sticky;left:0;top:0;z-index:30;grid-column:1;grid-row:1 / span '
          + headerLabels.length + ';box-sizing:border-box;padding:8px;background:' + palette.header
          + ';border-right:1px solid ' + palette.line + ';border-bottom:1px solid ' + palette.line
          + ';color:' + palette.text + ';font-size:12px;font-weight:800">' + escape(table.first_column_label || 'Item') + '</div>';
        const body = rows.map((row, rowIndex) => {
          const rowNumber = headerLabels.length + rowIndex + 1;
          const label = '<div style="position:sticky;left:0;z-index:5;grid-column:1;grid-row:' + rowNumber
            + ';box-sizing:border-box;padding:8px;background:' + palette.surface + ';border-right:1px solid '
            + palette.line + ';border-bottom:1px solid ' + palette.line + ';color:' + palette.text
            + ';font-size:12px;font-weight:700;overflow-wrap:anywhere">' + escape(row.label) + '</div>';
          const cells = columns.map((column, columnIndex) => {
            const cell = (row.cells || [])[columnIndex] || {};
            const status = String(cell.status || 'missing');
            const display = status === 'manual_not_applicable' ? 'NA' : format(cell.value);
            return '<div data-id="matrix-cell-' + rowIndex + '-' + columnIndex + '" style="grid-column:'
              + (columnIndex + 2) + ';grid-row:' + rowNumber + ';box-sizing:border-box;padding:8px;background:'
              + (statusPalette[status] || statusPalette.missing) + ';border-right:1px solid ' + palette.line
              + ';border-bottom:1px solid ' + palette.line + ';color:' + palette.text
              + ';font-size:12px;overflow-wrap:anywhere;cursor:help">' + escape(display) + '</div>';
          }).join('');
          return label + cells;
        }).join('');
        const legendItems = Array.isArray(presentation.legend.items) ? presentation.legend.items : [];
        const legend = presentation.legend.mode === 'hidden' ? '' : '<div style="display:flex;gap:12px;flex-wrap:wrap;padding-top:'
          + spacing + 'px;font-size:11px;color:' + palette.muted + '">' + legendItems.map(item => {
            const status = typeof item === 'object' && item ? String(item.status || '') : String(item);
            const label = typeof item === 'object' && item ? String(item.label || status) : String(item);
            return '<span><i style="display:inline-block;width:9px;height:9px;margin-right:4px;background:'
              + (statusPalette[status] || statusPalette.missing) + '"></i>' + escape(label) + '</span>';
          }).join('') + '</div>';
        outer += '<div style="overflow:auto;max-width:100%;max-height:calc(100% - 28px);border:1px solid '
          + palette.line + '"><div role="table" style="display:grid;grid-template-columns:' + gridColumns
          + ';grid-template-rows:repeat(' + headerLabels.length + ', ' + headerHeight + 'px) repeat('
          + rows.length + ', minmax(36px,auto));min-width:' + (firstWidth + columns.length * valueWidth)
          + 'px;background:' + palette.surface + '">' + firstHeader + headerRows.join('') + body + '</div></div>' + legend;
        return Editor.generateHtml('<div style="box-sizing:border-box;height:100%;padding:' + spacing
          + 'px;background:' + palette.surface + ';color:' + palette.text + ';overflow:hidden">' + outer + '</div>');
      },
      args: [data, config]
    }),
    tooltip: {
      renderer: Editor.wrapFn({
        fn: function(event, prepared) {
          const id = event && event.target && event.target.getAttribute
            ? String(event.target.getAttribute('data-id') || '') : '';
          const match = id.match(/^matrix-cell-(\d+)-(\d+)$/);
          if (!match) return '';
          const row = (prepared.rows || [])[Number(match[1])] || {};
          const column = (prepared.columns || [])[Number(match[2])] || {};
          const cell = (row.cells || [])[Number(match[2])] || {};
          return Editor.generateHtml('<div style="padding:10px"><strong>' + String(row.label || '')
            + '</strong><div>' + String((column.headers || []).join(' · ')) + '</div><div>'
            + String(cell.value == null ? '—' : cell.value) + '</div></div>');
        },
        args: [data]
      })
    }
  };
};
