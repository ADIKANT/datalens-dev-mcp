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
          ? Math.max(0, Math.min(10, presentation.labels.precision)) : 0;
        const format = value => numeric(value) ? value.toFixed(precision).split('.').map((part, index) => index === 0 ? part.replace(/\B(?=(\d{3})+(?!\d))/g, ' ') : part).join('.') : '—';
        const unit = ['from_field', 'count'].includes(presentation.labels.unit) ? '' : String(presentation.labels.unit || '');
        const state = prepared && prepared.state ? prepared.state : numeric(prepared && prepared.value) ? 'ready' : 'no_data';
        const dark = presentation.states_theme.theme === 'dark';
        const text = dark ? '#f1f3f5' : 'var(--g-color-text-primary,#111827)';
        const muted = dark ? '#b0b5bc' : 'var(--g-color-text-secondary,#667085)';
        const accent = /^#[0-9a-f]{6}$/i.test(presentation.kpi.accent || '') ? presentation.kpi.accent : '#0B8043';
        const width = Number(options.width) > 0 ? Number(options.width) : 320;
        const height = Number(options.height) > 0 ? Number(options.height) : 200;
        const compact = width < 520 || height < 210, dense = width < 360 || height < 170;
        const customSpacing = Number(presentation.geometry.spacing);
        const px = Number.isFinite(customSpacing) && customSpacing !== 8 ? Math.max(0, customSpacing) : dense ? 12 : 14;
        const py = Number.isFinite(customSpacing) && customSpacing !== 8 ? Math.max(0, customSpacing) : dense ? 10 : 12;
        const gap = dense ? 5 : 7;
        const titleSize = dense ? 18 : 20, valueSize = dense ? 32 : compact ? 40 : 48;
        const valueLine = valueSize + 2, previousSize = dense ? 20 : compact ? 24 : 28;
        const labelSize = dense ? 10 : 12, deltaSize = dense ? 16 : compact ? 20 : 24;
        const title = presentation.visible_title || {}, hint = presentation.hint || {};
        const titleHtml = title.visible && title.owner === 'body'
          ? '<div style="font-size:' + titleSize + 'px;line-height:' + (titleSize + 2) + 'px;color:' + muted
            + ';text-transform:uppercase;letter-spacing:0.08em;font-weight:800">' + escape(title.text) + '</div>' : '';
        const hintHtml = hint.enabled ? '<div data-id="kpi-hint" style="display:inline-flex;align-items:center;justify-content:center;width:'
          + (dense ? 16 : 18) + 'px;height:' + (dense ? 16 : 18) + 'px;border-radius:50%;background:var(--g-color-base-generic,#F2F4F7);color:'
          + muted + ';font-size:12px;font-weight:800;cursor:help;flex:0 0 auto">?</div>' : '';
        let html = titleHtml || hintHtml ? '<div style="display:flex;align-items:center;gap:8px">' + titleHtml + hintHtml + '</div>' : '';
        const messages = {loading: 'Loading…', error: 'Data unavailable', no_data: 'No data'};
        if (messages[state]) {
          html += '<div role="status">' + messages[state] + '</div>';
        } else {
          const valid = numeric(prepared.value) && numeric(prepared.previous);
          const delta = valid ? prepared.value - prepared.previous : null;
          const pct = valid && prepared.previous !== 0 ? Math.round(delta / Math.abs(prepared.previous) * 1000) / 10 : null;
          const deltaText = pct === null ? 'n/a' : (pct > 0 ? '+' : '') + String(pct) + '%';
          const positive = pct !== null && pct > 0, negative = pct !== null && pct < 0;
          const bg = positive ? '#E6F4EA' : negative ? '#FDECEC' : '#F3F4F6';
          const fg = positive ? '#0B8043' : negative ? '#B3261E' : '#5F6368';
          html += '<div style="display:flex;flex-direction:column;gap:' + (dense ? 2 : 4) + 'px">'
            + '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:' + (dense ? 10 : 14) + 'px">'
            + '<div data-id="kpi-value" style="font-size:' + valueSize + 'px;line-height:' + valueLine
            + 'px;font-weight:700;letter-spacing:-0.03em;white-space:nowrap;cursor:help">' + escape(format(prepared.value))
            + (unit ? ' <small>' + escape(unit) + '</small>' : '') + '</div>'
            + '<div data-id="kpi-delta" aria-label="' + escape(!valid ? 'Missing comparison' : prepared.previous === 0 ? 'Undefined: previous = 0' : deltaText) + '" style="padding:' + (dense ? '5px 8px' : '6px 10px') + ';border-radius:' + (dense ? 10 : 14)
            + 'px;background:' + bg + ';color:' + fg + ';font-size:' + deltaSize + 'px;line-height:' + (deltaSize + 2)
            + 'px;font-weight:800;white-space:nowrap;letter-spacing:-0.02em;flex:0 0 auto">' + escape(deltaText) + '</div></div>'
            + '<div style="font-size:' + labelSize + 'px;line-height:' + (labelSize + 2) + 'px;color:' + muted
            + ';text-transform:uppercase;letter-spacing:0.08em;font-weight:800">' + escape(presentation.comparison.label || 'VS PREV WINDOW') + '</div>'
            + '<div data-id="kpi-previous" style="font-size:' + previousSize + 'px;line-height:' + (previousSize + 2)
            + 'px;color:' + muted + ';font-weight:700;letter-spacing:-0.02em">' + escape(format(prepared.previous)) + '</div></div>';
          const points = Array.isArray(prepared.points) ? prepared.points : [];
          const values = points.map(p => p && typeof p === 'object' ? p.value : p);
          const finite = values.filter(numeric);
          if (finite.length) {
            const reserved = py * 2 + titleSize + valueLine + previousSize + 2 + labelSize + gap * 4 + 12;
            const sh = Math.max(34, Math.min(dense ? 52 : 82, height - reserved));
            const sw = Math.max(120, width - px * 2), base = sh - 3;
            const low = Math.min(0, ...finite), high = Math.max(1, ...finite), span = high - low;
            const segments = []; let segment = [];
            values.forEach((v, i) => {
              if (!numeric(v)) { if (segment.length) segments.push(segment); segment = []; return; }
              segment.push({x: 3 + (values.length === 1 ? (sw - 6) / 2 : i * (sw - 6) / (values.length - 1)), y: base - (v - low) * (sh - 6) / span, i: i});
            });
            if (segment.length) segments.push(segment);
            const marks = segments.map(seg => {
              const coordinates = seg.map(p => p.x.toFixed(2) + ',' + p.y.toFixed(2)).join(' ');
              return '<polyline data-id="sparkline-area" fill="' + accent + '" fill-opacity="' + (dense ? '.08' : '.10')
                + '" stroke="none" points="' + seg[0].x + ',' + base + ' ' + coordinates + ' ' + seg[seg.length - 1].x + ',' + base + '" />'
                + '<polyline fill="none" stroke="' + accent + '" stroke-width="' + (dense ? 2 : 2.5) + '" stroke-linecap="round" stroke-linejoin="round" points="' + coordinates + '" />'
                + seg.map(p => '<circle data-id="sparkline-point-' + p.i + '" cx="' + p.x + '" cy="' + p.y + '" r="' + (seg.length === 1 ? 2 : 5) + '" fill="' + (seg.length === 1 ? accent : 'transparent') + '" />').join('');
            }).join('');
            html += '<div style="display:flex;flex:1 1 auto;align-items:flex-end;min-height:0"><svg width="' + sw + '" height="' + sh
              + '" viewBox="0 0 ' + sw + ' ' + sh + '" aria-label="Trend" style="display:block;overflow:hidden">' + marks + '</svg></div>';
          }
        }
        return Editor.generateHtml('<div style="box-sizing:border-box;width:100%;height:' + height + 'px;padding:' + py + 'px ' + px
          + 'px;background:transparent;border:none;border-radius:0;box-shadow:none;font-family:Inter,Arial,sans-serif;color:' + text
          + ';display:flex;flex-direction:column;gap:' + gap + 'px;overflow:hidden">' + html + '</div>');
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
            ? Math.max(0, Math.min(10, presentation.labels.precision)) : 0;
          const format = value => numeric(value) ? value.toFixed(precision).split('.').map((part, index) => index === 0 ? part.replace(/\B(?=(\d{3})+(?!\d))/g, ' ') : part).join('.') : '—';
          const id = event && event.target && event.target.getAttribute
            ? String(event.target.getAttribute('data-id') || '') : '';
          const unit = presentation.tooltip.unit === true || presentation.tooltip.unit === 'from_field'
            ? '' : String(presentation.tooltip.unit || presentation.labels.unit || '');
          if (id === 'kpi-hint') {
            const text = presentation.hint.text
              || (Array.isArray(presentation.hint.content) ? presentation.hint.content.join(' · ') : '');
            return Editor.generateHtml('<div style="padding:10px 12px;max-width:280px;border-radius:12px;background:rgba(17,24,39,.96);color:#F9FAFB;box-shadow:0 12px 28px rgba(15,23,42,.28)"><strong>'
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
          if (id !== 'kpi-value' && id !== 'kpi-delta') return '';
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
