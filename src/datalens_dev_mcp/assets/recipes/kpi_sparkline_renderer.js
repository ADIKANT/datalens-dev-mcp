/* Standalone KPI with comparison and sparkline. Data loading stays in Prepare. */
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
        const unit = presentation.labels.unit === 'from_field'
          ? '' : String(presentation.labels.unit || '');
        const state = prepared && prepared.state
          ? prepared.state : numeric(prepared && prepared.value) ? 'ready' : 'no_data';
        const theme = presentation.states_theme.theme;
        const colors = theme === 'dark'
          ? {text: '#f1f3f5', muted: '#b0b5bc', background: '#202124', line: '#8ab4f8'}
          : theme === 'light'
            ? {text: '#202124', muted: '#6b7280', background: '#ffffff', line: '#5282ff'}
            : {
                text: 'var(--g-color-text-primary,#202124)',
                muted: 'var(--g-color-text-secondary,#6b7280)',
                background: 'var(--g-color-base-background,transparent)',
                line: 'var(--g-color-base-brand,#5282ff)'
              };
        const spacing = Number.isFinite(Number(presentation.geometry.spacing))
          ? Math.max(0, Math.min(48, Number(presentation.geometry.spacing))) : 8;
        const title = presentation.visible_title;
        const hint = presentation.hint || {};
        let html = title.visible && title.owner === 'body'
          ? '<div style="font-size:14px;line-height:18px;font-weight:700;overflow-wrap:anywhere">'
            + escape(title.text) + '</div>' : '';
        if (hint.enabled) {
          html += '<div data-id="kpi-hint" style="position:absolute;right:' + spacing
            + 'px;top:' + spacing + 'px;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;'
            + 'justify-content:center;background:var(--g-color-base-generic,#eef2f6);color:' + colors.muted
            + ';font-size:12px;font-weight:700;cursor:help">?</div>';
        }
        const messages = {loading: 'Loading…', error: 'Data unavailable', no_data: 'No data'};
        if (messages[state]) {
          html += '<div role="status" style="margin-top:' + spacing + 'px">' + messages[state] + '</div>';
        } else {
          const value = prepared.value;
          const previous = prepared.previous;
          const valid = numeric(value) && numeric(previous);
          const delta = valid ? value - previous : null;
          const relative = !valid ? 'Missing comparison' : previous === 0
            ? 'Undefined: previous = 0' : format(delta / Math.abs(previous) * 100) + '%';
          html += '<div data-id="kpi-value" style="font-size:32px;line-height:38px;font-weight:700;margin-top:'
            + spacing + 'px;cursor:help">' + escape(format(value))
            + (unit ? ' <small>' + escape(unit) + '</small>' : '') + '</div>';
          html += '<div style="font-size:12px;line-height:16px;margin-top:' + Math.max(2, spacing / 2)
            + 'px;color:' + colors.muted + '">' + escape(presentation.comparison.label || 'Comparison')
            + ': ' + escape(format(delta)) + ' · ' + escape(relative) + '</div>';
          html += '<div style="font-size:12px;line-height:16px;color:' + colors.muted + '">Previous: '
            + escape(format(previous)) + (unit ? ' ' + escape(unit) : '') + '</div>';
          const points = Array.isArray(prepared.points) ? prepared.points : [];
          const values = points.map(point => typeof point === 'object' && point !== null ? point.value : point);
          const finite = values.filter(numeric);
          if (finite.length) {
            let low = finite[0], high = finite[0];
            for (const item of finite) { low = Math.min(low, item); high = Math.max(high, item); }
            let path = '', connected = false;
            const circles = [];
            values.forEach((item, index) => {
              if (!numeric(item)) { connected = false; return; }
              const x = 4 + index * 292 / Math.max(1, values.length - 1);
              const y = high === low ? 30 : 56 - (item - low) * 52 / (high - low);
              path += (connected ? ' L' : ' M') + x.toFixed(2) + ',' + y.toFixed(2);
              circles.push('<circle data-id="sparkline-point-' + index + '" cx="' + x.toFixed(2)
                + '" cy="' + y.toFixed(2) + '" r="5" fill="transparent" style="cursor:help" />');
              connected = true;
            });
            html += '<svg viewBox="0 0 300 60" width="100%" height="60" aria-label="Trend" '
              + 'style="display:block;min-height:48px;margin-top:' + spacing + 'px;overflow:visible">'
              + '<path d="' + path + '" fill="none" stroke="' + colors.line + '" stroke-width="2" />'
              + circles.join('') + '</svg>';
          }
        }
        const height = Number.isFinite(options.height) ? Math.max(0, options.height) : 180;
        return Editor.generateHtml('<div style="position:relative;box-sizing:border-box;padding:' + spacing
          + 'px;overflow:auto;min-height:140px;height:' + height + 'px;color:' + colors.text
          + ';background:' + colors.background + '">' + html + '</div>');
      },
      args: [data, config]
    }),
    tooltip: {
      renderer: Editor.wrapFn({
        fn: function(event, prepared, presentation) {
          const escape = value => String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
          const numeric = value => typeof value === 'number' && Number.isFinite(value);
          const precision = Number.isInteger(presentation.labels.precision)
            ? Math.max(0, Math.min(10, presentation.labels.precision)) : 2;
          const format = value => numeric(value) ? value.toFixed(precision) : '—';
          const id = event && event.target && event.target.getAttribute
            ? String(event.target.getAttribute('data-id') || '') : '';
          const unit = presentation.tooltip.unit === true || presentation.tooltip.unit === 'from_field'
            ? '' : String(presentation.tooltip.unit || presentation.labels.unit || '');
          if (id === 'kpi-hint') {
            const text = presentation.hint.text
              || (Array.isArray(presentation.hint.content) ? presentation.hint.content.join(' · ') : '');
            return Editor.generateHtml('<div style="padding:10px;max-width:320px"><strong>'
              + escape(presentation.visible_title.text) + '</strong><div>' + escape(text) + '</div></div>');
          }
          if (id.indexOf('sparkline-point-') === 0) {
            const index = Number(id.slice('sparkline-point-'.length));
            const point = (prepared.points || [])[index];
            const value = point && typeof point === 'object' ? point.value : point;
            const period = point && typeof point === 'object' ? (point.date || point.period || '') : '';
            return Editor.generateHtml('<div style="padding:10px"><strong>' + escape(period)
              + '</strong><div>' + escape(format(value)) + (unit ? ' ' + escape(unit) : '') + '</div></div>');
          }
          if (id !== 'kpi-value') return '';
          const value = prepared.value;
          const previous = prepared.previous;
          const delta = numeric(value) && numeric(previous) ? value - previous : null;
          const relative = numeric(delta) && previous !== 0 ? delta / Math.abs(previous) * 100 : null;
          return Editor.generateHtml('<div style="padding:10px;min-width:220px">'
            + '<div><strong>Current</strong> ' + escape(prepared.current_period || '') + ': '
            + escape(format(value)) + (unit ? ' ' + escape(unit) : '') + '</div>'
            + '<div><strong>Previous</strong> ' + escape(prepared.previous_period || '') + ': '
            + escape(format(previous)) + (unit ? ' ' + escape(unit) : '') + '</div>'
            + '<div><strong>Change</strong>: ' + escape(format(delta)) + ' · '
            + (relative === null ? 'Undefined' : escape(format(relative)) + '%') + '</div></div>');
        },
        args: [data, config]
      })
    }
  };
};
