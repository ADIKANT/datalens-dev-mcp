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
            ? {surface: '#ffffff', header: '#f4f7fb', line: '#C9D3E0', text: '#102A56', muted: '#667085'}
            : {
                surface: 'var(--g-color-base-background,#ffffff)',
                header: 'var(--g-color-base-generic,#f4f7fb)',
                line: 'var(--g-color-line-generic,#C9D3E0)',
                text: 'var(--g-color-text-primary,#102A56)',
                muted: 'var(--g-color-text-secondary,#667085)'
              };
        const statusPalette = {
          noChange: 'var(--g-color-base-positive-light,#B8F6D6)',
          hwChange: 'var(--g-color-base-warning-light,#FFF2B8)',
          swChange: 'var(--g-color-base-info-light,#BBD8FF)',
          blChange: 'var(--g-color-base-danger-light,#FFE1D6)',
          config_error: 'var(--g-color-base-danger-light,#FFE1D6)',
          increase: 'var(--g-color-base-positive-light,#d9f2e6)',
          unchanged: 'var(--g-color-base-generic,#eef2f6)',
          decrease: 'var(--g-color-base-danger-light,#fde3e1)',
          missing: 'transparent',
          manual_not_applicable: 'var(--g-color-base-neutral-light,#f8fafc)'
        };
        const floating = theme === 'auto' ? 'var(--g-color-base-float,#ffffff)' : palette.surface;
        const statusText = {
          noChange: 'var(--g-color-text-positive,#237A57)',
          hwChange: 'var(--g-color-text-warning,#8A5A00)',
          swChange: 'var(--g-color-text-info,#0054B8)',
          blChange: 'var(--g-color-text-danger,#B42318)',
          config_error: 'var(--g-color-text-danger,#B42318)',
          missing: palette.muted,
          manual_not_applicable: palette.muted
        };
        const tinted = (color, content) => '<span aria-hidden="true" style="position:absolute;inset:0;background:'
          + color + ';pointer-events:none"></span><span style="position:relative;z-index:1">' + content + '</span>';
        let columns = Array.isArray(prepared && prepared.columns) ? prepared.columns : [];
        let rows = Array.isArray(prepared && prepared.rows) ? prepared.rows : [];
        const numericComparison = !columns.length;
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
        const headerLabels = numericComparison ? ['Metric'] : Array.isArray(table.header_rows) && table.header_rows.length
          ? table.header_rows : ['Column'];
        const headerHeights = Array.isArray(table.header_heights) && table.header_heights.length === headerLabels.length
          ? table.header_heights : headerLabels.map(() => Number(table.header_height) > 0 ? Number(table.header_height) : 32);
        const headerTops = headerHeights.map((_, level) => headerHeights.slice(0, level).reduce((a, b) => a + b, 0));
        const firstWidth = Number(table.first_column_width) > 0 ? Number(table.first_column_width) : 150;
        const valueWidth = Number(table.value_column_width) > 0 ? Number(table.value_column_width) : 112;
        const gridColumns = firstWidth + 'px repeat(' + columns.length + ', ' + valueWidth + 'px)';
        const headerRows = [];
        for (let level = 0; level < headerLabels.length; level += 1) {
          const headerHeight = headerHeights[level];
          let start = 0;
          while (start < columns.length) {
            const value = String((columns[start].headers || [])[level] == null ? '—' : (columns[start].headers || [])[level]);
            let end = start + 1;
            while (end < columns.length && Array.from({length: level + 1}, (_, ancestor) => ancestor).every(ancestor =>
              String((columns[end].headers || [])[ancestor] ?? '—') === String((columns[start].headers || [])[ancestor] ?? '—'))) end += 1;
            let tint = numericComparison ? palette.header : level === 0 ? statusPalette.manual_not_applicable
              : level === 1 ? palette.header : null;
            let textColor = palette.text;
            if (!numericComparison && level === 3) {
              const positive = ['approved', 'released'].includes(value.toLowerCase());
              tint = positive ? statusPalette.noChange : statusPalette.manual_not_applicable;
              textColor = positive ? statusText.noChange : palette.text;
            }
            if (!numericComparison && level === 4) {
              const positive = value.toUpperCase().startsWith('Y');
              const warning = value.toUpperCase() === 'N';
              tint = positive ? statusPalette.noChange : warning ? statusPalette.hwChange : statusPalette.manual_not_applicable;
              textColor = positive ? statusText.noChange : warning ? statusText.hwChange : palette.text;
            }
            let content = escape(value);
            if (!numericComparison && level === 2) content = value.split(/\s*\/\s*|\n/).map(part => '<div>' + escape(part) + '</div>').join('');
            if (!numericComparison && level === 5 && ['HW', 'SW', 'BL'].includes(value)) content += ' version';
            if (tint) content = tinted(tint, content);
            headerRows.push('<div role="columnheader" style="position:sticky;top:' + headerTops[level]
              + 'px;z-index:' + (20 - level) + ';grid-column:' + (start + 2) + ' / span ' + (end - start)
              + ';grid-row:' + (level + 1) + ';box-sizing:border-box;height:' + headerHeight
              + 'px;padding:6px 10px;background-color:' + floating + ';border-right:1px solid ' + palette.line
              + ';border-bottom:1px solid ' + palette.line + ';color:' + textColor
              + ';font-size:' + (level === 2 ? 13 : 12) + 'px;line-height:' + (level === 2 ? 18 : 16)
              + 'px;font-weight:' + (level >= 2 ? 800 : 700) + ';overflow:hidden;display:flex;'
              + (level === 2 ? 'flex-direction:column;justify-content:center;align-items:flex-start' : 'align-items:center')
              + '">' + content + '</div>');
            start = end;
          }
        }
        const firstHeader = headerLabels.map((label, level) => '<div role="rowheader" style="position:sticky;left:0;top:'
          + headerTops[level] + 'px;z-index:30;grid-column:1;grid-row:' + (level + 1)
          + ';box-sizing:border-box;padding:7px 12px;background:' + floating
          + ';border-right:1px solid ' + palette.line + ';border-bottom:1px solid ' + palette.line
          + ';color:' + palette.text + ';font-size:12px;line-height:16px;font-weight:800;overflow:hidden;white-space:nowrap">'
          + escape(label) + '</div>').join('');
        const body = rows.map((row, rowIndex) => {
          const rowNumber = headerLabels.length + rowIndex + 1;
          const label = '<div style="position:sticky;left:0;z-index:5;grid-column:1;grid-row:' + rowNumber
            + ';box-sizing:border-box;padding:8px 12px;background:' + palette.surface + ';border-right:1px solid '
            + palette.line + ';border-bottom:1px solid ' + palette.line + ';color:' + palette.text
            + ';font-size:12px;line-height:16px;font-weight:700;color:var(--g-color-text-link,#0054B8);overflow-wrap:anywhere">' + escape(row.label) + '</div>';
          const cells = columns.map((column, columnIndex) => {
            const cell = (row.cells || [])[columnIndex] || {};
            const status = String(cell.status || 'missing');
            const display = status === 'manual_not_applicable' ? 'NA' : status === 'config_error' ? 'CONFIG ERROR' : status === 'missing' && !numericComparison ? '-' : format(cell.value);
            return '<div data-id="matrix-cell-' + rowIndex + '-' + columnIndex + '" style="grid-column:'
              + (columnIndex + 2) + ';grid-row:' + rowNumber + ';box-sizing:border-box;min-width:0;padding:7px 10px;background:'
              + (statusPalette[status] || statusPalette.missing) + ';border-right:1px solid ' + palette.line
              + ';border-bottom:1px solid ' + palette.line + ';color:' + (statusText[status] || palette.text)
              + ';font-size:12px;line-height:16px;' + (numericComparison ? '' : 'font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;')
              + (numericComparison ? 'overflow-wrap:anywhere;' : 'white-space:nowrap;overflow:hidden;') + 'cursor:help">' + escape(display) + '</div>';
          }).join('');
          return label + cells;
        }).join('');
        const legendItems = numericComparison ? [{status:'increase',label:'Increase'},{status:'unchanged',label:'Unchanged'},{status:'decrease',label:'Decrease'},{status:'missing',label:'Missing'}] : Array.isArray(presentation.legend.items) ? presentation.legend.items : [];
        const legend = presentation.legend.mode === 'hidden' ? '' : '<div style="flex:0 0 auto;display:flex;gap:6px;flex-wrap:wrap;font-size:12px;line-height:16px;color:' + palette.text + '">' + legendItems.map(item => {
            const status = typeof item === 'object' && item ? String(item.status || '') : String(item);
            const label = typeof item === 'object' && item ? String(item.label || status) : String(item);
            return '<span style="display:inline-flex;padding:2px 6px;border-radius:3px;font-weight:700;color:' + (statusText[status] || palette.text) + ';background:'
              + (statusPalette[status] || palette.header) + '">' + escape(label) + '</span>';
          }).join('') + '</div>';
        outer += legend + '<div style="flex:1 1 auto;min-height:0;min-width:0;overflow:auto;border:1px solid '
          + palette.line + '"><div role="table" style="display:grid;grid-template-columns:' + gridColumns
          + ';grid-template-rows:' + headerHeights.map(h => h + 'px').join(' ') + ' repeat('
          + rows.length + ', minmax(34px,auto));min-width:' + (firstWidth + columns.length * valueWidth)
          + 'px;background:' + palette.surface + '">' + firstHeader + headerRows.join('') + body + '</div></div>';
        return Editor.generateHtml('<div style="box-sizing:border-box;height:100%;min-height:0;display:flex;flex-direction:column;gap:7px;font-family:Inter,Arial,sans-serif;padding:' + spacing
          + 'px;background:' + palette.surface + ';color:' + palette.text + ';overflow:hidden">' + outer + '</div>');
      },
      args: [data, config]
    }),
    tooltip: {
      renderer: Editor.wrapFn({
        fn: function(event, prepared) {
          const escape = value => String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
          const id = event && event.target && event.target.getAttribute
            ? String(event.target.getAttribute('data-id') || '') : '';
          const match = id.match(/^matrix-cell-(\d+)-(\d+)$/);
          if (!match) return '';
          const row = (prepared.rows || [])[Number(match[1])] || {};
          const column = (prepared.columns || [])[Number(match[2])] || {};
          const cell = (row.cells || [])[Number(match[2])] || {};
          return Editor.generateHtml('<div style="padding:10px"><strong>' + escape(row.label || '')
            + '</strong><div>' + escape((column.headers || []).join(' · ')) + '</div><div>'
            + escape(cell.status === 'manual_not_applicable' ? 'NA' : cell.status === 'missing' ? '-' : cell.status === 'config_error' ? 'CONFIG ERROR' : cell.value) + '</div><div>' + escape(cell.status || '') + '</div><div>' + escape(cell.provenance || cell.tooltip || '') + '</div></div>');
        },
        args: [data]
      })
    }
  };
};
