/* Canonical comparison matrix: prepared rows are {label, current, previous}.
 * Data loading is separate; render uses only arguments transported by wrapFn.
 */
module.exports = function renderMatrix(data, config) {
  return {
    render: Editor.wrapFn({
      fn: function(options, prepared, presentation) {
        const escape = value => String(value == null ? '' : value)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        const numeric = value => typeof value === 'number' && Number.isFinite(value);
        const precision = Number.isInteger(presentation.labels.precision)
          ? Math.min(10, Math.max(0, presentation.labels.precision)) : 2;
        const format = value => numeric(value) ? value.toFixed(precision) : '—';
        const dark = presentation.states_theme.theme === 'dark';
        const palette = dark
          ? {text: '#f1f3f5', background: '#202124', line: '#55595e', up: '#70c99a', down: '#f28b82', neutral: '#b0b5bc'}
          : {text: '#202124', background: '#ffffff', line: '#dfe3e8', up: '#167747', down: '#b3261e', neutral: '#6b7280'};
        const rows = prepared && Array.isArray(prepared.rows) ? prepared.rows : [];
        const state = prepared && prepared.state ? prepared.state : (rows.length ? 'ready' : 'no_data');
        const messages = {loading: 'Loading…', error: 'Data unavailable', no_data: 'No data'};
        const heading = presentation.visible_title;
        let html = heading.visible && heading.owner === 'body'
          ? '<h3 style="margin:0 0 12px">' + escape(heading.text) + '</h3>' : '';
        if (messages[state]) {
          html += '<div role="status">' + messages[state] + '</div>';
        } else {
          html += '<table style="border-collapse:collapse;width:100%;font-size:13px"><thead><tr>';
          for (const label of ['Category', 'Current', 'Previous', 'Δ', 'Δ %']) {
            html += '<th style="position:sticky;top:0;padding:8px;text-align:left;background:' + palette.background + '">' + label + '</th>';
          }
          html += '</tr></thead><tbody>';
          for (const row of rows) {
            const valid = numeric(row.current) && numeric(row.previous);
            const delta = valid ? row.current - row.previous : null;
            const percent = valid && row.previous !== 0 ? delta / Math.abs(row.previous) * 100 : null;
            const color = delta === null || delta === 0 ? palette.neutral : delta > 0 ? palette.up : palette.down;
            const relative = !valid ? 'Missing comparison' : row.previous === 0 ? 'Undefined: previous = 0' : format(percent) + '%';
            const tooltip = 'Current: ' + format(row.current) + '; Previous: ' + format(row.previous)
              + '; Delta: ' + format(delta) + '; Relative: ' + relative;
            html += '<tr title="' + escape(tooltip) + '">';
            const cells = [row.label, format(row.current), format(row.previous), format(delta), relative];
            cells.forEach((cell, index) => {
              html += '<td style="padding:8px;border-top:1px solid ' + palette.line
                + ';overflow-wrap:anywhere;' + (index > 2 ? 'color:' + color + ';' : '') + '">' + escape(cell) + '</td>';
            });
            html += '</tr>';
          }
          html += '</tbody></table>';
          if (presentation.legend.mode !== 'hidden') {
            html += '<div style="padding-top:12px;font-size:12px">'
              + '<span style="color:' + palette.up + '">↑ Increase</span> · '
              + '<span style="color:' + palette.down + '">↓ Decrease</span> · Unchanged · Missing</div>';
          }
        }
        const height = Number.isFinite(options.height) ? Math.max(0, options.height) : 300;
        return Editor.generateHtml('<div style="box-sizing:border-box;padding:12px;height:' + height
          + 'px;overflow:auto;color:' + palette.text + ';background:' + palette.background + '">' + html + '</div>');
      },
      args: [data, config]
    })
  };
};
