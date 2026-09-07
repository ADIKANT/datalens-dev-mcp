/* ISO-week totals table with sticky first/last columns and bottom totals. */
module.exports = function renderWeeklyTotals(data, config) {
  return {
    render: Editor.wrapFn({
      fn: function(options, prepared, presentation) {
        const escape = value => String(value == null ? '' : value)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        const format = value => String(Math.round(Number(value) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        const table = presentation.table || {};
        const widths = table.widths && typeof table.widths === 'object' ? table.widths : {};
        const firstWidth = Number(widths.first) > 0 ? Number(widths.first) : 132;
        const periodWidth = Number(widths.period) > 0 ? Number(widths.period) : 82;
        const totalWidth = Number(widths.total) > 0 ? Number(widths.total) : 96;
        const weeks = Array.isArray(prepared && prepared.weeks) ? prepared.weeks : [];
        const rows = Array.isArray(prepared && prepared.rows) ? prepared.rows : [];
        const state = prepared && prepared.state ? prepared.state : rows.length ? 'ready' : 'no_data';
        const theme = presentation.states_theme.theme;
        const colors = theme === 'dark'
          ? {surface: '#202124', alt: '#292a2d', header: '#303134', total: '#26364f', line: '#55595e', text: '#f1f3f5', muted: '#b0b5bc'}
          : theme === 'light'
            ? {surface: '#ffffff', alt: '#f9fafb', header: '#f8fafc', total: '#eef4ff', line: '#d0d5dd', text: '#101828', muted: '#667085'}
            : {
                surface: 'var(--g-color-base-background,transparent)',
                alt: 'var(--g-color-base-generic-ultralight,#f9fafb)',
                header: 'var(--g-color-base-generic,#f8fafc)',
                total: 'var(--g-color-base-info-light,#eef4ff)',
                line: 'var(--g-color-line-generic,#d0d5dd)',
                text: 'var(--g-color-text-primary,#101828)',
                muted: 'var(--g-color-text-secondary,#667085)'
              };
        const title = presentation.visible_title || {};
        const spacing = Number.isFinite(Number(presentation.geometry.spacing))
          ? Math.max(0, Number(presentation.geometry.spacing)) : 8;
        let heading = title.visible && title.owner === 'body'
          ? '<div style="font-size:14px;font-weight:700;margin-bottom:' + spacing + 'px">' + escape(title.text) + '</div>' : '';
        const messages = {loading: 'Loading…', error: 'Data unavailable', no_data: 'No data'};
        if (messages[state]) {
          return Editor.generateHtml('<div role="status" style="box-sizing:border-box;height:100%;padding:' + spacing
            + 'px;background:' + colors.surface + ';color:' + colors.muted + '">' + heading + messages[state] + '</div>');
        }
        const minWidth = firstWidth + weeks.length * periodWidth + totalWidth;
        const weekHeaders = weeks.map(week => '<div style="box-sizing:border-box;display:flex;align-items:center;justify-content:flex-end;flex:0 0 '
          + periodWidth + 'px;height:42px;padding:0 10px;background:' + colors.header + ';border-bottom:1px solid '
          + colors.line + ';border-right:1px solid ' + colors.line + ';color:' + colors.muted
          + ';font-size:12px;font-weight:800;white-space:nowrap">' + escape(week.label) + '</div>').join('');
        const bodyRows = rows.map((row, rowIndex) => {
          const background = rowIndex % 2 === 0 ? colors.surface : colors.alt;
          const cells = weeks.map((week, weekIndex) => {
            const value = (row.values || [])[weekIndex] || 0;
            return '<div data-id="weekly-cell-' + rowIndex + '-' + weekIndex
              + '" style="box-sizing:border-box;display:flex;align-items:center;justify-content:flex-end;flex:0 0 '
              + periodWidth + 'px;height:40px;padding:0 10px;background:' + background
              + ';border-bottom:1px solid ' + colors.line + ';border-right:1px solid ' + colors.line
              + ';color:' + (Number(value) === 0 ? colors.muted : colors.text)
              + ';font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap;cursor:help">'
              + format(value) + '</div>';
          }).join('');
          const total = row.total == null
            ? (row.values || []).reduce((sum, value) => sum + (Number(value) || 0), 0) : row.total;
          return '<div style="display:flex;width:' + minWidth + 'px;min-width:' + minWidth + 'px;height:40px">'
            + '<div style="box-sizing:border-box;position:sticky;left:0;z-index:2;display:flex;align-items:center;flex:0 0 '
            + firstWidth + 'px;height:40px;padding:0 14px;background:' + background + ';border-bottom:1px solid '
            + colors.line + ';border-right:1px solid ' + colors.line + ';color:' + colors.text
            + ';font-size:13px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
            + escape(row.label) + '</div>' + cells
            + '<div data-id="weekly-row-total-' + rowIndex
            + '" style="box-sizing:border-box;position:sticky;right:0;z-index:2;display:flex;align-items:center;justify-content:flex-end;flex:0 0 '
            + totalWidth + 'px;height:40px;padding:0 14px;background:' + colors.total + ';border-bottom:1px solid '
            + colors.line + ';border-left:1px solid ' + colors.line + ';color:' + colors.text
            + ';font-size:13px;font-weight:800;white-space:nowrap;cursor:help">' + format(total) + '</div></div>';
        }).join('');
        const totalValues = Array.isArray(prepared.total_values) ? prepared.total_values
          : weeks.map((week, index) => rows.reduce((sum, row) => sum + (Number((row.values || [])[index]) || 0), 0));
        const grandTotal = prepared.grand_total == null
          ? totalValues.reduce((sum, value) => sum + (Number(value) || 0), 0) : prepared.grand_total;
        const totalCells = totalValues.map(value => '<div style="box-sizing:border-box;display:flex;align-items:center;justify-content:flex-end;flex:0 0 '
          + periodWidth + 'px;height:42px;padding:0 10px;background:' + colors.header + ';border-top:2px solid '
          + colors.line + ';border-right:1px solid ' + colors.line + ';color:' + colors.text
          + ';font-size:13px;font-weight:800;white-space:nowrap">' + format(value) + '</div>').join('');
        const totalRow = '<div style="display:flex;width:' + minWidth + 'px;min-width:' + minWidth + 'px;height:42px">'
          + '<div style="box-sizing:border-box;position:sticky;left:0;z-index:2;display:flex;align-items:center;flex:0 0 '
          + firstWidth + 'px;height:42px;padding:0 14px;background:' + colors.header + ';border-top:2px solid '
          + colors.line + ';border-right:1px solid ' + colors.line + ';font-size:13px;font-weight:800">TOTAL</div>'
          + totalCells + '<div style="box-sizing:border-box;position:sticky;right:0;z-index:2;display:flex;align-items:center;justify-content:flex-end;flex:0 0 '
          + totalWidth + 'px;height:42px;padding:0 14px;background:' + colors.total + ';border-top:2px solid '
          + colors.line + ';border-left:1px solid ' + colors.line + ';font-size:13px;font-weight:800">'
          + format(grandTotal) + '</div></div>';
        heading += '<div style="width:100%;height:calc(100% - 24px);overflow:auto;border:1px solid ' + colors.line
          + ';background:' + colors.surface + '"><div style="position:sticky;top:0;z-index:4;display:flex;width:'
          + minWidth + 'px;min-width:' + minWidth + 'px;height:42px"><div style="box-sizing:border-box;position:sticky;left:0;z-index:5;display:flex;align-items:center;flex:0 0 '
          + firstWidth + 'px;height:42px;padding:0 14px;background:' + colors.header + ';border-bottom:1px solid '
          + colors.line + ';border-right:1px solid ' + colors.line + ';font-size:12px;font-weight:800">'
          + escape(table.first_column_label || 'Group') + '</div>' + weekHeaders
          + '<div style="box-sizing:border-box;position:sticky;right:0;z-index:5;display:flex;align-items:center;justify-content:flex-end;flex:0 0 '
          + totalWidth + 'px;height:42px;padding:0 14px;background:' + colors.total + ';border-bottom:1px solid '
          + colors.line + ';border-left:1px solid ' + colors.line + ';font-size:12px;font-weight:800">TOTAL</div></div>'
          + '<div>' + bodyRows + totalRow + '</div></div>';
        return Editor.generateHtml('<div style="box-sizing:border-box;width:100%;height:100%;min-height:180px;padding:'
          + spacing + 'px;background:' + colors.surface + ';color:' + colors.text
          + ';font-family:Inter,Arial,sans-serif;overflow:hidden">' + heading + '</div>');
      },
      args: [data, config]
    }),
    tooltip: {
      renderer: Editor.wrapFn({
        fn: function(event, prepared, presentation) {
          const id = event && event.target && event.target.getAttribute
            ? String(event.target.getAttribute('data-id') || '') : '';
          const match = id.match(/^weekly-cell-(\d+)-(\d+)$/);
          if (!match) return '';
          const row = (prepared.rows || [])[Number(match[1])] || {};
          const week = (prepared.weeks || [])[Number(match[2])] || {};
          const value = (row.values || [])[Number(match[2])];
          const unit = presentation.tooltip.unit === true || presentation.tooltip.unit === 'from_field'
            ? '' : String(presentation.tooltip.unit || presentation.labels.unit || '');
          return Editor.generateHtml('<div style="padding:10px"><strong>' + String(row.label || '')
            + '</strong><div>' + String(week.date_from || '') + ' — ' + String(week.date_to || '')
            + '</div><div>' + String(value == null ? '—' : value) + (unit ? ' ' + unit : '') + '</div></div>');
        },
        args: [data, config]
      })
    }
  };
};
