/* Reusable Advanced KPI. Prepared data: value, previous, points, state. */
module.exports = function renderKpi(data, config) {
  return {
    render: Editor.wrapFn({
      fn: function(options, prepared, presentation) {
        const escape = value => String(value == null ? '' : value)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        const numeric = value => typeof value === 'number' && Number.isFinite(value);
        const precision = Number.isInteger(presentation.labels.precision)
          ? Math.max(0, Math.min(10, presentation.labels.precision)) : 2;
        const format = value => numeric(value) ? value.toFixed(precision) : '—';
        const state = prepared && prepared.state ? prepared.state : numeric(prepared && prepared.value) ? 'ready' : 'no_data';
        const dark = presentation.states_theme.theme === 'dark';
        const text = dark ? '#f1f3f5' : '#202124';
        const background = dark ? '#202124' : '#ffffff';
        const title = presentation.visible_title;
        let html = title.visible && title.owner === 'body'
          ? '<div style="font-size:14px;overflow-wrap:anywhere">' + escape(title.text) + '</div>' : '';
        const messages = {loading: 'Loading…', error: 'Data unavailable', no_data: 'No data'};
        if (messages[state]) {
          html += '<div role="status">' + messages[state] + '</div>';
        } else {
          const value = prepared.value, previous = prepared.previous;
          const valid = numeric(value) && numeric(previous);
          const delta = valid ? value - previous : null;
          const relative = !valid ? 'Missing comparison' : previous === 0 ? 'Undefined: previous = 0'
            : format(delta / Math.abs(previous) * 100) + '%';
          const unit = presentation.labels.unit === 'from_field' ? '' : String(presentation.labels.unit || '');
          const tooltip = 'Current: ' + format(value) + '; Previous: ' + format(previous)
            + '; Delta: ' + format(delta) + '; Relative: ' + relative;
          html += '<div title="' + escape(tooltip) + '" style="font-size:32px;font-weight:600;margin-top:8px">'
            + escape(format(value)) + (unit ? ' <small>' + escape(unit) + '</small>' : '') + '</div>';
          html += '<div style="font-size:12px;margin-top:4px">' + escape(presentation.comparison.label || 'Comparison')
            + ': ' + escape(format(delta)) + ' · ' + escape(relative) + '</div>';
          const points = Array.isArray(prepared.points) ? prepared.points : [];
          const values = points.map(point => typeof point === 'object' && point !== null ? point.value : point);
          const finite = values.filter(numeric);
          if (finite.length) {
            let low = finite[0], high = finite[0];
            for (const value of finite) { low = Math.min(low, value); high = Math.max(high, value); }
            let path = '', connected = false;
            values.forEach((value, index) => {
              if (!numeric(value)) { connected = false; return; }
              const x = 4 + index * 292 / Math.max(1, values.length - 1);
              const y = high === low ? 30 : 56 - (value - low) * 52 / (high - low);
              path += (connected ? ' L' : ' M') + x.toFixed(2) + ',' + y.toFixed(2);
              connected = true;
            });
            html += '<svg viewBox="0 0 300 60" width="100%" height="60" aria-label="Trend">'
              + '<path d="' + path + '" fill="none" stroke="#5282ff" stroke-width="2" /></svg>';
          }
        }
        const height = Number.isFinite(options.height) ? Math.max(0, options.height) : 180;
        return Editor.generateHtml('<div style="box-sizing:border-box;padding:12px;overflow:auto;height:' + height
          + 'px;color:' + text + ';background:' + background + '">' + html + '</div>');
      },
      args: [data, config]
    })
  };
};
